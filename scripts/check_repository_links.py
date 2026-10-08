"""Check live repository links and package provenance without build dependencies."""

import json
import re
import sys
from pathlib import Path
from typing import Iterator, List

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "try-auroraview/auroraview"
REPOSITORY_URL = "https://github.com/" + REPOSITORY
FORMER_REPOSITORY = "/".join(("loonghao", "auroraview"))
FORMER_PAGES = "loonghao.github.io/" + "auroraview"
STALE_LINK = re.compile(
    "(?:"
    + re.escape(FORMER_REPOSITORY)
    + "|"
    + re.escape(FORMER_PAGES)
    + ")"
    + r"(?=$|[^\w.-]|\.git(?![\w.-]))"
)
SOURCE_DIRECTORIES = (
    ".github",
    "crates",
    "docs",
    "examples",
    "gallery",
    "packages",
    "python",
    "scripts",
    "src",
    "tests",
)
SOURCE_SUFFIXES = {
    ".md",
    ".mdc",
    ".txt",
    ".toml",
    ".json",
    ".ts",
    ".tsx",
    ".py",
    ".rs",
    ".ps1",
    ".sh",
    ".yml",
    ".yaml",
}
GENERATED_DIRECTORIES = {"node_modules", "target", "dist", ".venv", ".ruff_cache", "__pycache__"}


def active_files() -> Iterator[Path]:
    """Exclude release history, design history, and generated dependencies."""
    for path in sorted(ROOT.iterdir()):
        if (
            path.is_file()
            and path.suffix in SOURCE_SUFFIXES
            and not path.name.startswith("CHANGELOG")
        ):
            yield path
    for directory in SOURCE_DIRECTORIES:
        for path in sorted((ROOT / directory).rglob("*")):
            relative = path.relative_to(ROOT)
            if (
                not path.is_file()
                or path.suffix not in SOURCE_SUFFIXES
                or path.name.startswith("CHANGELOG")
                or GENERATED_DIRECTORIES.intersection(relative.parts)
                or relative.as_posix().startswith(("docs/rfcs/", "docs/reviews/"))
            ):
                continue
            yield path


def toml_string(path: str, section: str, key: str) -> str:
    """Read a simple quoted metadata field while keeping Python 3.7 support."""
    content = (ROOT / path).read_text(encoding="utf-8")
    table = re.search(r"(?ms)^\[" + re.escape(section) + r"\]\s*\n(.*?)(?=^\[|\Z)", content)
    if table:
        value = re.search(r"(?m)^" + re.escape(key) + r'\s*=\s*"([^"]+)"', table.group(1))
        if value:
            return value.group(1)
    raise ValueError("Missing {}.{} in {}".format(section, key, path))


def check() -> List[str]:
    errors = []  # type: List[str]
    sdk = json.loads((ROOT / "packages/auroraview-sdk/package.json").read_text(encoding="utf-8"))
    metadata = (
        ("Python package name", toml_string("pyproject.toml", "project", "name"), "auroraview"),
        (
            "Python extension module",
            toml_string("pyproject.toml", "tool.maturin", "module-name"),
            "auroraview._core",
        ),
        ("Cargo package name", toml_string("Cargo.toml", "package", "name"), "auroraview"),
        (
            "Cargo repository",
            toml_string("Cargo.toml", "workspace.package", "repository"),
            REPOSITORY_URL,
        ),
        ("SDK package name", sdk["name"], "@auroraview/sdk"),
        ("SDK repository", sdk["repository"]["url"], "git+" + REPOSITORY_URL + ".git"),
    )
    for label, actual, expected in metadata:
        if actual != expected:
            errors.append("{}: expected {!r}, got {!r}".format(label, expected, actual))
    for key, suffix in (
        ("Homepage", ""),
        ("Documentation", "#readme"),
        ("Repository", ""),
        ("Issues", "/issues"),
    ):
        if toml_string("pyproject.toml", "project.urls", key) != REPOSITORY_URL + suffix:
            errors.append(
                "Python project.urls.{} does not use the canonical repository".format(key)
            )
    for path, pattern in (
        ("scripts/install.sh", r'^REPO="([^"]+)"'),
        ("scripts/install.ps1", r'^\$Repo = "([^"]+)"'),
        ("crates/auroraview-cli/src/cli/self_update.rs", r'^const GITHUB_REPO: &str = "([^"]+)";'),
    ):
        match = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"), re.MULTILINE)
        if not match or match.group(1) != REPOSITORY:
            errors.append("{} does not resolve releases from the canonical repository".format(path))
    for path in active_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # Codecov has a separate external service binding; transfer it only after verification.
            line = re.sub(r'https://codecov\.io/[^\s"\'<>]+', "", line)
            if STALE_LINK.search(line):
                errors.append(
                    "{}:{} uses a former live repository link".format(
                        path.relative_to(ROOT).as_posix(), number
                    )
                )
    return errors


def main() -> int:
    errors = check()
    if errors:
        print("Repository link validation failed:", file=sys.stderr)
        for error in errors:
            print("- " + error, file=sys.stderr)
        return 1
    print("Repository links and package identities use " + REPOSITORY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
