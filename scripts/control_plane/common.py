from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{p}: expected a JSON object")
    return data


def canonical_bytes(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(data: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(data)).hexdigest()


def write_new_json(path: str | Path, data: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        raise FileExistsError(f"immutable artifact already exists: {p}")
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with p.open("x", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    return p


def require_fields(obj: dict[str, Any], fields: list[str], label: str) -> list[str]:
    missing = [field for field in fields if field not in obj or obj[field] in ("", None)]
    return [f"{label}.missing:{field}" for field in missing]


def parse_timestamp(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: invalid ISO-8601 timestamp: {value!r}") from exc
