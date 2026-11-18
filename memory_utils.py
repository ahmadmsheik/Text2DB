import os
import json
from llama_index.core.memory import ChatMemoryBuffer # RAM
from auth_utils import load_users

MEMORY_FILE = "conversation_memory.json"
memory_store = {}  # in-memory map: user_id → User object


class User:
    def __init__(self, user_id: str, role: str):
        self.user_id = user_id
        self.role = role
        self.memory = ChatMemoryBuffer.from_defaults(token_limit=1024)

    def add_message(self, role: str, content: str):
        self.memory.put_messages([{"role": role, "content": content}])

    def get_history(self):
        return self.memory.get_all()

    def save_to_disk(self):
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r") as f:
                all_data = json.load(f)
        else:
            all_data = {}

        all_data[self.user_id] = self.get_history()

        with open(MEMORY_FILE, "w") as f:
            json.dump(all_data, f, indent=4)

    @classmethod
    def load_from_disk(cls, user_id: str, role: str):
        """
        Load memory for a user from disk if available.
        """
        user = cls(user_id, role)

        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r") as f:
                all_data = json.load(f)
            messages = all_data.get(user_id, [])
            user.memory.put_messages(messages)

        return user


def get_memory(user_id: str) -> ChatMemoryBuffer:
    """
    Get the memory buffer for a user, loading from disk if needed.
    """
    if user_id not in memory_store:
        users = load_users()
        user_info = next((u for u in users.values() if u["user_id"] == user_id), None)
        role = user_info["role"] if user_info else "user"
        memory_store[user_id] = User.load_from_disk(user_id, role)

    return memory_store[user_id].memory


def update_memory(user_id: str, role: str, message: str):
    """
    Add a message to a user's memory.
    """
    if user_id not in memory_store:
        memory_store[user_id] = User.load_from_disk(user_id, role)

    memory_store[user_id].add_message(role, message)


def save_memory_to_disk(user_id: str):
    """
    Persist the user's memory to disk manually (e.g. on exit).
    """
    user = memory_store.get(user_id)
    if user:
        user.save_to_disk()


def get_user(user_id: str) -> User:
    return memory_store.get(user_id)
