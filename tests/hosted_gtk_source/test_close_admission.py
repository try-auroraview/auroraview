"""Run 12 source-only close-admission cases without polluting pytest imports.

The child loads actual Python lifecycle code with an explicit fake native
boundary. This driver is not an additional lifecycle case or native acceptance.
"""

import subprocess
import sys
import unittest
from pathlib import Path


class HostedSourceIsolationTests(unittest.TestCase):
    def test_source_cases_in_isolated_child(self):
        cases = Path(__file__).with_name("_close_admission_cases.py")
        result = subprocess.run(
            [sys.executable, "-B", str(cases), "-v"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        # unittest reports skips and unexpected successes after OK, so the
        # exact final summary also rejects those outcomes and missing cases.
        self.assertRegex(output, r"(?m)^Ran 12 tests in [^\n]+\n\nOK\s*\Z", output)
        self.assertNotRegex(output, r"(?m)^.*\.\.\. skipped\b", output)
        print("Source-only child suite: 12 passed, 0 skipped; no native acceptance")


if __name__ == "__main__":
    unittest.main()
