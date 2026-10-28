"""Offline checks for crates.io publish preconditions."""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLISHABLE = (
    "auroraview-contract",
    "auroraview-extensions",
    "auroraview-protect",
    "auroraview-pack",
)
EXCLUDED = PUBLISHABLE + ("auroraview-ue",)


def manifest(crate: str) -> str:
    return (REPO_ROOT / "crates" / crate / "Cargo.toml").read_text(encoding="utf-8")


class PublishPreflightTests(unittest.TestCase):
    def test_publishable_manifest_has_no_workspace_hack(self) -> None:
        for crate in PUBLISHABLE:
            with self.subTest(crate=crate):
                self.assertNotIn("auroraview-workspace-hack", manifest(crate))

    def test_hakari_excludes_publishable_crates(self) -> None:
        config = (REPO_ROOT / ".config" / "hakari.toml").read_text(encoding="utf-8")
        for crate in EXCLUDED:
            with self.subTest(crate=crate):
                self.assertIn(f'"{crate}"', config)

    def test_pack_keeps_path_dependencies_until_publication(self) -> None:
        pack = manifest("auroraview-pack")
        for crate in ("auroraview-protect", "auroraview-extensions"):
            with self.subTest(crate=crate):
                self.assertIn(f'{crate} = {{ path = "../{crate}"', pack)
