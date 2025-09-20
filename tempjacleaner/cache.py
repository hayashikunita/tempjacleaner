from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any

DEFAULT_CACHE = ".tempjacleaner_cache.json"

def load_cache(root: str, filename: str = DEFAULT_CACHE) -> Dict[str, Any]:
    p = Path(root) / filename
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_cache(root: str, data: Dict[str, Any], filename: str = DEFAULT_CACHE) -> None:
    p = Path(root) / filename
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def file_fingerprint(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"

__all__ = ["load_cache", "save_cache", "file_fingerprint", "DEFAULT_CACHE"]
