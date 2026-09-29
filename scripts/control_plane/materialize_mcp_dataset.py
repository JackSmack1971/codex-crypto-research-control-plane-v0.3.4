from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

sys.dont_write_bytecode = True

TRUNCATION_MARKERS = ("[truncated:", "... truncated", "<truncated>")


def _load_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    lower = text.lower()
    if any(marker in lower for marker in TRUNCATION_MARKERS):
        raise ValueError(f"truncation_marker:{path}")
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif suffix == ".json":
        obj = json.loads(text)
        rows = obj.get("rows") if isinstance(obj, dict) and "rows" in obj else obj
        if not isinstance(rows, list):
            raise ValueError(f"expected_json_array_or_rows:{path}")
    elif suffix == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
    else:
        raise ValueError(f"unsupported_chunk_extension:{path.suffix}")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"rows_must_be_objects:{path}")
    return rows


def _canonical_row(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _parse_csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _key(row: dict[str, Any], fields: list[str]) -> tuple[str, ...]:
    return tuple(str(row.get(field, "")) for field in fields)


def _sort_rows(rows: list[dict[str, Any]], fields: list[str]) -> None:
    if fields:
        rows.sort(key=lambda row: _key(row, fields))
    else:
        rows.sort(key=_canonical_row)


def _validate_unique(rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    if not fields:
        return
    seen: set[tuple[str, ...]] = set()
    for idx, row in enumerate(rows):
        missing = [field for field in fields if field not in row]
        if missing:
            raise ValueError(f"row[{idx}].missing_key_fields:{','.join(missing)}")
        key = _key(row, fields)
        if key in seen:
            raise ValueError(f"duplicate_key:{fields}:{key}")
        seen.add(key)


def main() -> int:
    ap = argparse.ArgumentParser(description="Materialize bounded Massive MCP query_data chunks into an immutable canonical JSONL dataset.")
    ap.add_argument("chunks", nargs="+")
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--attempt-id", required=True)
    ap.add_argument("--market", required=True)
    ap.add_argument("--endpoint-path", required=True)
    ap.add_argument("--params-json", default="{}")
    ap.add_argument("--requirement", choices=["CORE", "ENRICHMENT", "EVENT_OPTIONAL"], required=True)
    ap.add_argument("--research-cutoff", required=True)
    ap.add_argument("--retrieved-at", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--expected-rows", type=int, required=True)
    ap.add_argument("--sort-fields", default="")
    ap.add_argument("--key-fields", default="")
    ap.add_argument("--out-dir", default="research/data")
    args = ap.parse_args()

    try:
        params = json.loads(args.params_json)
        if not isinstance(params, dict):
            raise ValueError("params_json_must_be_object")
        rows: list[dict[str, Any]] = []
        chunk_paths = [Path(value) for value in args.chunks]
        for path in chunk_paths:
            rows.extend(_load_rows(path))
        if len(rows) != args.expected_rows:
            raise ValueError(f"row_count_mismatch:expected={args.expected_rows}:actual={len(rows)}")
        key_fields = _parse_csv_list(args.key_fields)
        sort_fields = _parse_csv_list(args.sort_fields)
        _validate_unique(rows, key_fields)
        _sort_rows(rows, sort_fields)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"MATERIALIZATION_ERROR:{exc}")
        return 2

    out_dir = Path(args.out_dir) / args.attempt_id
    data_path = out_dir / f"{args.dataset_id}.jsonl"
    meta_path = out_dir / f"{args.dataset_id}.meta.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    if data_path.exists() or meta_path.exists():
        print(f"IMMUTABLE_CONFLICT:{data_path if data_path.exists() else meta_path}")
        return 3

    body = "".join(_canonical_row(row) + "\n" for row in rows).encode("utf-8")
    data_digest = _sha256_bytes(body)
    metadata = {
        "dataset_id": args.dataset_id,
        "run_id": args.run_id,
        "attempt_id": args.attempt_id,
        "market": args.market,
        "endpoint_path": args.endpoint_path,
        "params": params,
        "requirement": args.requirement,
        "research_cutoff": args.research_cutoff,
        "retrieved_at": args.retrieved_at,
        "as_of": args.as_of,
        "row_count": len(rows),
        "sort_fields": sort_fields,
        "key_fields": key_fields,
        "data_path": data_path.as_posix(),
        "data_digest": data_digest,
        "source_chunks": [path.as_posix() for path in chunk_paths],
        "materialization_status": "VERIFIED",
    }
    try:
        with data_path.open("xb") as handle:
            handle.write(body)
        with meta_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError:
        print(f"IMMUTABLE_CONFLICT:{data_path}")
        return 3

    print(json.dumps({"data": data_path.as_posix(), "metadata": meta_path.as_posix(), "row_count": len(rows), "data_digest": data_digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
