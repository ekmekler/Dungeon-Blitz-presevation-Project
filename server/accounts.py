import os
import json
import struct
import tempfile
import uuid

from threading import Lock
from BitBuffer import BitBuffer

_ACCOUNTS_PATH = "Accounts.json"
_SAVES_DIR     = "saves"
_lock          = Lock()

def _atomic_write(path: str, data) -> None:
    """
    Atomically write JSON-serializable `data` to `path`.
    Writes to a temp file then renames it into place.
    """
    dirpath = os.path.dirname(path) or "."
    os.makedirs(dirpath, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", dir=dirpath, delete=False, encoding="utf-8") as tf:
        json.dump(data, tf, ensure_ascii=False, indent=2)
        tf.flush()
        os.fsync(tf.fileno())

    os.replace(tf.name, path)

def load_accounts() -> dict[str, int]:
    with open(_ACCOUNTS_PATH, "r", encoding="utf-8") as f:
            entries = json.load(f)
    return { e["email"]: int(e["user_id"]) for e in entries }


def save_accounts_index(index: dict[str, int]) -> None:
    entries = [
        {"email": email, "user_id": uid}
        for email, uid in index.items()
    ]
    with _lock:
        _atomic_write(_ACCOUNTS_PATH, entries)

def get_or_create_user_id(email: str) -> int:
    email = email.strip().lower()
    accounts = load_accounts()

    if email in accounts:
        return accounts[email]

    user_id = max(accounts.values(), default=0) + 1

    accounts[email] = user_id
    save_accounts_index(accounts)

    os.makedirs(_SAVES_DIR, exist_ok=True)
    save_path = os.path.join(_SAVES_DIR, f"{user_id}.json")
    _atomic_write(save_path, {"user_id": user_id, "characters": []})
    return user_id

def is_character_name_taken(name: str) -> bool:
    """
    Check if a character name exists in any user's save file.
    """
    name = name.strip().lower()
    accounts = load_accounts()
    for user_id in accounts.values():
        save_path = os.path.join(_SAVES_DIR, f"{user_id}.json")
        try:
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                characters = data.get("characters", [])
                for char in characters:
                    if char.get("name", "").strip().lower() == name:
                        return True
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return False

def build_popup_packet(message: str, disconnect: bool = False) -> bytes:
    buf = BitBuffer(debug=True)
    buf.write_method_13(message)
    buf.write_method_6(1 if disconnect else 0, 1)
    payload = buf.to_bytes()
    return struct.pack(">HH", 0x1B, len(payload)) + payload