from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True


def _typename(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    return type(value).__name__


def _matches_type(value: Any, expected: str) -> bool:
    actual = _typename(value)
    if expected == "number":
        return actual in {"integer", "number"}
    return actual == expected


def validate(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    expected = schema.get("type")
    if expected:
        types = [expected] if isinstance(expected, str) else expected
        if not any(_matches_type(value, item) for item in types):
            return [f"{path}:type:expected={types}:actual={_typename(value)}"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}:const:{schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}:enum:{value!r}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}:minLength:{schema['minLength']}")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{path}:pattern:{schema['pattern']}")
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{path}:format:date-time")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}:minimum:{schema['minimum']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}:minItems:{schema['minItems']}")
        if schema.get("uniqueItems"):
            rendered = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(rendered) != len(set(rendered)):
                errors.append(f"{path}:uniqueItems")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                errors.extend(validate(item, item_schema, f"{path}[{idx}]"))

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}:missing:{key}")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                errors.extend(validate(item, properties[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}:additionalProperty:{key}")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate one JSON artifact against the repository's supported JSON-Schema subset.")
    ap.add_argument("artifact")
    ap.add_argument("schema")
    args = ap.parse_args()
    try:
        artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"LOAD_ERROR:{exc}")
        return 2
    errors = validate(artifact, schema)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"PASS:{args.artifact}:{args.schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
