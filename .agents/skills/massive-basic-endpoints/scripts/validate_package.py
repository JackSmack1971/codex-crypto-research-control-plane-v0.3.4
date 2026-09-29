#!/usr/bin/env python3
"""Static integrity checks for the Massive Basic endpoint skill package."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
CATALOG = ROOT / "references" / "endpoint-catalog.json"
EVALS = ROOT / "evals" / "cases.jsonl"

ALLOWED_MARKETS = {"stocks", "options", "indices", "forex", "crypto", "futures", "economy"}
REQUIRED_ENTRY_KEYS = {
    "id",
    "market",
    "capability",
    "method",
    "path",
    "basic_limit",
    "best_for",
    "deprecated",
    "source_section",
}
REQUIRED_EVAL_COUNTS = {"routing_positive": 20, "routing_negative": 20, "routing_neighbor": 10, "task": 10, "failure": 5}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def check_markdown_links(errors: list[str]) -> None:
    for path in ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            if not resolved.exists():
                fail(errors, f"broken markdown link in {path.relative_to(ROOT)}: {target}")


def main() -> int:
    errors: list[str] = []

    text = SKILL.read_text(encoding="utf-8")
    fm = frontmatter(text)
    name = fm.get("name", "")
    description = fm.get("description", "")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        fail(errors, f"invalid skill name: {name!r}")
    if len(name) > 64:
        fail(errors, "skill name exceeds 64 characters")
    if not description or len(description) > 1024:
        fail(errors, f"description length invalid: {len(description)}")
    for required in ("Basic", "2026-09-28"):
        if required not in description:
            fail(errors, f"description missing routing discriminator: {required}")

    ui_path = ROOT / "agents" / "openai.yaml"
    ui_text = ui_path.read_text(encoding="utf-8") if ui_path.exists() else ""
    if not ui_text.startswith("interface:\n"):
        fail(errors, "agents/openai.yaml missing interface mapping")
    for key in ("display_name", "short_description", "default_prompt"):
        match = re.search(rf'^  {key}: "([^"\n]+)"$', ui_text, re.M)
        if not match:
            fail(errors, f"agents/openai.yaml missing quoted {key}")
        elif key == "short_description" and not 25 <= len(match.group(1)) <= 64:
            fail(errors, f"short_description length invalid: {len(match.group(1))}")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    entries = catalog.get("entries", [])
    if catalog.get("entry_count") != 96 or len(entries) != 96:
        fail(errors, f"catalog must contain 96 entries; declared={catalog.get('entry_count')} actual={len(entries)}")
    if catalog.get("snapshot_date") != "2026-09-28" or catalog.get("plan") != "Basic":
        fail(errors, "catalog snapshot metadata changed unexpectedly")

    ids: list[str] = []
    compound: list[tuple[str, str, str]] = []
    for i, entry in enumerate(entries, 1):
        missing = REQUIRED_ENTRY_KEYS - entry.keys()
        if missing:
            fail(errors, f"entry {i} missing keys: {sorted(missing)}")
            continue
        ids.append(entry["id"])
        compound.append((entry["market"], entry["capability"], entry["path"]))
        if entry["market"] not in ALLOWED_MARKETS:
            fail(errors, f"entry {entry['id']} has invalid market {entry['market']!r}")
        if entry["method"] != "GET":
            fail(errors, f"entry {entry['id']} has unexpected method {entry['method']!r}")
        if not entry["path"].startswith("/"):
            fail(errors, f"entry {entry['id']} has invalid path {entry['path']!r}")
        if not entry["basic_limit"].strip():
            fail(errors, f"entry {entry['id']} has empty basic_limit")
        if len(entry["best_for"].strip()) < 24:
            fail(errors, f"entry {entry['id']} has suspiciously short best_for text")

    if len(ids) != len(set(ids)):
        fail(errors, "catalog entry ids are not unique")
    if len(compound) != len(set(compound)):
        fail(errors, "duplicate market/capability/path rows found")

    treasury = [e for e in entries if e["path"] == "/fed/v1/treasury-yields"]
    if len(treasury) != 1 or treasury[0]["best_for"] == "Historical U.S.":
        fail(errors, "Treasury Yields description repair is missing")

    eval_counts: Counter[str] = Counter()
    seen_eval_ids: set[str] = set()
    for line_no, line in enumerate(EVALS.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(errors, f"invalid eval JSON on line {line_no}: {exc}")
            continue
        case_id = case.get("id")
        kind = case.get("kind")
        if not case_id or case_id in seen_eval_ids:
            fail(errors, f"missing/duplicate eval id on line {line_no}: {case_id!r}")
        seen_eval_ids.add(case_id)
        eval_counts[kind] += 1
    if dict(eval_counts) != REQUIRED_EVAL_COUNTS:
        fail(errors, f"eval corpus counts mismatch: {dict(eval_counts)}")

    check_markdown_links(errors)

    for path in ROOT.rglob("*"):
        if path.is_file() and (path.suffix in {".pyc", ".pyo"} or "__pycache__" in path.parts):
            fail(errors, f"cache artifact present: {path.relative_to(ROOT)}")
        if path.is_file():
            lower = path.name.lower()
            if lower.endswith((".tmp", ".bak", ".swp")):
                fail(errors, f"temporary file present: {path.relative_to(ROOT)}")

    placeholder_re = re.compile(r"\b(?:TODO|TBD|CHANGEME|PLACEHOLDER)\b", re.I)
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".yaml", ".json", ".jsonl"}:
            data = path.read_text(encoding="utf-8", errors="replace")
            if placeholder_re.search(data):
                fail(errors, f"placeholder token present: {path.relative_to(ROOT)}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        print(f"\n{len(errors)} validation error(s)")
        return 1

    print("PASS: package static integrity")
    print(f"PASS: {len(entries)} catalog entries across {len(ALLOWED_MARKETS)} markets")
    print(f"PASS: eval corpus {sum(eval_counts.values())} cases with required category counts")
    print("PASS: frontmatter, links, placeholders, and artifact hygiene")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
