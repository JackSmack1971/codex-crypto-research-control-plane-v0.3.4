import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StructureTests(unittest.TestCase):
    def test_control_plane_validator(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "control_plane" / "validate_control_plane.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("PASS: 9 agents, 7 skills (5 workflow + 2 support), 20 schemas, Massive MCP configured, deterministic daily pipeline present", proc.stdout)

    def test_eval_corpus_validator(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "control_plane" / "validate_evals.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("routing corpus 20 positive / 20 negative / 10 neighbor", proc.stdout)


if __name__ == "__main__":
    unittest.main()
