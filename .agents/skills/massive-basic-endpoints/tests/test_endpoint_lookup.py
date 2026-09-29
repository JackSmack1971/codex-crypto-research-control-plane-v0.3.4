from __future__ import annotations

import argparse
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("endpoint_lookup", ROOT / "scripts" / "endpoint_lookup.py")
assert SPEC and SPEC.loader
lookup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lookup)


class EndpointLookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = lookup.load_catalog()

    def select(self, **kwargs):
        defaults = dict(
            market=None,
            query=None,
            capability=None,
            path=None,
            include_deprecated=False,
            limit=5,
            json=False,
        )
        defaults.update(kwargs)
        return lookup.select_entries(self.catalog, argparse.Namespace(**defaults))

    def test_catalog_count(self):
        self.assertEqual(self.catalog["entry_count"], 96)
        self.assertEqual(len(self.catalog["entries"]), 96)

    def test_crypto_daily_market_summary_ranks_first(self):
        rows = self.select(market="crypto", query="daily market summary")
        self.assertTrue(rows)
        self.assertEqual(rows[0]["path"], "/v2/aggs/grouped/locale/global/market/crypto/{date}")

    def test_market_alias(self):
        rows = self.select(market="fx", query="previous day bar")
        self.assertEqual(rows[0]["market"], "forex")
        self.assertEqual(rows[0]["path"], "/v2/aggs/ticker/{forexTicker}/prev")

    def test_deprecated_hidden_when_current_alternative_exists(self):
        rows = self.select(market="stocks", query="dividends", limit=10)
        self.assertTrue(any(e["capability"] == "Dividends" and not e["deprecated"] for e in rows))
        self.assertFalse(any(e["deprecated"] for e in rows))

    def test_exact_shared_path_requires_market_to_get_single_limit(self):
        rows = self.select(path="/v3/reference/tickers", include_deprecated=True, limit=20)
        markets = {e["market"] for e in rows}
        self.assertGreater(len(markets), 1)
        rows = self.select(market="indices", path="/v3/reference/tickers", include_deprecated=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["basic_limit"], "Updated hourly; history All history")

    def test_treasury_description_is_not_truncated(self):
        rows = self.select(market="economy", query="Treasury yields")
        self.assertEqual(rows[0]["path"], "/fed/v1/treasury-yields")
        self.assertGreater(len(rows[0]["best_for"]), len("Historical U.S."))

    def test_representative_task_cases(self):
        cases = [json.loads(line) for line in (ROOT / "evals" / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
        tasks = [case for case in cases if case["kind"] == "task"]
        self.assertEqual(len(tasks), 10)
        for case in tasks:
            expected = case["expected"]
            rows = self.select(market=expected["market"], capability=expected["capability"], limit=10)
            self.assertTrue(rows, case["id"])
            self.assertTrue(any(row["path"] == expected["path"] for row in rows), case["id"])


if __name__ == "__main__":
    unittest.main()
