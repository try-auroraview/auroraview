"""Execute mutation workflow shell steps against deterministic CLI/artifact fixtures."""

import json
import os
import shlex
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

    def test_root_helpers_are_enabled_with_mixed_workspace_features(self):
        self.assertIsNotNone(shutil.which("jq"), "jq is required for the workflow metadata probe")
        cargo = """
        cargo() {
          if [ "$1" = metadata ]; then
            printf '%s\\n' '{"packages":[{"name":"auroraview","features":{"test-helpers":[]}},{"name":"auroraview-core","features":{}}]}'
          else
            printf '%s\\n' "$@" > cargo-args.txt
          fi
        }
        """
        result = self.run_step("Run incremental mutation testing", cargo)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = (self.root / "cargo-args.txt").read_text().splitlines()
        self.assertIn("--features", args, "root integration tests require test-helpers on Linux")
        self.assertEqual(args[args.index("--features") + 1], "test-helpers")
        self.assertLess(
            args.index("--features"), args.index("--"), "features must apply to baseline builds"
        )
        package_option = next((arg for arg in args if arg in ("-p", "--package")), None)
        self.assertIsNotNone(
            package_option, "feature flags must target the root package explicitly"
        )
        self.assertEqual(args[args.index(package_option) + 1], "auroraview")

    def test_real_mutation_baseline_builds_feature_gated_integration_test(self):
        for tool in ("cargo", "cargo-mutants", "cargo-nextest"):
            self.assertIsNotNone(
                shutil.which(tool), f"{tool} must be installed for the compiler test"
            )
        files = {
            "Cargo.toml": "\n".join(
                (
                    "[package]",
                    'name = "auroraview"',
                    'version = "0.0.0"',
                    'edition = "2021"',
                    "[features]",
                    "test-helpers = []",
                    "[workspace]",
                )
            ),
            "src/lib.rs": "pub mod ipc;\n",
            "src/ipc/mod.rs": (
                "pub struct Timer;\nimpl Timer {\n"
                '    #[cfg(feature = "test-helpers")]\n'
                "    pub fn should_tick(&self) -> bool { true }\n}\n"
            ),
            "tests/timer.rs": (
                "use auroraview::ipc::Timer;\n"
                "#[test]\nfn tick_available() { assert!(Timer.should_tick()); }\n"
            ),
        }
        for name, source in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        for name in (".cargo/mutants.toml", ".config/nextest.toml"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, path)

        # Use the actual workflow command and configs, with only the changed
        # file replaced by a dependency-free fixture of the Timer bug pattern.
        script = self.steps["Run incremental mutation testing"]["run"]
        command = next(
            line.strip()
            for line in script.splitlines()
            if line.strip().startswith("cargo mutants ")
        )
        command = command.replace("${{ steps.changed.outputs.file_args }}", "--file src/ipc/mod.rs")
        args = shlex.split(command.split(" 2>&1", 1)[0])
        args[0] = shutil.which("cargo")
        result = subprocess.run(
            args,
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ, CARGO_TERM_COLOR="never"),
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-6000:])
        outcomes = json.loads((self.root / "mutants.out/outcomes.json").read_text(encoding="utf-8"))
        self.assertEqual(outcomes["outcomes"][0]["summary"], "Success")
        self.assertGreater(outcomes["total_mutants"], 0, "the compiler test must execute a mutant")
        self.assertEqual(outcomes["caught"], outcomes["total_mutants"])

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
