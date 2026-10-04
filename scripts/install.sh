#!/bin/bash
# AuroraView CLI Install Script
# Usage: curl -fsSL https://raw.githubusercontent.com/try-auroraview/auroraview/main/scripts/install.sh | bash
# Or: wget -qO- https://raw.githubusercontent.com/try-auroraview/auroraview/main/scripts/install.sh | bash

set -e

# Configuration
REPO="try-auroraview/auroraview"
BINARY_NAME="auroraview-cli"
INSTALL_DIR="${AURORAVIEW_INSTALL_DIR:-$HOME/.auroraview/bin}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Detect OS and architecture
detect_platform() {
    local os arch

    case "$(uname -s)" in
        Linux*)  os="linux" ;;
        Darwin*) os="macos" ;;
        CYGWIN*|MINGW*|MSYS*) os="windows" ;;
        *) error "Unsupported operating system: $(uname -s)" ;;
    esac

    case "$(uname -m)" in
        x86_64|amd64) arch="x64" ;;
        arm64|aarch64) arch="arm64" ;;
        *) error "Unsupported architecture: $(uname -m)" ;;
    esac

    # macOS arm64 check
    if [ "$os" = "macos" ] && [ "$arch" = "arm64" ]; then
        PLATFORM="macos-arm64"
        TARGET="aarch64-apple-darwin"
        EXT="tar.gz"
    elif [ "$os" = "macos" ] && [ "$arch" = "x64" ]; then
        PLATFORM="macos-x64"
        TARGET="x86_64-apple-darwin"
        EXT="tar.gz"
    elif [ "$os" = "linux" ] && [ "$arch" = "x64" ]; then
        PLATFORM="linux-x64"
        TARGET="x86_64-unknown-linux-gnu"
        EXT="tar.gz"
    elif [ "$os" = "windows" ]; then
        PLATFORM="windows-x64"
        TARGET="x86_64-pc-windows-msvc"
        EXT="zip"
    else
        error "Unsupported platform: $os-$arch"
    fi

    info "Detected platform: $PLATFORM ($TARGET)"
}

# Get latest version from GitHub API
get_latest_version() {
    info "Fetching latest version..."
    
    local api_url="https://api.github.com/repos/${REPO}/releases/latest"
    local response
    
    if command -v curl &> /dev/null; then
        response=$(curl -sL "$api_url")
    elif command -v wget &> /dev/null; then
        response=$(wget -qO- "$api_url")
    else
        error "Neither curl nor wget found. Please install one of them."
    fi
    
    # Extract tag_name from JSON response
    VERSION=$(echo "$response" | grep -o '"tag_name": *"[^"]*"' | head -1 | cut -d'"' -f4)
    
    if [ -z "$VERSION" ]; then
        error "Failed to get latest version. API response: $response"
    fi
    
    # Extract version number (auroraview-v0.3.8 -> 0.3.8)
    VERSION_NUM=$(echo "$VERSION" | sed 's/auroraview-v//')
    
    success "Latest version: $VERSION_NUM"
}

# Download and extract binary
download_and_install() {
    local download_url="https://github.com/${REPO}/releases/download/${VERSION}/${BINARY_NAME}-${VERSION_NUM}-${TARGET}.${EXT}"
    local tmp_dir=$(mktemp -d)
    local archive_file="${tmp_dir}/${BINARY_NAME}.${EXT}"
    
    info "Downloading from: $download_url"
    
    # Download
    if command -v curl &> /dev/null; then
        curl -fsSL "$download_url" -o "$archive_file" || error "Download failed"
    else
        wget -q "$download_url" -O "$archive_file" || error "Download failed"
    fi
    
    success "Downloaded successfully"
    
    # Create install directory
    mkdir -p "$INSTALL_DIR"
    
    # Extract
    info "Extracting..."
    if [ "$EXT" = "tar.gz" ]; then
        tar -xzf "$archive_file" -C "$tmp_dir"
    elif [ "$EXT" = "zip" ]; then
        if command -v unzip &> /dev/null; then
            unzip -q "$archive_file" -d "$tmp_dir"
        else
            error "unzip not found. Please install it."
        fi
    fi
    
    # Find and move binary
    local binary_path
    if [ "$PLATFORM" = "windows-x64" ]; then
        binary_path=$(find "$tmp_dir" -name "${BINARY_NAME}.exe" -type f | head -1)
        if [ -n "$binary_path" ]; then
            mv "$binary_path" "${INSTALL_DIR}/${BINARY_NAME}.exe"
            chmod +x "${INSTALL_DIR}/${BINARY_NAME}.exe"
        fi
    else
        binary_path=$(find "$tmp_dir" -name "${BINARY_NAME}" -type f | head -1)
        if [ -n "$binary_path" ]; then
            mv "$binary_path" "${INSTALL_DIR}/${BINARY_NAME}"
            chmod +x "${INSTALL_DIR}/${BINARY_NAME}"
        fi
    fi
    
    if [ -z "$binary_path" ]; then
        error "Binary not found in archive"
    fi
    
    # Cleanup
    rm -rf "$tmp_dir"
    
    success "Installed to: $INSTALL_DIR"
}

# Add to PATH instructions
show_path_instructions() {
    local shell_config=""
    local shell_name=""
    
    case "$SHELL" in
        */bash)
            shell_config="$HOME/.bashrc"
            shell_name="bash"
            ;;
        */zsh)
            shell_config="$HOME/.zshrc"
            shell_name="zsh"
            ;;
        */fish)
            shell_config="$HOME/.config/fish/config.fish"
            shell_name="fish"
            ;;
        *)
            shell_config="$HOME/.profile"
            shell_name="shell"
            ;;
    esac
    
    # Check if already in PATH
    if echo "$PATH" | grep -q "$INSTALL_DIR"; then
        success "Installation complete! auroraview-cli is ready to use."
    else
        echo ""
        warn "Add the following to your $shell_config to add auroraview-cli to PATH:"
        echo ""
        if [ "$shell_name" = "fish" ]; then
            echo "  fish_add_path $INSTALL_DIR"
        else
            echo "  export PATH=\"\$PATH:$INSTALL_DIR\""
        fi
        echo ""
        info "Then restart your terminal or run:"
        if [ "$shell_name" = "fish" ]; then
            echo "  source $shell_config"
        else
            echo "  source $shell_config"
        fi
        echo ""
    fi
}

# Verify installation
verify_installation() {
    local binary_path
    if [ "$PLATFORM" = "windows-x64" ]; then
        binary_path="${INSTALL_DIR}/${BINARY_NAME}.exe"
    else
        binary_path="${INSTALL_DIR}/${BINARY_NAME}"
    fi
    
    if [ -x "$binary_path" ]; then
        info "Verifying installation..."
        "$binary_path" --version && success "Verification successful!"
    else
        error "Installation verification failed"
    fi
}

# Main
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           AuroraView CLI Installer                           ║"
    echo "║           https://github.com/try-auroraview/auroraview             ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    
    detect_platform
    get_latest_version
    download_and_install
    verify_installation
    show_path_instructions
    
    echo ""
    success "Installation complete!"
    echo ""
    info "Get started with:"
    echo "  auroraview-cli --help"
    echo "  auroraview-cli --url https://example.com"
    echo ""
}

main "$@"
