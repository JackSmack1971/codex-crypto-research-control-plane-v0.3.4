from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from common import digest, load_json, require_fields, write_new_json

REQUIRED = [
    "hypothesis_id", "created_at", "question", "economic_rationale", "signal_definition",
    "universe", "primary_metric", "expected_sign", "test_period", "multiple_testing_family", "status"
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("--out-dir", default="research/registry")
    args = ap.parse_args()
    obj = load_json(args.payload)
    errors = require_fields(obj, REQUIRED, "hypothesis")
    if obj.get("status") != "REGISTERED":
        errors.append("hypothesis.status_must_be_REGISTERED")
    if errors:
        print("\n".join(errors))
        return 2
    obj["content_digest"] = digest(obj)
    out = Path(args.out_dir) / f"{obj['hypothesis_id']}.json"
    try:
        write_new_json(out, obj)
    except FileExistsError:
        print(f"IMMUTABLE_CONFLICT:{out}")
        return 3
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
