#!/usr/bin/env bash
# Unified build entrypoint for Scriptorium.
# Detects the OS and runs the appropriate build pipeline.
#
# Usage:
#   bash build.sh
#
# macOS output:  dist/Scriptorium.app
# Windows output: dist/ScriptoriumSetup.exe  (requires Git Bash)

set -euo pipefail
cd "$(dirname "$0")"

ensure_uv() {
    if command -v uv &>/dev/null; then
        echo "==> uv found: $(uv --version)"
        return
    fi
    echo "==> uv not found, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "==> uv installed: $(uv --version)"
}

build_macos() {
    ensure_uv

    echo "==> Installing all optional dependencies..."
    uv sync --all-extras

    if ! command -v brew &>/dev/null; then
        echo "==> Homebrew not found, installing..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)"
    fi

    if ! command -v ffmpeg &>/dev/null; then
        echo "==> Installing ffmpeg via Homebrew..."
        brew install ffmpeg
    else
        echo "==> ffmpeg found: $(ffmpeg -version | head -1)"
    fi

    echo "==> Cleaning previous build artifacts..."
    rm -rf dist/ build/

    echo "==> Installing PyInstaller..."
    uv pip install pyinstaller

    echo "==> Building .app bundle..."
    uv run pyinstaller packaging/scriptorium.spec --noconfirm --clean

    echo ""
    echo "==> Build complete: dist/Scriptorium.app"
    echo ""
    echo "To run on a Mac that did not build it, clear the quarantine flag:"
    echo "  xattr -cr dist/Scriptorium.app"
}

build_windows() {
    ensure_uv

    if ! command -v iscc &>/dev/null && ! command -v iscc.exe &>/dev/null; then
        echo "ERROR: Inno Setup compiler (iscc) not found on PATH."
        echo ""
        echo "Install Inno Setup 6+ from: https://jrsoftware.org/issetup.php"
        echo "Then ensure the install directory is on your PATH."
        exit 1
    fi

    echo "==> Delegating to packaging/build_installer.bat..."
    cmd.exe //c "packaging\\build_installer.bat"
}

OS="$(uname -s)"
case "$OS" in
    Darwin)
        echo "==> Detected macOS"
        build_macos
        ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT)
        echo "==> Detected Windows"
        build_windows
        ;;
    *)
        echo "ERROR: Unsupported OS: $OS"
        exit 1
        ;;
esac
