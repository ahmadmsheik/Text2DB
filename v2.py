from llm_utils import get_llm
from typing import List, Dict
from sqlalchemy import create_engine, text
import re
import json
import os

def generate_table_descriptions(table_ddl_list: List[str], chunk_size: int = 5) -> List[str]:
    """
    Sends CREATE TABLE schema strings to the LLM in chunks and gets back
    annotated descriptions. Returns a list of enriched schema strings.
    """
    described_chunks = []
    llm = get_llm()

    for i in range(0, len(table_ddl_list), chunk_size):
        chunk = table_ddl_list[i:i + chunk_size]
        ddl_block = "\n\n".join(chunk)

        prompt = f"""
            You are a database assistant. Given these CREATE TABLE statements, generate a description for each table and its columns.
            
            ❌ Do NOT include any introduction like “Here are the descriptions...”.

            
            For each table:

            1. Start with a one-line summary of what the table stores.
            2. Then describe each column and its role.

            Add your description after each table.
            
            Use this format:

            **CREATE TABLE TableName;**

            Description:
            This table ...
            - column_name (DATA_TYPE): explanation
            - ...

            ONLY use this format. Do not include parentheses or full DDL inside CREATE TABLE.
            Here is the schema:

            {ddl_block}
        """

        llm_response = llm.complete(prompt).text
        described_chunks.append(llm_response.strip())

    return described_chunks


def extract_create_table_list(connection_uri: str) -> List[str]:
    engine = create_engine(connection_uri)
    table_statements = []

    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
        ))
        tables = [row[0] for row in result.fetchall()]

        for table in tables:
            # Get column definitions
            columns = conn.execute(text(f"""
                SELECT COLUMN_NAME, DATA_TYPE 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = '{table}'
            """)).fetchall()

            # Get foreign key constraints
            fks = conn.execute(text(f"""
                SELECT 
                    kcu.COLUMN_NAME,
                    ccu.TABLE_NAME AS REFERENCED_TABLE_NAME,
                    ccu.COLUMN_NAME AS REFERENCED_COLUMN_NAME
                FROM 
                    INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                JOIN 
                    INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu 
                    ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                JOIN 
                    INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu 
                    ON rc.UNIQUE_CONSTRAINT_NAME = ccu.CONSTRAINT_NAME
                WHERE 
                    kcu.TABLE_NAME = '{table}'
            """)).fetchall()

            # Format column definitions
            col_defs = []
            for col in columns:
                col_def = f"{col[0]} {col[1]}"
                for fk in fks:
                    if fk[0] == col[0]:
                        col_def += f" REFERENCES {fk[1]}({fk[2]})"
                col_defs.append(col_def)

            col_def_str = ",\n  ".join(col_defs)
            create_stmt = f"""CREATE TABLE {table} (
  {col_def_str}
);"""
            table_statements.append(create_stmt)

    return table_statements



def split_described_chunks_per_table(described_chunks: List[str]) -> List[str]:
    """
    Splits multi-table LLM responses into individual table+description chunks
    using the LLM's markdown-style formatting: **CREATE TABLE table_name;**
    """
    all_table_chunks = []

    for chunk in described_chunks:
        split_chunks = re.split(r"(?=\*\*CREATE TABLE\s+\w+;\*\*)", chunk.strip(), flags=re.IGNORECASE)


        for subchunk in split_chunks:
            cleaned = subchunk.strip()
            if cleaned:
                all_table_chunks.append(cleaned)

    return all_table_chunks


def generate_join_graph(schema_chunks: List[str], chunk_size: int = 5) -> Dict[str, Dict[str, str]]:
    """
    Given a list of CREATE TABLE statements, pass them to the LLM in chunks.
    The LLM returns inferred join relationships with ON clauses.
    The function aggregates these into a join graph dict.
    """
    join_graph = {}
    llm = get_llm()

    for i in range(0, len(schema_chunks), chunk_size):
        chunk = schema_chunks[i:i + chunk_size]
        ddl_block = "\n\n".join(chunk)

        prompt = f"""
        You are a database relationship inference assistant. Given these CREATE TABLE statements,
        return a JSON dictionary of **direct joinable relationships** using foreign keys.

        Each key should be a table, and each value should be a dictionary of tables it directly joins with.
        The value should be the appropriate SQL ON clause.

        ⚠️ DO NOT infer joins through intermediate tables.
        ⚠️ ONLY include tables that have explicit direct foreign key references.

        Use this format (JSON only, no explanations):
        {{
        "orders": {{
            "users": "orders.user_id = users.user_id",
            "payments": "orders.order_id = payments.order_id"
        }},
        "order_items": {{
            "orders": "order_items.order_id = orders.order_id",
            "products": "order_items.product_id = products.product_id"
        }}
        }}

        Here is the schema:

        {ddl_block}
        """

        llm_response = llm.complete(prompt).text.strip()
        try:
            chunk_graph = eval(llm_response)
            for table, joins in chunk_graph.items():
                join_graph.setdefault(table, {}).update(joins)
        except Exception as e:
            print(f"⚠️ Failed to parse LLM join output: {e}\n{llm_response}")

    return join_graph


def extract_join_graph_from_db(connection_uri: str) -> Dict[str, Dict[str, str]]:
    engine = create_engine(connection_uri)
    join_graph = {}

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                fk_tab.TABLE_NAME AS FK_Table,
                fk_col.COLUMN_NAME AS FK_Column,
                pk_tab.TABLE_NAME AS PK_Table,
                pk_col.COLUMN_NAME AS PK_Column
            FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS AS rc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS fk_col
                ON rc.CONSTRAINT_NAME = fk_col.CONSTRAINT_NAME
            JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS fk_tab
                ON fk_col.TABLE_NAME = fk_tab.TABLE_NAME
            JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE AS pk_col
                ON rc.UNIQUE_CONSTRAINT_NAME = pk_col.CONSTRAINT_NAME
            JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS pk_tab
                ON pk_col.TABLE_NAME = pk_tab.TABLE_NAME;
        """))

        for row in result.fetchall():
            fk_table = row.FK_Table
            pk_table = row.PK_Table
            fk_col = row.FK_Column
            pk_col = row.PK_Column

            # Forward edge
            join_graph.setdefault(fk_table, {})[pk_table] = f"{fk_table}.{fk_col} = {pk_table}.{pk_col}"
            # Optional reverse edge
            join_graph.setdefault(pk_table, {})[fk_table] = f"{fk_table}.{fk_col} = {pk_table}.{pk_col}"

    return join_graph



def save_join_graph(db_name: str, join_graph: dict, filepath: str = "join_graphs.json"):
    """
    Saves or updates the join graph for a specific database inside a JSON file.
    """
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            all_graphs = json.load(f)
    else:
        all_graphs = {}

    all_graphs[db_name] = join_graph

    with open(filepath, "w") as f:
        json.dump(all_graphs, f, indent=2)
