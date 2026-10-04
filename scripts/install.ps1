# AuroraView CLI Install Script for Windows PowerShell
# Usage: irm https://raw.githubusercontent.com/try-auroraview/auroraview/main/scripts/install.ps1 | iex
# Or: Invoke-WebRequest -Uri https://raw.githubusercontent.com/try-auroraview/auroraview/main/scripts/install.ps1 -UseBasicParsing | Invoke-Expression

$ErrorActionPreference = "Stop"

# Configuration
$Repo = "try-auroraview/auroraview"
$BinaryName = "auroraview-cli"
$InstallDir = if ($env:AURORAVIEW_INSTALL_DIR) { $env:AURORAVIEW_INSTALL_DIR } else { "$env:USERPROFILE\.auroraview\bin" }

# Print functions
function Write-Info { Write-Host "[INFO] $args" -ForegroundColor Blue }
function Write-Success { Write-Host "[OK] $args" -ForegroundColor Green }
function Write-Warn { Write-Host "[WARN] $args" -ForegroundColor Yellow }
function Write-Error-Exit { Write-Host "[ERROR] $args" -ForegroundColor Red; exit 1 }

# Detect architecture
function Get-Platform {
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    
    switch ($arch) {
        "X64" {
            $script:Platform = "windows-x64"
            $script:Target = "x86_64-pc-windows-msvc"
        }
        "Arm64" {
            # Note: ARM64 Windows is not currently supported, fallback to x64 emulation
            Write-Warn "ARM64 Windows detected. Using x64 binary (runs via emulation)."
            $script:Platform = "windows-x64"
            $script:Target = "x86_64-pc-windows-msvc"
        }
        default {
            Write-Error-Exit "Unsupported architecture: $arch"
        }
    }
    
    Write-Info "Detected platform: $Platform ($Target)"
}

# Get latest version from GitHub API
function Get-LatestVersion {
    Write-Info "Fetching latest version..."
    
    $apiUrl = "https://api.github.com/repos/$Repo/releases/latest"
    
    try {
        $response = Invoke-RestMethod -Uri $apiUrl -UseBasicParsing
        $script:Version = $response.tag_name
        $script:VersionNum = $Version -replace "auroraview-v", ""
        
        Write-Success "Latest version: $VersionNum"
    }
    catch {
        Write-Error-Exit "Failed to get latest version: $_"
    }
}

# Download and extract binary
function Install-Binary {
    $downloadUrl = "https://github.com/$Repo/releases/download/$Version/$BinaryName-$VersionNum-$Target.zip"
    $tempDir = Join-Path $env:TEMP "auroraview-install-$(Get-Random)"
    $archiveFile = Join-Path $tempDir "$BinaryName.zip"
    
    Write-Info "Downloading from: $downloadUrl"
    
    try {
        # Create temp directory
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
        
        # Download
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $downloadUrl -OutFile $archiveFile -UseBasicParsing
        
        Write-Success "Downloaded successfully"
        
        # Create install directory
        if (-not (Test-Path $InstallDir)) {
            New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        }
        
        # Extract
        Write-Info "Extracting..."
        Expand-Archive -Path $archiveFile -DestinationPath $tempDir -Force
        
        # Find and move binary
        $binaryPath = Get-ChildItem -Path $tempDir -Filter "$BinaryName.exe" -Recurse | Select-Object -First 1
        
        if ($binaryPath) {
            $destPath = Join-Path $InstallDir "$BinaryName.exe"
            Move-Item -Path $binaryPath.FullName -Destination $destPath -Force
            Write-Success "Installed to: $InstallDir"
        }
        else {
            Write-Error-Exit "Binary not found in archive"
        }
    }
    catch {
        Write-Error-Exit "Installation failed: $_"
    }
    finally {
        # Cleanup
        if (Test-Path $tempDir) {
            Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

# Add to PATH
function Add-ToPath {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    
    if ($currentPath -notlike "*$InstallDir*") {
        Write-Info "Adding $InstallDir to user PATH..."
        
        $newPath = "$currentPath;$InstallDir"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        
        # Also update current session
        $env:Path = "$env:Path;$InstallDir"
        
        Write-Success "Added to PATH"
        Write-Warn "Please restart your terminal for PATH changes to take effect."
    }
    else {
        Write-Info "Already in PATH"
    }
}

# Verify installation
function Test-Installation {
    $binaryPath = Join-Path $InstallDir "$BinaryName.exe"
    
    if (Test-Path $binaryPath) {
        Write-Info "Verifying installation..."
        
        try {
            $version = & $binaryPath --version
            Write-Success "Verification successful! $version"
        }
        catch {
            Write-Warn "Could not verify installation: $_"
        }
    }
    else {
        Write-Error-Exit "Installation verification failed"
    }
}

# Main
function Main {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║           AuroraView CLI Installer                           ║" -ForegroundColor Cyan
    Write-Host "║           https://github.com/try-auroraview/auroraview             ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    
    Get-Platform
    Get-LatestVersion
    Install-Binary
    Add-ToPath
    Test-Installation
    
    Write-Host ""
    Write-Success "Installation complete!"
    Write-Host ""
    Write-Info "Get started with:"
    Write-Host "  auroraview-cli --help"
    Write-Host "  auroraview-cli --url https://example.com"
    Write-Host ""
}

Main
