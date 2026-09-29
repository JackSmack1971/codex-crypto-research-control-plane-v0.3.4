from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_NAMES = {"CONTROL_PLANE_MANIFEST.json", ".DS_Store", "Thumbs.db"}
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".runtime"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".swp"}


def include(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return (
        path.is_file()
        and path.name not in EXCLUDED_NAMES
        and not any(part in EXCLUDED_PARTS for part in rel.parts)
        and path.suffix.lower() not in EXCLUDED_SUFFIXES
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generated-at", default=date.today().isoformat())
    args = ap.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    entries = []
    for path in sorted((p for p in ROOT.rglob("*") if include(p)), key=lambda p: p.as_posix()):
        data = path.read_bytes()
        entries.append({
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        })
    manifest = {
        "name": "codex-crypto-research-control-plane",
        "version": version,
        "generated_at": args.generated_at,
        "file_count": len(entries),
        "files": entries,
    }
    out = ROOT / "CONTROL_PLANE_MANIFEST.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out} with {len(entries)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
