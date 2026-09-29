import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "control_plane"))
from common import write_new_json

class ImmutabilityTests(unittest.TestCase):
    def test_existing_artifact_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "artifact.json"
            write_new_json(path, {"a": 1})
            with self.assertRaises(FileExistsError):
                write_new_json(path, {"a": 2})
            self.assertIn('"a": 1', path.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
