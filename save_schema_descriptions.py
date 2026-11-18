import json
from config import SCHEMA_FILE
import os

def save_schema_to_store(db_name: str, schema_description: dict):

    # Load current store
    if os.path.exists(SCHEMA_FILE):
        with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    # Update the entry
    data[db_name] = {
        "description": schema_description
    }

    with open(SCHEMA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_schema_for_db(db_name: str):
    if not os.path.exists(SCHEMA_FILE):
        return None
    
    print("DB NAME:", db_name)

    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    description = data.get(db_name, {}).get("description")
    print("Description Retrieved:", description)

    return description