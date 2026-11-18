from llama_index.readers.database import DatabaseReader
from sqlalchemy import create_engine, text
from config import DB_URI
import json
import os
from typing import List


db_reader = None
engine = None


def create_db_reader(db_uri):
    global db_reader
    global engine
    try:
        engine = create_engine(db_uri)
        db_reader = DatabaseReader(engine)
        return db_reader
    except Exception as e:
        print(f"❌ DB Initialization Error: {e}")
        return None
    

def run_query(query: str, db_name: str = None):
    if db_reader is None:
        if db_name:
            # Try to initialize the database reader using the saved connection
            connections = load_database_connections()
            if db_name in connections:
                connection_uri = connections[db_name]
                create_db_reader(connection_uri)
            else:
                raise RuntimeError(f"Database '{db_name}' not found in saved connections.")
        else:
            raise RuntimeError("Database not initialized. Call create_db_reader() first or provide db_name.")
    try:
        query = query.strip().strip("```").replace("sql", "").strip()
        query = query.strip('`')
        if query.startswith('SELECT'):
            result = db_reader.load_data(query)
            result = extract_rows_from_documents(result)
            return True, result
        elif query.startswith('INSERT') or query.startswith('DELETE') or query.startswith('UPDATE'):
            return True, execute_non_select_query(query)
    except Exception as e:
        return False, f"❌ Query Execution Error: {e}"
    

def extract_rows_from_documents(documents):
    result = []
    for doc in documents:
        line = doc.text_resource.text
        row = {}
        for pair in line.split(","):
            if ":" in pair:
                key, value = pair.split(":", 1)
                row[key.strip()] = value.strip()
        result.append(row)
    return result


def get_all_databases():
    try:
        engine = create_engine(DB_URI.format(DBNAME='master'))
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sys.databases WHERE database_id > 4"))
            dbs = [row[0] for row in result.fetchall()]
        return dbs
    except Exception as e:
        print(f"❌ Failed to retrieve databases: {e}")
        return []
    
    
def execute_non_select_query(query: str):
    
    global engine
    try:
        with engine.connect() as conn:
            conn.execute(text(query))
            conn.commit()
        return "✅ Query executed successfully."
    except Exception as e:
        return f"❌ Execution failed: {e}"
    
    
    
    """
    NEW TO VERSION 2
    """
    
def save_db_list_with_connection(database_name: str, connection_string: str, filepath: str = "available_databases.json"):
    """
    Saves or updates a single database and its connection string in a persistent JSON file.

    Args:
        database_name (str): Name of the database.
        connection_string (str): SQLAlchemy-style connection string.
        filepath (str): Path to the JSON file.
    """
    data = {}

    # Step 1: Load existing file (if any)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️ Warning: Failed to load existing data: {e}")
            data = {}

    # Step 2: Ensure "databases" key exists
    if "databases" not in data or not isinstance(data["databases"], dict):
        data["databases"] = {}

    # Step 3: Add or update the entry
    data["databases"][database_name] = connection_string

    # Step 4: Save back to file
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"✅ Saved database '{database_name}' to {filepath}")
    except Exception as e:
        print(f"❌ Failed to save database: {e}")


def load_database_connections(filepath: str = "available_databases.json") -> dict:
    """
    Loads the full {database_name: connection_string} dictionary.
    """
    if not os.path.exists(filepath):
        return {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("databases", {})
    except Exception as e:
        print(f"❌ Failed to load connection strings: {e}")
        return {}


    
    
def is_valid_database(server: str, driver: str, db_name: str) -> bool:
    """
    Checks whether the provided database name exists on the given SQL Server.

    Args:
        server (str): SQL Server address (e.g., 'localhost').
        db_name (str): Database name to check.

    Returns:
        bool: True if the database exists, False otherwise.
    """
    try:
        uri = f"mssql+pyodbc://@{server}/master?driver={driver.replace(' ', '+')}"
        engine = create_engine(uri)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sys.databases WHERE database_id > 4"))
            db_names = [row[0] for row in result.fetchall()]

        return db_name in db_names

    except Exception as e:
        print(f"❌ DB validation error: {e}")
        return False
    
    
    
def try_connect_to_database(server: str, db_name: str) -> tuple:
    """
    Validates if a given database exists and builds connection URI.

    Args:
        server (str): SQL Server hostname or IP.
        driver (str): ODBC driver name.
        db_name (str): Database name to validate.

    Returns:
        tuple: (success: bool, message or connection_uri)
    """
    try:
        dbs = get_all_databases()
        if db_name in dbs:
            connection_uri = f"mssql+pyodbc://@{server}/{db_name}?driver=ODBC+Driver+17+for+SQL+Server"
            return True, connection_uri
        else:
            return False, f"Database '{db_name}' not found on server."
    except Exception as e:
        return False, str(e)


def extract_schema_from_database(connection_uri: str) -> str:
    """
    Extracts schema from the connected database as CREATE TABLE statements.
    """
    engine = create_engine(connection_uri)
    schema_text = []

    with engine.connect() as conn:
        result = conn.execute(text("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"))
        tables = [row[0] for row in result.fetchall()]

        for table in tables:
            columns = conn.execute(text(f"""
                SELECT COLUMN_NAME, DATA_TYPE 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = '{table}'
            """))
            col_defs = ", ".join([f"{col[0]} {col[1]}" for col in columns])
            schema_text.append(f"-- Table: {table}\nCREATE TABLE {table} ({col_defs});")

    return "\n\n".join(schema_text)


    
