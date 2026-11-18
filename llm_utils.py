from llama_index.llms.ollama import Ollama
from config import LLM_NAME
from prompts import ROUTING_PROMPT, GENERAL_RESPONSE_PROMPT, SQL_PROMPT_TEMPLATE, CORRECTION_QUERY_PROMPT
from rag_utils import query_schema_rag
from rag_training import query_sql_qa_rag
import json
from typing import List

def get_llm():
    return Ollama(model=LLM_NAME, request_timeout=240, temperature=0.2)

def classify_input(question: str):
    llm = get_llm()
    prompt = ROUTING_PROMPT.format(question=question)
    response = llm.complete(prompt)
    return response.text.strip().lower()

def generate_general_response(question: str, context: str):
    llm = get_llm()
    prompt = GENERAL_RESPONSE_PROMPT.format(question=question, context=context)
    response = llm.complete(prompt)
    return response.text.strip()

def generate_sql_query(question: str, schema_description: dict):
    llm = get_llm()
    schema_retrieved = query_schema_rag(question)
    description_str = json.dumps(schema_description, indent=2) if schema_description else "No description available."
    examples_retrieved = query_sql_qa_rag(question)
    prompt = SQL_PROMPT_TEMPLATE.format(input=question,
                                        schema_retrieved=schema_retrieved,
                                        schema_description=description_str,
                                        examples=examples_retrieved) 
    print(prompt)    
    response = llm.complete(prompt)
    return response.text.strip(), schema_retrieved

def generate_correction_response(question: str, bad_query: str, error_message: str):
    llm = get_llm()
    schema_retrieved = query_schema_rag(question)
    examples_retrieved = query_sql_qa_rag(question)
    prompt = CORRECTION_QUERY_PROMPT.format(question=question, schema=schema_retrieved, 
                                            examples=examples_retrieved, bad_query= bad_query, error_message=error_message)

    response = llm.complete(prompt)
    return response.text.strip()

def generate_correction_responsev2(question: str, bad_query: str, error_message: str, table_descriptions: List[str], joins: List[str]) -> str:
    """
    Generates a corrected SQL query using the existing schema descriptions and joins
    instead of querying RAG or examples.
    """
    llm = get_llm()

    prompt = f"""
    You are a SQL fixer assistant.

    🎯 TASK: The user submitted a question and a SQL query was generated, but it failed.
    Use the table descriptions and join conditions below to fix the SQL query.

    Return ONLY the corrected T-SQL query — no explanation or comments.

    🧠 QUESTION:
    {question}

    ❌ FAILED QUERY:
    {bad_query}

    ⚠️ ERROR MESSAGE:
    {error_message}

    📄 TABLE DESCRIPTIONS:
    {'\n\n'.join(table_descriptions)}

    🔗 JOINS:
    {'\n'.join(joins)}

    🔁 FIXED SQL QUERY:
    """

    response = llm.complete(prompt)
    return response.text.strip()

