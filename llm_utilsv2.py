from typing import List, Dict
from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.llms.ollama import Ollama
from config import LLM_NAME
import json
from json_repair import repair_json
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

def get_llm():
    return Ollama(model=LLM_NAME, request_timeout=240, temperature=0.2)

# === Step 1: Use the Join Graph to plan required tables and joins ===
def plan_query_with_join_graph(question: str, join_graph: Dict[str, Dict[str, str]]) -> Dict[str, List[str]]:
    
    llm = get_llm()
    prompt = f"""
            You are a SQL planning assistant. You will receive:

            1. A user question.
            2. A join graph: it tells you which tables are connected via foreign keys.

            Your task:
            - Identify the minimal set of tables required to answer the question.
            - Use only the foreign keys from the join graph to decide how tables are joined.
            - Do NOT assume any columns or join paths not explicitly shown.
            - If a join path is ambiguous or missing, leave it empty.

            CRITICAL: Return ONLY valid JSON in this exact format. No explanations, no comments, no greetings, no prefaces, no additional text:

            {{
            "tables": ["..."],
            "joins": ["..."]
            }}

            Example:
            Question: Which students are enrolled in Math courses?

            Join Graph:
            {{
            "Students": {{"Enrollments": "Students.StudentID = Enrollments.StudentID"}},
            "Enrollments": {{"Courses": "Enrollments.CourseID = Courses.CourseID"}},
            "Courses": {{}}
            }}

            Output:
            {{
            "tables": ["Students", "Enrollments", "Courses"],
            "joins": [
                "Students.StudentID = Enrollments.StudentID",
                "Enrollments.CourseID = Courses.CourseID"
            ]
            }}

            Now, here is the user question and join graph:

            Question: {question}

            Join Graph:
            {json.dumps(join_graph, indent=2)}

            Return only valid JSON. Your entire response MUST start with '{{' and end with '}}'. Do not include any extra text or explanations.
        """
    
    print("Prompt: ", prompt)

    response = llm.complete(prompt).text.strip()
    print("Plan from the LLM:", response)
    
    # Extract JSON from response (handle cases where LLM adds extra text)
    json_start = response.find('{')
    json_end = response.rfind('}') + 1
    
    if json_start != -1 and json_end > json_start:
        json_part = response[json_start:json_end]
        print("Extracted JSON:", json_part)
    else:
        json_part = response
    
    try:
        fixed_json = repair_json(json_part)
        data = json.loads(fixed_json)
        if not isinstance(data, dict) or "tables" not in data or "joins" not in data:
            print(f"Warning: Unexpected response format: {data}")
            # Provide fallback structure
            return {"tables": [], "joins": []}
        return data
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Warning: Failed to parse LLM response: {e}")
        print(f"Raw response: {response}")
        print(f"Extracted JSON part: {json_part}")
        # Provide fallback structure
        return {"tables": [], "joins": []}

# === Step 2: Retrieve table descriptions from vector DB ===
def retrieve_table_descriptions(table_names: List[str], db_name: str) -> List[str]:
    embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
    
    storage_path = f"./storage/{db_name}"
    storage_context = StorageContext.from_defaults(persist_dir=storage_path)
    index = load_index_from_storage(storage_context, embed_model=embed_model)
    retriever = index.as_retriever()

    descriptions = []
    for table in table_names:
        query = f"Return the schema and description of the table `{table}`"
        print(f"Retrieving from storage path: {storage_path}")
        nodes = retriever.retrieve(query)
        
        if nodes:
            # Only take the first node
            first_node = nodes[0]
            chunk_text = first_node.text if hasattr(first_node, 'text') else str(first_node)
            descriptions.append(chunk_text)
            print(f"First Chunk Text of {first_node}:", chunk_text)
        else:
            descriptions.append(f"No description found for table: {table}")

    return descriptions

# === Step 3: Generate SQL Query ===
def generate_sql_query(question: str, descriptions: List[str], joins: List[str]) -> str:
    llm = get_llm()
    prompt = f"""
    You are a highly disciplined SQL Server assistant.

    🎯 TASK: Convert natural language to executable T-SQL for CRUD operations based on the provided schema. Return ONLY the T-SQL query, with no comments, explanations, or other text.

    Given the following descriptions of tables and how they are joined, generate the SQL query that answers the question.

    Descriptions:
    {"\n\n".join(descriptions)}

    Joins:
    {"\n".join(joins)}

    Question:
    {question}

    T-SQL Query::
    """

    return llm.complete(prompt).text.strip()

def load_join_graph_by_db_name(db_name: str, path: str = "./join_graphs.json") -> Dict[str, Dict[str, str]]:
    with open(path, "r") as f:
        full_graph = json.load(f)
    return full_graph.get(db_name, {})


def run_text_to_sql_pipeline(question: str, db_name: str) -> tuple[str, List[str], List[str]]:
    join_graph = load_join_graph_by_db_name(db_name)
    
    print("Join Graph: ", join_graph)
    plan = plan_query_with_join_graph(question, join_graph)
    
    print("Plan: ", plan)

    table_names = plan["tables"]
    joins = plan["joins"]

    descriptions = retrieve_table_descriptions(table_names, db_name)
    
    print("Retrieved tables: ", descriptions)
    print("Passed Join Grpah:", joins)
    sql_query = generate_sql_query(question, descriptions, joins)
    print("Generated SQL QUERY: ", sql_query)

    return sql_query, descriptions, joins



