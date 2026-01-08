import json
import os

DATA_FILE = "data/last_ids.json"


def load_last_id(email: str) -> int:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return 0
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            return int(data.get(email, 0))
    except:
        return 0

def save_last_id(email: str, msg_id: int):
    os.makedirs("data", exist_ok=True)
    
    data = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        except:
            data = {}
    
    data[email] = msg_id
    
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
