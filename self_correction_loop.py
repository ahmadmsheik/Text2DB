import json
from db_utils import run_query

def try_execute_query(query):
    success, result = run_query(query)
    return success, result


def log_correction(prompt, schema, corrected_query, bad_query=None, error_message=None, path="corrected_sql_data.jsonl"):
    record = {
        "input": f"{prompt}\nSchema:\n{schema}",
        "output": corrected_query,
        "metadata": {
            "original_query": bad_query,
            "error_message": error_message
        }
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")