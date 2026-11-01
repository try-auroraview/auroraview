"""Execute mutation workflow shell steps against deterministic CLI/artifact fixtures."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class MutationWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "output.txt"
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/mutation-testing.yml").read_text(encoding="utf-8")
        )
        self.steps = {
            step["name"]: step
            for step in workflow["jobs"]["incremental"]["steps"]
            if "name" in step
        }

    def run_step(self, name, prefix="", pipefail=False):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash, "bash is required to execute workflow steps")
        script = self.steps[name]["run"].replace("${{ steps.changed.outputs.file_args }}", "")
        return subprocess.run(
            [bash, "--noprofile", "--norc", "-e", "-c", prefix + script],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(
                os.environ,
                GITHUB_OUTPUT=self.output.as_posix(),
                GITHUB_ENV=(self.root / "env.txt").as_posix(),
                MSYS_NO_PATHCONV="1",
                SHELLOPTS="pipefail" if pipefail else "",
            ),
        )

    def parse(self, counts=None):
        if counts is not None:
            artifacts = self.root / "mutants.out"
            artifacts.mkdir()
            for name, count in counts.items():
                (artifacts / f"{name}.txt").write_text("mutant\n" * count, encoding="utf-8")
        result = self.run_step("Parse mutation results")
        self.assertEqual(result.returncode, 0, result.stderr)
        return dict(line.split("=", 1) for line in self.output.read_text().splitlines())

    def test_empty_result_files_from_failed_baseline(self):
        self.assertEqual(
            self.parse(dict.fromkeys(("caught", "missed", "timeout", "unviable"), 0)),
            {"caught": "0", "missed": "0", "timeout": "0", "unviable": "0", "score": "N/A"},
        )

    def test_missing_results_do_not_report_a_perfect_score(self):
        self.assertEqual(
            self.parse(),
            {"caught": "0", "missed": "0", "timeout": "0", "unviable": "0", "score": "N/A"},
        )

    def test_nonempty_results_keep_counts_and_score(self):
        self.assertEqual(
            self.parse({"caught": 3, "missed": 1, "timeout": 2, "unviable": 1}),
            {"caught": "3", "missed": "1", "timeout": "2", "unviable": "1", "score": "75%"},
        )

    def test_caught_mutants_with_other_files_missing(self):
        self.assertEqual(
            self.parse({"caught": 2}),
            {"caught": "2", "missed": "0", "timeout": "0", "unviable": "0", "score": "100%"},
        )

    def test_mutation_exit_status_survives_log_pipeline(self):
        self.assertIsNotNone(shutil.which("jq"), "jq is required for the workflow metadata probe")
        for exit_code in (0, 2, 3, 4):
            for pipefail in (False, True):
                with self.subTest(exit_code=exit_code, pipefail=pipefail):
                    # Control only cargo's external responses; execute the workflow's
                    # real metadata probe, pipeline and shell error handling.
                    cargo = (
                        """
                    cargo() {
                      if [ "$1" = metadata ]; then
                        printf '%%s\\n' '{"packages":[{"features":{}}]}'
                      else
                        echo 'mutation CLI output'
                        return %d
                      fi
                    }
                    """
                        % exit_code
                    )
                    result = self.run_step("Run incremental mutation testing", cargo, pipefail)
                    self.assertEqual(result.returncode, exit_code, result.stderr)
                    self.assertIn(
                        "mutation CLI output", (self.root / "mutants-output.txt").read_text()
                    )


if __name__ == "__main__":
    unittest.main()
