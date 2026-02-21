import json
import os
from datetime import datetime

DATA_FILE = "users_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_user(user_id):
    data = load_data()
    user_id_str = str(user_id)
    if user_id_str not in data:
        data[user_id_str] = {
            "last_poll_time": None,
            "answers": [],
            "test_results": []
        }
        save_data(data)
    return data[user_id_str]

def update_user(user_id, updates):
    data = load_data()
    user_id_str = str(user_id)
    if user_id_str in data:
        data[user_id_str].update(updates)
    else:
        data[user_id_str] = updates
    save_data(data)
