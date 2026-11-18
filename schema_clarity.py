from llm_utils import get_llm
import json
from json_repair import repair_json

def revise_schema_description(
    original_schema_sql: str,
    current_description_json: str,
    feedback: str,
    max_retries= 3
) -> str:
    """
    Uses the LLM to revise a JSON schema description based on user feedback.

    Args:
        original_schema_sql (str): The original SQL schema string.
        current_description_json (str): The current JSON-formatted schema description.
        feedback (str): User-provided feedback to improve the description.

    Returns:
        str: Updated JSON schema description (as a string).
    """
    llm = get_llm()

    prompt = """
   You previously generated the following JSON schema description:

    {current_description_json}

    The user gave the following feedback:
    "{feedback}"

    Here is the original SQL schema:
    {original_schema_sql}

    Your task is to revise the description based on this feedback.

    🧠 Steps:
    1. Read the user's feedback carefully.
    2. Identify every part of the schema where this feedback should apply (table names, column names, descriptions).
    3. Update the relevant descriptions accordingly. Ensure **all related entries are consistent** with the change.
    4. Do not change parts that the feedback doesn't apply to.
    5. Return ONLY a valid JSON object — with no extra text or formatting.

    ✅ Output format example (structure and style to follow):

    {{
        "TABLE NAME": {{
            "description": "A brief summary of what the table stores.",
            "columns": {{
            "COLUMN NAME": "Description of the column's purpose.",
            "COLUMN NAME": "Another column and what it means."
            }}
        }},
        "TABLE NAME": {{
            "description": "Summary of this second table.",
            "columns": {{
            "COLUMN NAME": "Explains the first column in this table.",
            "COLUMN NAME": "Explains the second column."
            }}
        }}
        }}
    """.format(
    current_description_json=current_description_json,
    feedback=feedback,
    original_schema_sql=original_schema_sql
    )

    response = llm.complete(prompt)
    raw_text = response.text.strip()
    parsed, error = try_parse_json(raw_text)

    if parsed:
        return parsed

    repaired = fix_invalid_json_with_jsonrepair(raw_text)
    parsed, _ = try_parse_json(repaired)

    if parsed:
        return parsed

    raise ValueError("LLM output could not be repaired into valid JSON.")



def generate_structured_schema_description(schema: str) -> dict:

    prompt = """
        You are a strict database documentation assistant.

        Your task is to analyze the SQL schema below and return a structured **valid JSON object** describing each table and its columns.

        ⚠️ Follow these formatting rules:
        - Output must be a valid JSON object.
        - Keys and values must use double quotes.
        - Do NOT include any markdown, code blocks, or explanations.
        - Do NOT include trailing commas.
        - Ensure all brackets and commas are properly closed.

        ✅ Output format example (use this structure exactly):

        {{
        "TABLE_1": {{
            "description": "A brief summary of what the table stores.",
            "columns": {{
            "COLUMN_1": "Description of the column's purpose.",
            "COLUMN_2": "Another column and what it means."
            }}
        }},
        "TABLE_2": {{
            "description": "Summary of this second table.",
            "columns": {{
            "COLUMN_A": "Explains the first column in this table.",
            "COLUMN_B": "Explains the second column."
            }}
        }}
        }}

        Now, return the JSON description for the following schema:

        --- SQL SCHEMA START ---
        {schema}
        --- SQL SCHEMA END ---
    """.format(schema=schema)

    return generate_valid_json(prompt)


def try_parse_json(raw_text):
    try:
        return json.loads(raw_text), None
    except json.JSONDecodeError as e:
        return None, e
    

def generate_valid_json(prompt: str) -> dict:
    llm = get_llm()
    response = llm.complete(prompt)
    raw_text = response.text.strip()

    parsed, error = try_parse_json(raw_text)
    if parsed:
        return parsed

    repaired = fix_invalid_json_with_jsonrepair(raw_text)
    parsed, _ = try_parse_json(repaired)

    if parsed:
        return parsed

    raise ValueError("Failed to produce valid JSON from LLM output.")



def fix_invalid_json_with_jsonrepair(raw_text: str) -> str:
    try:
       return repair_json(raw_text) 
    except Exception as e:
        raise ValueError(f"json_repair failed: {e}")


def extract_joins_with_llm(schema_chunk, current_graph):
    llm = get_llm()
    prompt = f"""
        Given the following SQL schema chunk:

        {schema_chunk}

        And the current join graph:
        {json.dumps(current_graph)}

        Add any new join relationships based on foreign key constraints or common patterns.
        Respond ONLY in the following JSON format:
        {{
        "table1": ["related_table1", "related_table2"],
        ...
        }}
"""
    llm_output = llm.complete(prompt)
    return json.loads(llm_output)