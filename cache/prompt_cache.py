import json
import hashlib
from pathlib import Path
from datetime import datetime
from config import CACHE_DIR

Path(CACHE_DIR).mkdir(exist_ok=True)


def get_cached(cache_key: str) -> str | None:
    cache_file = Path(CACHE_DIR) / f"{cache_key}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)["program"]
    return None


def set_cached(cache_key: str, program: str):
    cache_file = Path(CACHE_DIR) / f"{cache_key}.json"
    with open(cache_file, "w") as f:
        json.dump({
            "program": program,
            "timestamp": datetime.now().isoformat()
        }, f)