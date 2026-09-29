#!/usr/bin/env python3
"""Deterministically query the bundled Massive Basic endpoint snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references" / "endpoint-catalog.json"

MARKET_ALIASES = {
    "stock": "stocks",
    "stocks": "stocks",
    "equity": "stocks",
    "equities": "stocks",
    "option": "options",
    "options": "options",
    "index": "indices",
    "indices": "indices",
    "fx": "forex",
    "forex": "forex",
    "currency": "forex",
    "currencies": "forex",
    "crypto": "crypto",
    "cryptocurrency": "crypto",
    "cryptocurrencies": "crypto",
    "future": "futures",
    "futures": "futures",
    "macro": "economy",
    "economy": "economy",
    "economic": "economy",
}


def tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def normalize_market(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip().lower()
    return MARKET_ALIASES.get(key, key)


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def score(entry: dict, query: str) -> tuple[int, int, str, str]:
    q = query.strip().lower()
    q_tokens = tokens(q)
    capability = entry["capability"].lower()
    haystack = " ".join(
        [
            entry["market"],
            entry["capability"],
            entry["path"],
            entry["basic_limit"],
            entry["best_for"],
        ]
    ).lower()
    overlap = len(q_tokens & tokens(haystack))
    phrase_bonus = 6 if q and q in capability else 0
    exact_cap_bonus = 12 if q == capability else 0
    path_bonus = 8 if q and q in entry["path"].lower() else 0
    deprecated_penalty = -3 if entry.get("deprecated") else 0
    return (
        exact_cap_bonus + phrase_bonus + path_bonus + overlap + deprecated_penalty,
        overlap,
        entry["market"],
        entry["capability"],
    )


def select_entries(catalog: dict, args: argparse.Namespace) -> list[dict]:
    entries = catalog["entries"]
    market = normalize_market(args.market)
    if market:
        entries = [e for e in entries if e["market"] == market]
    if args.path:
        entries = [e for e in entries if e["path"] == args.path]
    if args.capability:
        needle = args.capability.strip().lower()
        entries = [e for e in entries if needle in e["capability"].lower()]
    if not args.include_deprecated:
        non_deprecated = [e for e in entries if not e.get("deprecated")]
        if non_deprecated:
            entries = non_deprecated
    if args.query:
        ranked = sorted(entries, key=lambda e: score(e, args.query), reverse=True)
        positive = [e for e in ranked if score(e, args.query)[0] > 0]
        entries = positive or ranked
    else:
        entries = sorted(entries, key=lambda e: (e["market"], e["capability"], e["path"]))
    return entries[: args.limit]


def format_table(entries: list[dict]) -> str:
    if not entries:
        return "NO_MATCH\n"
    lines: list[str] = []
    for e in entries:
        status = "deprecated" if e.get("deprecated") else "current-in-snapshot"
        lines.extend(
            [
                f"[{e['market']}] {e['capability']} ({status})",
                f"  {e['method']} {e['path']}",
                f"  Basic snapshot limit: {e['basic_limit']}",
                f"  Best for: {e['best_for']}",
            ]
        )
        if e.get("note"):
            lines.append(f"  Note: {e['note']}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query the bundled 2026-09-28 Massive Basic REST endpoint snapshot."
    )
    parser.add_argument("--market", help="stocks/options/indices/forex/crypto/futures/economy")
    parser.add_argument("--query", help="free-text routing query")
    parser.add_argument("--capability", help="case-insensitive capability substring")
    parser.add_argument("--path", help="exact documented REST path")
    parser.add_argument("--include-deprecated", action="store_true")
    parser.add_argument("--limit", type=int, default=5, help="maximum rows to return (default: 5)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of readable text")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.limit < 1 or args.limit > 96:
        print("--limit must be between 1 and 96", file=sys.stderr)
        return 2
    catalog = load_catalog()
    entries = select_entries(catalog, args)
    if args.json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(format_table(entries))
    return 0 if entries else 1


if __name__ == "__main__":
    raise SystemExit(main())
