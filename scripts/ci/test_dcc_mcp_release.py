"""Offline publication guards; no network, tags, releases or package uploads."""

import base64
import copy
import csv
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import dcc_mcp_release as release


def source():
    return {
        release.PACKAGE
        + "/pyproject.toml": b'[project]\nname = "auroraview-dcc-mcp"\nversion = "1.2.3"\n',
        release.PACKAGE + "/python/auroraview_dcc_mcp/__init__.py": b'"""Contracts."""\n',
        release.PACKAGE + "/python/auroraview_dcc_mcp/runtime.py": b"def close():\n    pass\n",
        release.PACKAGE + "/tests/test_runtime.py": b"def test_contract():\n    assert True\n",
        release.PACKAGE + "/LICENSE": b"Fixture license\n",
        release.PACKAGE + "/README.md": b"Fixture contract package\n",
    }


def metadata(version):
    return "Metadata-Version: 2.4\nName: auroraview-dcc-mcp\nVersion: {}\n\n".format(
        version
    ).encode()


def zip_bytes(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return stream.getvalue()


def wheel(files, version="1.2.3", changed=None):
    prefix = "auroraview_dcc_mcp-{}.dist-info/".format(version)
    members = {
        name[len(release.PACKAGE + "/python/") :]: content
        for name, content in files.items()
        if name.startswith(release.PACKAGE + "/python/")
    }
    members.update(
        {
            prefix + "METADATA": metadata(version),
            prefix + "WHEEL": b"Wheel-Version: 1.0\nTag: py3-none-any\n",
            prefix + "licenses/LICENSE": files[release.PACKAGE + "/LICENSE"],
        }
    )
    if changed:
        members.update(changed)
    record = io.StringIO(newline="")
    writer = csv.writer(record)
    for name, content in members.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        writer.writerow((name, "sha256=" + digest, len(content)))
    writer.writerow((prefix + "RECORD", "", ""))
    members[prefix + "RECORD"] = record.getvalue().encode()
    return zip_bytes(members)


def sdist(files, version="1.2.3", changed=None):
    members = {name[len(release.PACKAGE) + 1 :]: content for name, content in files.items()}
    members["PKG-INFO"] = metadata(version)
    if changed:
        members.update(changed)
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, content in members.items():
            item = tarfile.TarInfo("auroraview_dcc_mcp-{}/{}".format(version, name))
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
    return stream.getvalue()


def bundle(files, wheel_data=None, sdist_data=None):
    return zip_bytes(
        {
            "auroraview_dcc_mcp-1.2.3-py3-none-any.whl": wheel_data or wheel(files),
            "auroraview_dcc_mcp-1.2.3.tar.gz": sdist_data or sdist(files),
        }
    )


def run():
    return {
        "id": 123,
        "status": "completed",
        "conclusion": "success",
        "repository": {"id": 12, "full_name": "example/project"},
        "head_repository": {"id": 12, "full_name": "example/project"},
        "workflow_id": 42,
        "path": release.WORKFLOW,
        "head_sha": "a" * 40,
    }


def artifact(data):
    return {
        "id": 456,
        "name": release.ARTIFACT,
        "expired": False,
        "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
        "workflow_run": {
            "id": 123,
            "head_sha": "a" * 40,
            "repository_id": 12,
            "head_repository_id": 12,
        },
    }


def jobs():
    return [
        {
            "id": index,
            "name": name,
            "run_id": 123,
            "head_sha": "a" * 40,
            "status": "completed",
            "conclusion": "success",
        }
        for index, name in enumerate(sorted(release.CONTRACT_JOBS | {"wheel"}), 1)
    ]


class IdentityTests(unittest.TestCase):
    def test_command_failure_retains_http_status_without_stderr_secrets(self):
        result = subprocess.CompletedProcess(
            [], 1, stdout=b"", stderr=b"credential-value; HTTP 403; private body"
        )
        with (
            patch.object(release.subprocess, "run", return_value=result),
            self.assertRaises(ValueError) as error,
        ):
            release.command("vx", "gh", "api", "endpoint")
        self.assertEqual(str(error.exception), "vx gh failed (1; HTTP 403)")

    def test_publication_inputs(self):
        release.inputs(
            "example/project",
            "123",
            "auroraview-dcc-mcp-v1.2.3-preview.2",
            "refs/heads/main",
            "b" * 40,
        )

    def test_partial_or_untrusted_inputs_fail(self):
        valid = [
            "example/project",
            "123",
            "auroraview-dcc-mcp-v1.2.3-preview.2",
            "refs/heads/main",
            "b" * 40,
        ]
        cases = (
            (0, "../project"),
            (1, ""),
            (2, ""),
            (1, "123;echo"),
            (1, "0"),
            (2, "-option"),
            (2, "auroraview-dcc-mcp-v1.2.3-preview.0"),
            (3, "refs/heads/feature"),
            (3, "refs/tags/main"),
            (4, "main"),
        )
        for index, value in cases:
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                args = valid.copy()
                args[index] = value
                release.inputs(*args)

    def test_successful_canonical_source_run(self):
        self.assertEqual(
            release.validate_run(
                run(), {"id": 42, "path": release.WORKFLOW}, "example/project", "123"
            ),
            "a" * 40,
        )

    def test_run_identity_and_success_are_required(self):
        cases = (
            ("id", 124),
            ("status", "in_progress"),
            ("conclusion", "failure"),
            ("workflow_id", 43),
            ("path", ".github/workflows/other.yml"),
            ("head_sha", "main"),
            ("repository", {"id": 12, "full_name": "other/project"}),
            ("head_repository", {"id": 13, "full_name": "example/project"}),
            ("head_repository", {"id": 12, "full_name": "fork/project"}),
            ("repository", {"full_name": "example/project"}),
        )
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                changed = run()
                changed[key] = value
                release.validate_run(
                    changed, {"id": 42, "path": release.WORKFLOW}, "example/project", "123"
                )

    def test_missing_or_wrong_canonical_workflow_is_rejected(self):
        for workflow in ({"path": release.WORKFLOW}, {"id": 42, "path": "other.yml"}):
            with self.subTest(workflow=workflow), self.assertRaises(ValueError):
                release.validate_run(run(), workflow, "example/project", "123")

    def test_single_immutable_artifact(self):
        selected = artifact(b"fixture")
        self.assertIs(
            release.select_artifact({"total_count": 1, "artifacts": [selected]}, run()), selected
        )

    def test_artifact_identity_and_digest_are_required(self):
        for key, value in (
            ("expired", True),
            ("id", 0),
            ("digest", ""),
            ("digest", "sha256:bad"),
            ("name", "other"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                changed = artifact(b"fixture")
                changed[key] = value
                release.select_artifact({"total_count": 1, "artifacts": [changed]}, run())
        for key, value in (
            ("id", 124),
            ("head_sha", "b" * 40),
            ("repository_id", 13),
            ("head_repository_id", 13),
        ):
            with self.subTest(source=key), self.assertRaises(ValueError):
                changed = artifact(b"fixture")
                changed["workflow_run"][key] = value
                release.select_artifact({"total_count": 1, "artifacts": [changed]}, run())

    def test_missing_multiple_and_truncated_artifacts_fail(self):
        selected = artifact(b"fixture")
        for listing in (
            {"total_count": 0, "artifacts": []},
            {"total_count": 2, "artifacts": [selected, copy.deepcopy(selected)]},
            {"total_count": 2, "artifacts": [selected]},
        ):
            with self.subTest(listing=listing), self.assertRaises(ValueError):
                release.select_artifact(listing, run())


class JobTests(unittest.TestCase):
    def test_all_compatibility_jobs_and_wheel_are_required(self):
        selected = release.validate_jobs(jobs(), run())
        self.assertEqual(set(selected), release.CONTRACT_JOBS | {"wheel"})

    def test_skipped_failed_or_other_commit_jobs_are_rejected(self):
        for key, value in (
            ("status", "in_progress"),
            ("conclusion", "skipped"),
            ("conclusion", "failure"),
            ("head_sha", "b" * 40),
            ("run_id", 124),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                changed = jobs()
                changed[-1][key] = value
                release.validate_jobs(changed, run())

    def test_missing_duplicate_and_unexpected_matrix_jobs_are_rejected(self):
        for changed in (
            jobs()[:-1],
            jobs() + [jobs()[0]],
            jobs() + [{"name": "contracts (other, unknown, unknown)"}],
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                release.validate_jobs(changed, run())

    def test_job_inventory_is_paginated(self):
        expected = jobs()
        with patch.object(
            release,
            "api",
            side_effect=[
                {"total_count": len(expected), "jobs": expected[:4]},
                {"total_count": len(expected), "jobs": expected[4:]},
            ],
        ) as api:
            self.assertEqual(release.source_jobs("example/project", "123"), expected)
        self.assertTrue(api.call_args_list[-1].args[1].endswith("page=2"))

    def test_truncated_changed_or_repeated_job_pages_fail(self):
        expected = jobs()
        for pages in (
            [{"total_count": 9, "jobs": expected[:4]}, {"total_count": 9, "jobs": []}],
            [{"total_count": 9, "jobs": expected[:4]}, {"total_count": 8, "jobs": expected[4:]}],
            [{"total_count": 2, "jobs": [expected[0], expected[0]]}],
            [{"total_count": 0, "jobs": []}],
        ):
            with (
                self.subTest(pages=pages),
                patch.object(release, "api", side_effect=pages),
                self.assertRaises(ValueError),
            ):
                release.source_jobs("example/project", "123")


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.files = source()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.destination = Path(self.temporary.name) / "release" / "dist"

    def unpack(self, data, digest=None):
        return release.unpack(
            data,
            digest or "sha256:" + hashlib.sha256(data).hexdigest(),
            self.files,
            "1.2.3",
            self.destination,
        )

    def test_exact_distribution_bytes_and_hashes(self):
        data = bundle(self.files)
        hashes = self.unpack(data)
        self.assertEqual(len(hashes), 2)
        for name, digest in hashes.items():
            self.assertEqual(
                hashlib.sha256((self.destination / name).read_bytes()).hexdigest(), digest
            )

    def test_wrong_download_digest_fails_before_writing(self):
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.unpack(bundle(self.files), "sha256:" + "0" * 64)
        self.assertFalse(self.destination.exists())

    def test_unexpected_or_unsafe_artifact_members_fail(self):
        for data in (zip_bytes({"../escape.whl": b"bad"}), zip_bytes({"notes.txt": b"bad"})):
            with (
                self.subTest(data=data[:10]),
                self.assertRaisesRegex(ValueError, "artifact members"),
            ):
                self.unpack(data)
        self.assertFalse(self.destination.exists())

    def test_changed_wheel_source_fails_even_with_valid_record(self):
        changed = wheel(self.files, changed={"auroraview_dcc_mcp/runtime.py": b"changed"})
        with self.assertRaisesRegex(ValueError, "Wheel source mismatch"):
            self.unpack(bundle(self.files, wheel_data=changed))
        self.assertFalse(self.destination.exists())

    def test_unexpected_wheel_code_fails(self):
        changed = wheel(self.files, changed={"unexpected.py": b"pass"})
        with self.assertRaisesRegex(ValueError, "wheel members"):
            self.unpack(bundle(self.files, wheel_data=changed))

    def test_wheel_metadata_and_record_must_match(self):
        for member, content, message in (
            ("METADATA", metadata("9.9.9"), "metadata mismatch"),
            ("WHEEL", b"tampered after RECORD", "RECORD content mismatch"),
        ):
            with self.subTest(member=member):
                with zipfile.ZipFile(io.BytesIO(wheel(self.files))) as archive:
                    members = {name: archive.read(name) for name in archive.namelist()}
                members["auroraview_dcc_mcp-1.2.3.dist-info/" + member] = content
                with self.assertRaisesRegex(ValueError, message):
                    self.unpack(bundle(self.files, wheel_data=zip_bytes(members)))
        self.assertFalse(self.destination.exists())

    def test_changed_sdist_and_metadata_fail_before_writing(self):
        for changed, message in (
            ({"tests/test_runtime.py": b"changed"}, "Sdist source mismatch"),
            ({"PKG-INFO": metadata("9.9.9")}, "metadata mismatch"),
            ({"../escape": b"bad"}, "Sdist source mismatch"),
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, message):
                self.unpack(bundle(self.files, sdist_data=sdist(self.files, changed=changed)))
        self.assertFalse(self.destination.exists())

    def test_missing_package_module_fails(self):
        files = self.files.copy()
        del files[release.PACKAGE + "/python/auroraview_dcc_mcp/runtime.py"]
        with self.assertRaisesRegex(ValueError, "modules are missing"):
            self.unpack(bundle(self.files, sdist_data=sdist(files)))

    def test_existing_output_is_never_replaced(self):
        self.destination.mkdir(parents=True)
        marker = self.destination / "marker"
        marker.write_text("keep")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.unpack(bundle(self.files))
        self.assertEqual(marker.read_text(), "keep")


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        release.git(self.root, "init", "--quiet")
        release.git(self.root, "config", "user.name", "loonghao")
        release.git(self.root, "config", "user.email", "hal.long@outlook.com")
        files = source() | {release.INPUTS[1]: b"check wheel\n", release.WORKFLOW: b"workflow\n"}
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.source = self.commit()
        self.git = release.git

    def commit(self):
        release.git(self.root, "add", ".")
        release.git(self.root, "commit", "--quiet", "-m", "chore: publication fixture")
        return release.git(self.root, "rev-parse", "HEAD").decode().strip()

    def validate(self, publication):
        def local_git(root, *args):
            if args[:1] == ("fetch",):
                self.assertEqual(args, ("fetch", "--no-tags", "origin", self.source))
                return b""
            return self.git(root, *args)

        with patch.object(release, "git", side_effect=local_git):
            return release.validate_source(self.root, self.source, publication)

    def test_workflow_only_changes_can_reuse_verified_package(self):
        (self.root / release.WORKFLOW).write_text("new guarded workflow\n")
        files, version = self.validate(self.commit())
        self.assertEqual(files, source())
        self.assertEqual(version, "1.2.3")

    def test_package_tests_and_checker_changes_require_a_new_source_run(self):
        for name in (
            release.PACKAGE + "/python/auroraview_dcc_mcp/runtime.py",
            release.PACKAGE + "/tests/test_runtime.py",
            release.INPUTS[1],
        ):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b"changed\n")
                with self.assertRaises(ValueError):
                    self.validate(self.commit())
                path.write_bytes(original)
                self.commit()

    def test_checkout_must_be_the_publication_commit(self):
        with self.assertRaisesRegex(ValueError, "publication commit"):
            self.validate("b" * 40)


class PreparationTests(unittest.TestCase):
    def test_receipt_checksums_and_packages_are_separate(self):
        files = source()
        data = bundle(files)
        selected = artifact(data)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            outputs = Path(directory) / "outputs"

            def download(*args, output=None, cwd=None):
                self.assertEqual(cwd, Path.home())
                self.assertEqual(
                    args,
                    (
                        "vx",
                        "gh",
                        "api",
                        "--hostname",
                        "github.com",
                        "repos/example/project/actions/artifacts/456/zip",
                    ),
                )
                output.write(data)

            with (
                patch.object(
                    release,
                    "api",
                    side_effect=[
                        {"id": 42, "path": release.WORKFLOW},
                        run(),
                        {"total_count": len(jobs()), "jobs": jobs()},
                        {"total_count": 1, "artifacts": [selected]},
                    ],
                ) as api,
                patch.object(release, "validate_source", return_value=(files, "1.2.3")),
                patch.object(release, "command", side_effect=download),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(outputs)}),
                redirect_stdout(io.StringIO()),
            ):
                receipt = release.prepare(
                    "example/project",
                    "123",
                    "auroraview-dcc-mcp-v1.2.3-preview.2",
                    "refs/heads/main",
                    "b" * 40,
                    Path(directory),
                    output,
                )
            self.assertEqual(
                api.call_args_list[-1].args[1], "actions/runs/123/artifacts?per_page=100"
            )
            self.assertEqual({item.suffix for item in (output / "dist").iterdir()}, {".whl", ".gz"})
            self.assertEqual(json.loads((output / "publication.json").read_text()), receipt)
            self.assertEqual(receipt["artifact_id"], selected["id"])
            self.assertEqual(receipt["artifact_digest"], selected["digest"])
            for name, digest in receipt["files"].items():
                self.assertIn("{}  {}\n".format(digest, name), (output / "SHA256SUMS").read_text())
            self.assertIn("#sha256=", (output / "notes.md").read_text())
            self.assertNotIn(directory, (output / "notes.md").read_text())
            self.assertIn("release-tag=auroraview-dcc-mcp-v1.2.3-preview.2\n", outputs.read_text())

    def test_tag_version_mismatch_stops_before_download(self):
        with (
            patch.object(
                release,
                "api",
                side_effect=[
                    {"id": 42, "path": release.WORKFLOW},
                    run(),
                    {"total_count": len(jobs()), "jobs": jobs()},
                ],
            ),
            patch.object(release, "validate_source", return_value=(source(), "1.2.3")),
            patch.object(release, "command") as download,
            self.assertRaisesRegex(ValueError, "Tag version"),
        ):
            release.prepare(
                "example/project",
                "123",
                "auroraview-dcc-mcp-v9.9.9-preview.2",
                "refs/heads/main",
                "b" * 40,
                Path("unused"),
                Path("unused"),
            )
        download.assert_not_called()


class PypiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        (self.output / "dist").mkdir()
        self.files = {
            "auroraview_dcc_mcp-1.2.3-py3-none-any.whl": b"selected wheel",
            "auroraview_dcc_mcp-1.2.3.tar.gz": b"selected sdist",
        }
        for name, data in self.files.items():
            (self.output / "dist" / name).write_bytes(data)
        self.receipt = {
            "repository": "example/project",
            "publication_commit": "b" * 40,
            "source_run_id": 123,
            "release_tag": "auroraview-dcc-mcp-v1.2.3-preview.2",
            "version": "1.2.3",
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in self.files.items()},
        }
        self.save_receipt()

    def save_receipt(self):
        (self.output / "publication.json").write_text(json.dumps(self.receipt), encoding="utf-8")

    def metadata(self, names=None):
        return {
            "info": {"name": "auroraview-dcc-mcp", "version": "1.2.3"},
            "urls": [
                {"filename": name, "digests": {"sha256": self.receipt["files"][name]}}
                for name in (self.files if names is None else names)
            ],
        }

    def check(self, metadata, complete=False):
        with patch.object(release, "pypi", return_value=metadata), redirect_stdout(io.StringIO()):
            return release.check_pypi(
                self.output, complete, "example/project", "refs/heads/main", "b" * 40
            )

    def test_absent_version_is_allowed_only_before_upload(self):
        self.assertEqual(self.check(None)["verified_files"], {})
        with self.assertRaisesRegex(ValueError, "missing selected"):
            self.check(None, complete=True)

    def test_same_public_bytes_allow_upload_retry_and_readback(self):
        for complete in (False, True):
            with self.subTest(complete=complete):
                self.assertEqual(
                    self.check(self.metadata(), complete)["verified_files"], self.receipt["files"]
                )

    def test_partial_upload_can_resume_but_is_not_complete(self):
        names = [next(iter(self.files))]
        metadata = self.metadata(names)
        self.assertEqual(set(self.check(metadata)["verified_files"]), set(names))
        with self.assertRaisesRegex(ValueError, "missing selected"):
            self.check(metadata, complete=True)

    def test_conflicting_public_hash_fails_before_and_after_upload(self):
        metadata = self.metadata()
        metadata["urls"][0]["digests"]["sha256"] = "0" * 64
        for complete in (False, True):
            with (
                self.subTest(complete=complete),
                self.assertRaisesRegex(ValueError, "conflicts with frozen"),
            ):
                self.check(metadata, complete)

    def test_missing_or_repeated_public_hash_is_rejected(self):
        missing = self.metadata()
        missing["urls"][0]["digests"] = {}
        repeated = self.metadata()
        repeated["urls"].append(repeated["urls"][0])
        for metadata in (missing, repeated):
            with (
                self.subTest(metadata=metadata),
                self.assertRaisesRegex(ValueError, "conflicts with frozen"),
            ):
                self.check(metadata)

    def test_public_project_and_version_identity_must_match(self):
        for field, value in (("name", "other-project"), ("version", "9.9.9")):
            metadata = self.metadata()
            metadata["info"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "identity mismatch"):
                self.check(metadata)

    def test_changed_local_bytes_stop_before_registry_lookup(self):
        (self.output / "dist" / next(iter(self.files))).write_bytes(b"changed")
        with (
            patch.object(release, "pypi") as lookup,
            self.assertRaisesRegex(ValueError, "differs from frozen"),
        ):
            release.check_pypi(self.output, False, "example/project", "refs/heads/main", "b" * 40)
        lookup.assert_not_called()

    def test_foreign_receipt_identity_stops_before_registry_lookup(self):
        for field, value in (("repository", "other/project"), ("publication_commit", "c" * 40)):
            with self.subTest(field=field):
                receipt = self.receipt.copy()
                receipt[field] = value
                (self.output / "publication.json").write_text(json.dumps(receipt))
                with (
                    patch.object(release, "pypi") as lookup,
                    self.assertRaisesRegex(ValueError, "workflow identity"),
                ):
                    release.check_pypi(
                        self.output, False, "example/project", "refs/heads/main", "b" * 40
                    )
                lookup.assert_not_called()

    def test_extra_local_files_and_unsafe_receipt_names_are_rejected(self):
        extra = self.output / "dist" / "notes.txt"
        extra.write_bytes(b"unexpected")
        with self.assertRaisesRegex(ValueError, "Unexpected local"):
            self.check(None)
        extra.unlink()
        self.receipt["files"]["../escape.whl"] = "0" * 64
        self.save_receipt()
        with self.assertRaisesRegex(ValueError, "Unexpected receipt"):
            self.check(None)

    def test_official_404_is_the_only_allowed_http_absence(self):
        for code in (404, 403, 429, 500):
            error = HTTPError(
                "https://pypi.org/pypi/auroraview-dcc-mcp/1.2.3/json", code, "fixture", None, None
            )
            with (
                self.subTest(code=code),
                patch.object(release, "urlopen", side_effect=error) as lookup,
            ):
                if code == 404:
                    self.assertIsNone(release.pypi("1.2.3"))
                else:
                    with self.assertRaisesRegex(ValueError, "HTTP {}".format(code)):
                        release.pypi("1.2.3")
                lookup.assert_called_once_with(
                    "https://pypi.org/pypi/auroraview-dcc-mcp/1.2.3/json", timeout=30
                )

    def test_network_or_invalid_json_never_means_absent(self):
        with (
            patch.object(release, "urlopen", side_effect=URLError("private proxy detail")),
            self.assertRaisesRegex(ValueError, "Official PyPI lookup failed") as error,
        ):
            release.pypi("1.2.3")
        self.assertNotIn("private", str(error.exception))
        with (
            patch.object(release, "urlopen", return_value=io.BytesIO(b"invalid JSON")),
            self.assertRaisesRegex(ValueError, "Official PyPI lookup failed"),
        ):
            release.pypi("1.2.3")

    def test_official_json_is_read_without_credentials(self):
        with patch.object(
            release, "urlopen", return_value=io.BytesIO(json.dumps(self.metadata()).encode())
        ):
            self.assertEqual(release.pypi("1.2.3"), self.metadata())


if __name__ == "__main__":
    unittest.main()
