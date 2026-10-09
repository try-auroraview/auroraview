"""Reuse a verified contract distribution without rebuilding it (Python 3.11+)."""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

PACKAGE = "packages/auroraview-dcc-mcp"
WORKFLOW = ".github/workflows/dcc-mcp-contracts.yml"
ARTIFACT = "auroraview-dcc-mcp-python"
INPUTS = (PACKAGE, "scripts/ci/check_dcc_mcp_wheel.py")
CONTRACT_JOBS = {
    "contracts ({}, {}, {})".format(system, python, core)
    for system in ("ubuntu-latest", "windows-latest")
    for python in ("3.7", "3.11")
    for core in ("0.20.25", "0.20.41")
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(*args, cwd=None, output=None):
    result = subprocess.run(
        args,
        cwd=cwd,
        stdout=output if output is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    if result.returncode:
        tool = " ".join(args[:2]) if args[0] == "vx" else args[0]
        status = re.search(rb"HTTP [0-9]{3}", result.stderr)
        detail = "; " + status[0].decode() if status else ""
        raise ValueError("{} failed ({}{})".format(tool, result.returncode, detail))
    return result.stdout


def api(repository, endpoint):
    return json.loads(
        command(
            "vx",
            "gh",
            "api",
            "--hostname",
            "github.com",
            "repos/{}/{}".format(repository, endpoint),
            cwd=Path.home(),
        )
    )


def inputs(repository, run_id, tag, ref, commit):
    require(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]*", repository),
        "Invalid repository",
    )
    require(run_id and tag, "source-run-id and release-tag must both be supplied")
    require(re.fullmatch(r"[1-9][0-9]*", run_id), "Invalid source run ID")
    require(ref == "refs/heads/main", "Manual publication must run from main")
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Invalid publication commit")
    require(
        re.fullmatch(r"auroraview-dcc-mcp-v[0-9]+\.[0-9]+\.[0-9]+-preview\.[1-9][0-9]*", tag),
        "A unique auroraview-dcc-mcp preview tag is required",
    )


def validate_run(run, workflow, repository, run_id):
    require(run.get("id") == int(run_id), "Source run ID mismatch")
    require(
        run.get("status") == "completed" and run.get("conclusion") == "success",
        "Source run is not successful",
    )
    for field in ("repository", "head_repository"):
        require(
            (run.get(field) or {}).get("full_name") == repository, "Source run repository mismatch"
        )
    repository_id = (run.get("repository") or {}).get("id")
    require(type(repository_id) is int and repository_id > 0, "Invalid source repository ID")
    require(
        (run.get("head_repository") or {}).get("id") == repository_id,
        "Source head repository ID mismatch",
    )
    require(type(workflow.get("id")) is int and workflow["id"] > 0, "Invalid source workflow ID")
    require(run.get("workflow_id") == workflow.get("id"), "Source workflow ID mismatch")
    require(
        workflow.get("path") == WORKFLOW and run.get("path") == WORKFLOW,
        "Source workflow path mismatch",
    )
    require(re.fullmatch(r"[0-9a-f]{40}", run.get("head_sha", "")), "Invalid source commit")
    return run["head_sha"]


def select_artifact(listing, run):
    artifacts = listing.get("artifacts", [])
    require(listing.get("total_count") == len(artifacts), "Artifact listing is incomplete")
    matches = [artifact for artifact in artifacts if artifact.get("name") == ARTIFACT]
    require(len(matches) == 1, "Exactly one contract artifact is required")
    artifact = matches[0]
    require(artifact.get("expired") is False, "Source artifact has expired")
    require(type(artifact.get("id")) is int and artifact["id"] > 0, "Invalid artifact ID")
    source = artifact.get("workflow_run") or {}
    require(
        source.get("id") == run["id"] and source.get("head_sha") == run["head_sha"],
        "Artifact source mismatch",
    )
    repository_id = run["repository"]["id"]
    require(
        source.get("repository_id") == repository_id
        and source.get("head_repository_id") == repository_id,
        "Artifact repository mismatch",
    )
    require(
        re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest", "")),
        "Artifact SHA256 digest is required",
    )
    return artifact


def source_jobs(repository, run_id):
    jobs = []
    total = None
    page = 1
    while total is None or len(jobs) < total:
        listing = api(
            repository,
            "actions/runs/{}/jobs?filter=latest&per_page=100&page={}".format(run_id, page),
        )
        count = listing.get("total_count")
        batch = listing.get("jobs")
        require(type(count) is int and 0 < count <= 10000, "Invalid source job count")
        require(total is None or count == total, "Source job inventory changed during pagination")
        require(isinstance(batch, list) and batch, "Source job listing is incomplete")
        total = count
        jobs.extend(batch)
        require(len(jobs) <= total, "Source job listing exceeds its declared count")
        page += 1
    ids = [job.get("id") for job in jobs]
    require(
        all(type(value) is int and value > 0 for value in ids) and len(set(ids)) == len(ids),
        "Invalid or repeated source jobs",
    )
    return jobs


def validate_jobs(jobs, run):
    required = CONTRACT_JOBS | {"wheel"}
    selected = [job for job in jobs if job.get("name") in required]
    require(
        len(selected) == len(required) and {job["name"] for job in selected} == required,
        "Source contract matrix or wheel job is missing or duplicated",
    )
    require(
        {job.get("name") for job in jobs if job.get("name", "").startswith("contracts (")}
        == CONTRACT_JOBS,
        "Unexpected source contract matrix",
    )
    for job in selected:
        require(
            job.get("run_id") == run["id"] and job.get("head_sha") == run["head_sha"],
            "Source job identity mismatch",
        )
        require(
            job.get("status") == "completed" and job.get("conclusion") == "success",
            "Source contract or wheel job did not succeed",
        )
    return {job["name"]: job["id"] for job in selected}


def git(root, *args):
    return command("vx", "git", "-C", str(root), *args, cwd=Path.home())


def source_files(root, commit, prefix):
    names = git(root, "ls-tree", "-r", "--name-only", commit, "--", prefix).decode().splitlines()
    return {name: git(root, "show", "{}:{}".format(commit, name)) for name in names}


def validate_source(root, source, publication):
    require(
        git(root, "rev-parse", "HEAD").decode().strip() == publication,
        "Checkout is not the publication commit",
    )
    # Fetch only the validated commit ID, never a caller-controlled refspec.
    git(root, "fetch", "--no-tags", "origin", source)
    try:
        git(root, "diff", "--exit-code", source, publication, "--", *INPUTS)
    except ValueError:
        raise ValueError("Package, tests or checker differ from the verified source") from None
    files = source_files(root, publication, PACKAGE)
    project = tomllib.loads(files[PACKAGE + "/pyproject.toml"].decode())["project"]
    require(project["name"] == "auroraview-dcc-mcp", "Unexpected project name")
    require(
        re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", project["version"]), "Unexpected project version"
    )
    return files, project["version"]


def validate_wheel(data, files, version):
    import base64

    dist_info = "auroraview_dcc_mcp-{}.dist-info/".format(version)
    expected = {
        name[len(PACKAGE + "/python/") :]: content
        for name, content in files.items()
        if name.startswith(PACKAGE + "/python/")
    }
    with zipfile.ZipFile(io.BytesIO(data)) as wheel:
        members = wheel.namelist()
        allowed = set(expected) | {
            dist_info + name for name in ("METADATA", "WHEEL", "RECORD", "licenses/LICENSE")
        }
        require(
            len(members) == len(set(members)) and set(members) == allowed,
            "Unexpected wheel members",
        )
        for name, content in expected.items():
            require(wheel.read(name) == content, "Wheel source mismatch: " + name)
        require(
            wheel.read(dist_info + "licenses/LICENSE") == files[PACKAGE + "/LICENSE"],
            "Wheel license mismatch",
        )
        metadata = BytesParser().parsebytes(wheel.read(dist_info + "METADATA"))
        require(
            metadata["Name"] == "auroraview-dcc-mcp" and metadata["Version"] == version,
            "Wheel metadata mismatch",
        )
        records = list(csv.reader(io.StringIO(wheel.read(dist_info + "RECORD").decode())))
        require(
            len(records) == len(members) and {row[0] for row in records} == set(members),
            "Wheel RECORD mismatch",
        )
        for name, digest, size in records:
            if name == dist_info + "RECORD":
                require(digest == size == "", "Invalid self RECORD entry")
                continue
            content = wheel.read(name)
            expected_digest = (
                "sha256="
                + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
            )
            require(
                digest == expected_digest and size == str(len(content)),
                "Wheel RECORD content mismatch",
            )


def validate_sdist(data, files, version):
    prefix = "auroraview_dcc_mcp-{}/".format(version)
    found = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive:
            require(member.name.startswith(prefix), "Unexpected sdist root")
            relative = member.name[len(prefix) :]
            if member.isdir():
                require(".." not in Path(relative).parts, "Unsafe sdist directory")
                continue
            require(member.isfile() and relative not in found, "Unexpected sdist member")
            found.add(relative)
            content = archive.extractfile(member).read()
            if relative == "PKG-INFO":
                metadata = BytesParser().parsebytes(content)
                require(
                    metadata["Name"] == "auroraview-dcc-mcp" and metadata["Version"] == version,
                    "Sdist metadata mismatch",
                )
            else:
                require(
                    files.get(PACKAGE + "/" + relative) == content,
                    "Sdist source mismatch: " + relative,
                )
    require("PKG-INFO" in found and "pyproject.toml" in found, "Incomplete source distribution")
    require(
        all(
            name[len(PACKAGE) + 1 :] in found
            for name in files
            if name.startswith(PACKAGE + "/python/")
        ),
        "Sdist package modules are missing",
    )


def unpack(archive, digest, files, version, destination):
    require(
        hashlib.sha256(archive).hexdigest() == digest.removeprefix("sha256:"),
        "Downloaded artifact digest mismatch",
    )
    wheel_name = "auroraview_dcc_mcp-{}-py3-none-any.whl".format(version)
    sdist_name = "auroraview_dcc_mcp-{}.tar.gz".format(version)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        require(
            sorted(bundle.namelist()) == sorted([wheel_name, sdist_name]),
            "Unexpected artifact members",
        )
        payloads = {name: bundle.read(name) for name in (wheel_name, sdist_name)}
    validate_wheel(payloads[wheel_name], files, version)
    validate_sdist(payloads[sdist_name], files, version)
    require(not destination.exists(), "Release output directory already exists")
    destination.mkdir(parents=True)
    for name, content in payloads.items():
        (destination / name).write_bytes(content)
    return {name: hashlib.sha256(content).hexdigest() for name, content in payloads.items()}


def prepare(repository, run_id, tag, ref, publication, root, output):
    inputs(repository, run_id, tag, ref, publication)
    workflow = api(repository, "actions/workflows/dcc-mcp-contracts.yml")
    run = api(repository, "actions/runs/" + run_id)
    source = validate_run(run, workflow, repository, run_id)
    verified_jobs = validate_jobs(source_jobs(repository, run_id), run)
    print(
        "Verified source run {} at {} with {} successful required jobs".format(
            run_id, source, len(verified_jobs)
        )
    )
    files, version = validate_source(root, source, publication)
    print("Verified equivalent package, tests and wheel checker inputs")
    require(
        tag.startswith("auroraview-dcc-mcp-v{}-preview.".format(version)),
        "Tag version differs from package metadata",
    )
    listing = api(repository, "actions/runs/{}/artifacts?per_page=100".format(run_id))
    artifact = select_artifact(listing, run)
    print("Selected artifact {} ({})".format(artifact["id"], artifact["digest"]))
    with tempfile.TemporaryFile() as downloaded:
        command(
            "vx",
            "gh",
            "api",
            "--hostname",
            "github.com",
            "repos/{}/actions/artifacts/{}/zip".format(repository, artifact["id"]),
            output=downloaded,
            cwd=Path.home(),
        )
        downloaded.seek(0)
        hashes = unpack(downloaded.read(), artifact["digest"], files, version, output / "dist")
    receipt = {
        "repository": repository,
        "source_workflow": WORKFLOW,
        "source_run_id": int(run_id),
        "source_commit": source,
        "verified_jobs": verified_jobs,
        "publication_commit": publication,
        "release_tag": tag,
        "artifact_id": artifact["id"],
        "artifact_digest": artifact["digest"],
        "equivalent_inputs": list(INPUTS),
        "version": version,
        "files": hashes,
    }
    (output / "publication.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text(
        "".join("{}  {}\n".format(digest, name) for name, digest in hashes.items()),
        encoding="utf-8",
    )
    wheel = next(name for name in hashes if name.endswith(".whl"))
    url = "https://github.com/{}/releases/download/{}/{}".format(repository, tag, wheel)
    notes = (
        "Independent Python contract preview, package version `{}`.\n\n"
        "Reuses verified [source run {}](https://github.com/{}/actions/runs/{}) "
        "without rebuilding. Source commit `{}`; publication commit `{}`. "
        "See `publication.json` and `SHA256SUMS` for provenance.\n\n"
        "Install the pinned wheel:\n\n"
        "```sh\nvx uv pip install --python <host-python> "
        '"auroraview-dcc-mcp @ {}#sha256={}"\n```\n\n'
        "Add the optional Core dependency by using `auroraview-dcc-mcp[core]` in that command.\n\n"
        "Public package consumption does not establish native host or GUI acceptance.\n"
    ).format(version, run_id, repository, run_id, source, publication, url, hashes[wheel])
    (output / "notes.md").write_text(notes, encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as outputs:
            outputs.write(
                "release-tag={}\nsource-commit={}\nartifact-id={}\n".format(
                    tag, source, artifact["id"]
                )
            )
    print(json.dumps(receipt, indent=2))
    return receipt


def pypi(version):
    url = "https://pypi.org/pypi/auroraview-dcc-mcp/{}/json".format(version)
    try:
        with urlopen(url, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise ValueError("Official PyPI lookup failed: HTTP {}".format(error.code)) from None
    except (URLError, ValueError):
        raise ValueError("Official PyPI lookup failed") from None


def check_pypi(output, complete, repository, ref, publication):
    receipt = json.loads((output / "publication.json").read_text(encoding="utf-8"))
    require(
        receipt.get("repository") == repository
        and receipt.get("publication_commit") == publication,
        "Publication receipt differs from workflow identity",
    )
    inputs(
        repository,
        str(receipt.get("source_run_id", "")),
        receipt.get("release_tag", ""),
        ref,
        publication,
    )
    version = receipt.get("version", "")
    require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "Invalid receipt version")
    require(
        receipt["release_tag"].startswith("auroraview-dcc-mcp-v{}-preview.".format(version)),
        "Receipt tag version mismatch",
    )
    expected = receipt.get("files") or {}
    names = {
        "auroraview_dcc_mcp-{}-py3-none-any.whl".format(version),
        "auroraview_dcc_mcp-{}.tar.gz".format(version),
    }
    require(set(expected) == names, "Unexpected receipt distribution names")
    require(
        {path.name for path in (output / "dist").iterdir()} == names,
        "Unexpected local distributions",
    )
    for name, digest in expected.items():
        require(re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid receipt distribution hash")
        require(
            hashlib.sha256((output / "dist" / name).read_bytes()).hexdigest() == digest,
            "Local distribution differs from frozen receipt",
        )
    metadata = pypi(version)
    found = {}
    if metadata is not None:
        info = metadata.get("info") or {}
        require(
            info.get("name") == "auroraview-dcc-mcp" and info.get("version") == version,
            "Official PyPI package identity mismatch",
        )
        require(
            isinstance(metadata.get("urls"), list), "Official PyPI distribution list is missing"
        )
        for entry in metadata["urls"]:
            name = entry.get("filename")
            if name in expected:
                digest = (entry.get("digests") or {}).get("sha256")
                require(
                    name not in found and digest == expected[name],
                    "Official PyPI distribution conflicts with frozen receipt",
                )
                found[name] = digest
    require(not complete or set(found) == names, "Official PyPI is missing selected distributions")
    result = {"version": version, "complete": complete, "verified_files": found}
    print(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run-id", default=os.environ.get("SOURCE_RUN_ID", ""))
    parser.add_argument("--release-tag", default=os.environ.get("RELEASE_TAG", ""))
    parser.add_argument("--output", type=Path, default=Path("release"))
    parser.add_argument("--check-pypi", choices=("before", "after"))
    args = parser.parse_args()
    if args.check_pypi:
        check_pypi(
            args.output,
            args.check_pypi == "after",
            os.environ.get("GITHUB_REPOSITORY", ""),
            os.environ.get("GITHUB_REF", ""),
            os.environ.get("GITHUB_SHA", ""),
        )
        return
    prepare(
        os.environ.get("GITHUB_REPOSITORY", ""),
        args.source_run_id,
        args.release_tag,
        os.environ.get("GITHUB_REF", ""),
        os.environ.get("GITHUB_SHA", ""),
        Path(__file__).resolve().parents[2],
        args.output,
    )


if __name__ == "__main__":
    main()
