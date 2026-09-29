import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "control_plane"
sys.path.insert(0, str(SCRIPTS))
from promotion_gate import evaluate


class PromotionGateTests(unittest.TestCase):
    def base(self):
        h = {"hypothesis_id": "h1", "status": "REGISTERED", "multiple_testing_family": "fam"}
        v = {
            "candidate_id": "c1",
            "hypothesis_id": "h1",
            "validator": "statistical-validator",
            "verdict": "PROMOTE",
            "checks": {
                "chronology": True,
                "leakage": True,
                "multiple_testing": True,
                "uncertainty": True,
                "parameter_stability": True,
                "regime_dependence": True,
                "turnover": True,
                "cost_scenarios": True,
                "oos": True,
            },
            "evidence": ["validation-details.json"],
        }
        a = {
            "subject_type": "candidate",
            "subject_id": "c1",
            "candidate_id": "c1",
            "hypothesis_id": "h1",
            "auditor": "methodology-auditor",
            "status": "PASS",
            "reason_codes": [],
            "evidence": ["audit-details.json"],
        }
        d = {
            "run_id": "r1",
            "status": "PASS",
            "cutoff": "2026-09-28T23:00:00Z",
            "datasets": ["crypto_grouped"],
            "findings": [],
        }
        return h, v, a, d

    def test_passes_only_complete_positive_evidence(self):
        ok, reasons = evaluate(*self.base())
        self.assertTrue(ok)
        self.assertEqual([], reasons)

    def test_blocks_missing_multiple_testing_family(self):
        h, v, a, d = self.base()
        h["multiple_testing_family"] = ""
        ok, reasons = evaluate(h, v, a, d)
        self.assertFalse(ok)
        self.assertIn("hypothesis.missing_multiple_testing_family", reasons)

    def test_blocks_failed_oos(self):
        h, v, a, d = self.base()
        v["checks"]["oos"] = False
        ok, reasons = evaluate(h, v, a, d)
        self.assertFalse(ok)
        self.assertIn("validation.check_failed:oos", reasons)

    def test_blocks_failed_parameter_stability(self):
        h, v, a, d = self.base()
        v["checks"]["parameter_stability"] = False
        ok, reasons = evaluate(h, v, a, d)
        self.assertFalse(ok)
        self.assertIn("validation.check_failed:parameter_stability", reasons)

    def test_blocks_audit_failure(self):
        h, v, a, d = self.base()
        a["status"] = "FAIL"
        ok, reasons = evaluate(h, v, a, d)
        self.assertFalse(ok)
        self.assertIn("audit.status.FAIL", reasons)

    def test_blocks_audit_identity_mismatch(self):
        h, v, a, d = self.base()
        a["subject_id"] = "c2"
        ok, reasons = evaluate(h, v, a, d)
        self.assertFalse(ok)
        self.assertIn("identity.audit_subject_mismatch", reasons)

    def test_blocks_missing_validation_evidence(self):
        h, v, a, d = self.base()
        v["evidence"] = []
        ok, reasons = evaluate(h, v, a, d)
        self.assertFalse(ok)
        self.assertIn("validation.missing_evidence", reasons)


if __name__ == "__main__":
    unittest.main()
