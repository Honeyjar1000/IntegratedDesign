import requests
from typing import Any, Dict
from config import API_BASE

def post_json(path: str, payload: Dict[str, Any], timeout: float = 2.0) -> Dict[str, Any]:
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_json(path: str, timeout: float = 2.0) -> Dict[str, Any]:
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=timeout)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}
