"""Execute mutation workflow shell steps against deterministic CLI/artifact fixtures."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutation_changed_files  # noqa: E402

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
        self.workflow = workflow
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

    def test_incremental_command_scopes_all_crates_to_changed_lines(self):
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
        # --workspace + --in-diff is the only selector that reaches sub-crates
        # and restricts mutants to the lines changed by this PR.
        self.assertIn("--workspace", args)
        self.assertIn("--in-diff", args)
        self.assertEqual(args[args.index("--in-diff") + 1], "mutation.diff")
        # A hard-coded root-package filter or --file args reproduce the bug:
        # --file unions with examine_globs, -p auroraview drops sub-crates.
        self.assertNotIn("-p", args)
        self.assertNotIn("--package", args)
        self.assertNotIn("--file", args)
        # Mixed workspace features must not leak a bare --features: cargo-mutants
        # forwards it to every member and crashes on crates that lack it.
        self.assertNotIn("--features", args)

    def test_feature_guard_enables_helpers_when_all_members_define_it(self):
        self.assertIsNotNone(shutil.which("jq"), "jq is required for the workflow metadata probe")
        cargo = """
        cargo() {
          if [ "$1" = metadata ]; then
            printf '%s\\n' '{"packages":[{"name":"a","features":{"test-helpers":[]}},{"name":"b","features":{"test-helpers":[]}}]}'
          else
            printf '%s\\n' "$@" > cargo-args.txt
          fi
        }
        """
        result = self.run_step("Run incremental mutation testing", cargo)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = (self.root / "cargo-args.txt").read_text().splitlines()
        self.assertIn("--features", args)
        self.assertEqual(args[args.index("--features") + 1], "test-helpers")
        self.assertLess(
            args.index("--features"), args.index("--"), "features must apply to baseline builds"
        )

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

        # Use the actual workflow command and configs. The feature guard resolves
        # to --features test-helpers for this single-package fixture; scope the
        # selector to the fixture file so the real baseline build stays bounded.
        script = self.steps["Run incremental mutation testing"]["run"]
        command = next(
            line.strip()
            for line in script.splitlines()
            if line.strip().startswith("cargo mutants ")
        )
        command = command.replace('"${feature_args[@]}"', '--features "test-helpers"')
        command = command.replace("--in-diff mutation.diff", "--file src/ipc/mod.rs")
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
            timeout=90,
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

    def test_changed_files_step_generates_diff_and_classifies_windows_only(self):
        changed = self.steps["Get changed Rust files"]["run"]
        self.assertIn("> mutation.diff", changed)
        self.assertIn("mutation_changed_files.py", changed)
        self.assertIn("changed-files.txt", changed)
        # The old --file union selector and its file_args output are gone.
        self.assertNotIn("file_args", changed)
        self.assertNotIn("--file ", changed)

    def test_run_step_gates_on_windows_only_output(self):
        run = self.steps["Run incremental mutation testing"]
        self.assertIn("windows_only != 'true'", run["if"])
        command = next(
            line.strip()
            for line in run["run"].splitlines()
            if line.strip().startswith("cargo mutants ")
        )
        self.assertIn("--workspace", command)
        self.assertIn("--in-diff mutation.diff", command)
        self.assertNotIn("file_args", command)

    def test_parse_and_report_steps_do_not_report_for_windows_only(self):
        for name in (
            "Parse mutation results",
            "Comment PR with mutation results",
            "Write mutation results to step summary",
        ):
            self.assertIn("windows_only != 'true'", self.steps[name]["if"])

    def test_windows_skip_step_points_to_native_windows_check(self):
        step = self.steps["Explain Windows-only mutation skip"]
        self.assertIn("windows_only == 'true'", step["if"])
        self.assertIn("pr-checks.yml", step["run"])
        self.assertIn("test-window-background", step["run"])
        pr_checks = (ROOT / ".github/workflows/pr-checks.yml").read_text(encoding="utf-8")
        self.assertIn("runner.os == 'Windows'", pr_checks)
        self.assertIn("Test native Windows background color", pr_checks)

    def test_native_windows_recipe_keeps_locked(self):
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        recipe = next(
            line
            for line in justfile.split("test-window-background:", 1)[1].splitlines()
            if line.strip().startswith("vx cargo test")
        )
        self.assertIn("--locked", recipe)
        self.assertIn("window_background_tests", recipe)

    def test_workflow_paths_watch_the_classifier(self):
        # PyYAML (1.1) parses the bare `on:` key as boolean True.
        triggers = self.workflow.get("on", self.workflow.get(True))
        paths = triggers["pull_request"]["paths"]
        self.assertIn("scripts/ci/mutation_changed_files.py", paths)


class MutationChangedFiles(unittest.TestCase):
    def test_added_lines_maps_new_side_line_numbers(self):
        diff = (
            "diff --git a/x.rs b/x.rs\n"
            "--- a/x.rs\n"
            "+++ b/x.rs\n"
            "@@ -10,2 +10,3 @@ fn f() {\n"
            " context\n"
            "-removed\n"
            "+added at 11\n"
            "+added at 12\n"
        )
        self.assertEqual(mutation_changed_files.added_lines(diff), {"x.rs": {11, 12}})

    def test_file_level_windows_cfg_gates_the_whole_file(self):
        source = '#![cfg(target_os = "windows")]\nfn a() -> u32 { 1 }\nfn b() -> u32 { 2 }\n'
        self.assertEqual(mutation_changed_files.windows_line_ranges(source), [(1, 3)])

    def test_item_level_windows_cfg_gates_only_its_item(self):
        source = "\n".join(
            (
                "fn portable() -> u32 { 1 }",
                '#[cfg(target_os = "windows")]',
                "fn win_only() -> u32 { 2 }",
                "fn after() -> u32 { 3 }",
            )
        )
        ranges = mutation_changed_files.windows_line_ranges(source)
        self.assertIn((2, 3), ranges)
        self.assertFalse(mutation_changed_files._covers(ranges, 1))
        self.assertFalse(mutation_changed_files._covers(ranges, 4))

    def test_is_windows_only_true_for_gated_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "win.rs").write_text(
                "fn portable() -> u32 { 1 }\n"
                '#[cfg(target_os = "windows")]\n'
                "fn paint() -> u32 { 2 }\n",
                encoding="utf-8",
            )
            diff = (
                "diff --git a/win.rs b/win.rs\n"
                "--- a/win.rs\n"
                "+++ b/win.rs\n"
                "@@ -1,3 +1,3 @@\n"
                " fn portable() -> u32 { 1 }\n"
                ' #[cfg(target_os = "windows")]\n'
                "-fn paint() -> u32 { 3 }\n"
                "+fn paint() -> u32 { 2 }\n"
            )
            self.assertEqual(mutation_changed_files.added_lines(diff), {"win.rs": {3}})
            self.assertTrue(mutation_changed_files.is_windows_only(root, diff, ["win.rs"]))

    def test_is_windows_only_false_for_mixed_or_unreadable_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mix.rs").write_text(
                "fn portable() -> u32 { 1 }\nfn other() -> u32 { 2 }\n", encoding="utf-8"
            )
            mixed = (
                "diff --git a/mix.rs b/mix.rs\n"
                "--- a/mix.rs\n"
                "+++ b/mix.rs\n"
                "@@ -1,2 +1,2 @@\n"
                "-fn portable() -> u32 { 0 }\n"
                "+fn portable() -> u32 { 1 }\n"
                " fn other() -> u32 { 2 }\n"
            )
            self.assertFalse(mutation_changed_files.is_windows_only(root, mixed, ["mix.rs"]))
            missing = (
                "diff --git a/gone.rs b/gone.rs\n"
                "--- a/gone.rs\n"
                "+++ b/gone.rs\n"
                "@@ -0,0 +1 @@\n"
                "+fn new() -> u32 { 1 }\n"
            )
            # A source file that cannot be read is treated as mixed (conservative).
            self.assertFalse(mutation_changed_files.is_windows_only(root, missing, ["gone.rs"]))

    def test_main_writes_windows_only_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "win.rs").write_text(
                '#![cfg(target_os = "windows")]\nfn paint() -> u32 { 1 }\n', encoding="utf-8"
            )
            (root / "mutation.diff").write_text(
                "diff --git a/win.rs b/win.rs\n--- a/win.rs\n+++ b/win.rs\n"
                "@@ -1,2 +1,2 @@\n"
                ' #![cfg(target_os = "windows")]\n'
                "+fn paint() -> u32 { 1 }\n",
                encoding="utf-8",
            )
            (root / "changed-files.txt").write_text("win.rs\n", encoding="utf-8")
            out = root / "out.txt"
            rc = mutation_changed_files.main(
                [
                    "--diff",
                    str(root / "mutation.diff"),
                    "--files",
                    str(root / "changed-files.txt"),
                    "--root",
                    str(root),
                    "--output",
                    str(out),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertEqual(out.read_text(encoding="utf-8"), "windows_only=true\n")


if __name__ == "__main__":
    unittest.main()
