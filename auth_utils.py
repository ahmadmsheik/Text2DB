import uuid
import json
import os

USER_FILE = "users.json"

def load_users():
    if not os.path.exists(USER_FILE):
        return {}
    with open(USER_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USER_FILE, "w") as f:
        json.dump(users, f, indent=4)

def register_user(username: str, password: str, role: str = "user") -> dict:
    users = load_users()
    if username in users:
        return {"success": False, "message": "Username already exists."}

    user_id = str(uuid.uuid4())
    users[username] = {
        "user_id": user_id,
        "password": password,
        "role": role
    }
    save_users(users)
    return {"success": True, "user_id": user_id, "role": role}

def login_user(username: str, password: str) -> dict:
    users = load_users()
    user = users.get(username)
    if user and user["password"] == password:
        return {"success": True, "user_id": user["user_id"], "role": user["role"]}
    return {"success": False, "message": "Invalid username or password."}
