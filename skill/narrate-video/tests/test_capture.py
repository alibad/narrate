"""Runs the capture adapter's helper checks (camera keys, frame slots, the frame listing) under Node; no browser."""
import shutil
import subprocess
import unittest
from pathlib import Path

TEST = Path(__file__).resolve().parent / "test_capture.mjs"


@unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
class CaptureHelperTests(unittest.TestCase):
    def test_helper_checks_pass(self):
        result = subprocess.run(["node", str(TEST)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("helper checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
