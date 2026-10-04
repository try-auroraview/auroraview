"""Tests for CLI install scripts.

This module tests the install scripts for auroraview-cli.
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent


class TestInstallScriptSyntax:
    """Test install script syntax and structure."""

    def test_bash_script_exists(self):
        """Test that install.sh exists."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        assert script_path.exists(), f"install.sh not found at {script_path}"

    def test_powershell_script_exists(self):
        """Test that install.ps1 exists."""
        script_path = PROJECT_ROOT / "scripts" / "install.ps1"
        assert script_path.exists(), f"install.ps1 not found at {script_path}"

    def test_bash_script_has_shebang(self):
        """Test that install.sh has proper shebang."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert content.startswith("#!/bin/bash"), "install.sh should start with #!/bin/bash"

    def test_bash_script_has_set_e(self):
        """Test that install.sh has set -e for error handling."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "set -e" in content, "install.sh should have 'set -e' for error handling"

    def test_powershell_script_has_error_action(self):
        """Test that install.ps1 has ErrorActionPreference."""
        script_path = PROJECT_ROOT / "scripts" / "install.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert '$ErrorActionPreference = "Stop"' in content, (
            "install.ps1 should have ErrorActionPreference = Stop"
        )

    def test_bash_script_has_repo_config(self):
        """Test that install.sh has correct repo configuration."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert 'REPO="try-auroraview/auroraview"' in content, "install.sh should have correct repo"
        assert 'BINARY_NAME="auroraview-cli"' in content, (
            "install.sh should have correct binary name"
        )

    def test_powershell_script_has_repo_config(self):
        """Test that install.ps1 has correct repo configuration."""
        script_path = PROJECT_ROOT / "scripts" / "install.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert '$Repo = "try-auroraview/auroraview"' in content, (
            "install.ps1 should have correct repo"
        )
        assert '$BinaryName = "auroraview-cli"' in content, (
            "install.ps1 should have correct binary name"
        )


class TestInstallScriptPlatformDetection:
    """Test platform detection logic in scripts."""

    def test_bash_detects_linux(self):
        """Test that bash script can detect Linux."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "Linux*)" in content and 'os="linux"' in content

    def test_bash_detects_macos(self):
        """Test that bash script can detect macOS."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "Darwin*)" in content and 'os="macos"' in content

    def test_bash_detects_x64(self):
        """Test that bash script can detect x86_64 architecture."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "x86_64|amd64)" in content and 'arch="x64"' in content

    def test_bash_detects_arm64(self):
        """Test that bash script can detect ARM64 architecture."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "arm64|aarch64)" in content and 'arch="arm64"' in content


class TestInstallScriptTargetTriples:
    """Test that scripts use correct Rust target triples."""

    def test_bash_has_windows_target(self):
        """Test Windows target triple."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "x86_64-pc-windows-msvc" in content

    def test_bash_has_linux_target(self):
        """Test Linux target triple."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "x86_64-unknown-linux-gnu" in content

    def test_bash_has_macos_x64_target(self):
        """Test macOS x64 target triple."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "x86_64-apple-darwin" in content

    def test_bash_has_macos_arm64_target(self):
        """Test macOS ARM64 target triple."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "aarch64-apple-darwin" in content

    def test_powershell_has_windows_target(self):
        """Test Windows target triple in PowerShell script."""
        script_path = PROJECT_ROOT / "scripts" / "install.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "x86_64-pc-windows-msvc" in content


class TestInstallScriptDownloadUrls:
    """Test download URL construction in scripts."""

    def test_bash_constructs_github_url(self):
        """Test that bash script constructs correct GitHub release URL."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "https://github.com/${REPO}/releases/download" in content
        assert "${VERSION}" in content
        assert "${BINARY_NAME}" in content
        assert "${TARGET}" in content

    def test_powershell_constructs_github_url(self):
        """Test that PowerShell script constructs correct GitHub release URL."""
        script_path = PROJECT_ROOT / "scripts" / "install.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "https://github.com/$Repo/releases/download" in content


class TestInstallScriptPathHandling:
    """Test PATH handling in scripts."""

    def test_bash_has_default_install_dir(self):
        """Test that bash script has default install directory."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "$HOME/.auroraview/bin" in content

    def test_bash_supports_custom_install_dir(self):
        """Test that bash script supports custom install directory."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "AURORAVIEW_INSTALL_DIR" in content

    def test_powershell_has_default_install_dir(self):
        """Test that PowerShell script has default install directory."""
        script_path = PROJECT_ROOT / "scripts" / "install.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert ".auroraview\\bin" in content or ".auroraview/bin" in content

    def test_powershell_supports_custom_install_dir(self):
        """Test that PowerShell script supports custom install directory."""
        script_path = PROJECT_ROOT / "scripts" / "install.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "AURORAVIEW_INSTALL_DIR" in content


class TestInstallScriptVerification:
    """Test installation verification in scripts."""

    def test_bash_verifies_installation(self):
        """Test that bash script verifies installation."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"
        content = script_path.read_text(encoding="utf-8")
        assert "--version" in content
        assert "verify" in content.lower() or "Verif" in content

    def test_powershell_verifies_installation(self):
        """Test that PowerShell script verifies installation."""
        script_path = PROJECT_ROOT / "scripts" / "install.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "--version" in content
        assert "Verif" in content


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
class TestPowerShellScriptExecution:
    """Test PowerShell script can be parsed (Windows only)."""

    def test_powershell_syntax_check(self):
        """Test that PowerShell script has valid syntax."""
        script_path = PROJECT_ROOT / "scripts" / "install.ps1"

        # Use PowerShell to check syntax without executing
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$null = [System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$errors); $errors.Count",
            ],
            capture_output=True,
            text=True,
        )

        # If there are no syntax errors, the output should be "0"
        assert result.returncode == 0, f"PowerShell syntax check failed: {result.stderr}"
        error_count = result.stdout.strip()
        assert error_count == "0", f"PowerShell script has syntax errors: {result.stderr}"


@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
class TestBashScriptExecution:
    """Test bash script can be parsed (Unix only)."""

    def test_bash_syntax_check(self):
        """Test that bash script has valid syntax."""
        script_path = PROJECT_ROOT / "scripts" / "install.sh"

        # Use bash -n to check syntax without executing
        result = subprocess.run(
            ["bash", "-n", str(script_path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Bash syntax check failed: {result.stderr}"
