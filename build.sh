#!/usr/bin/env bash
# Unified build entrypoint for Scriptorium.
# Detects the OS and runs the appropriate build pipeline.
#
# Usage:
#   bash build.sh
#
# macOS output:  dist/Scriptorium.app
# Windows output: dist/ScriptoriumSetup.exe  (Git Bash, WSL, or MSYS2)

set -euo pipefail
cd "$(dirname "$0")"

export NODE_OPTIONS="--no-deprecation"

BUILD_START="$SECONDS"
STEP=0

step() {
    STEP=$((STEP + 1))
    echo ""
    echo "==> [$STEP] $1"
}

elapsed() {
    local secs=$(( SECONDS - BUILD_START ))
    printf "%dm%02ds" $((secs / 60)) $((secs % 60))
}

ensure_uv() {
    if command -v uv &>/dev/null; then
        echo "    uv found: $(uv --version)"
        return
    fi
    echo "    uv not found, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "    uv installed: $(uv --version)"
}

build_macos() {
    step "Checking prerequisites"
    ensure_uv

    if ! command -v brew &>/dev/null; then
        echo "    Homebrew not found, installing..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)"
    fi

    if ! command -v ffmpeg &>/dev/null; then
        echo "    Installing ffmpeg via Homebrew..."
        brew install ffmpeg
    else
        echo "    ffmpeg found: $(ffmpeg -version | head -1)"
    fi

    step "Installing dependencies (uv sync --all-extras)"
    uv sync --all-extras

    step "Cleaning previous build artifacts"
    rm -rf dist/ build/

    step "Installing PyInstaller"
    uv pip install pyinstaller

    step "Building .app bundle (this may take a while)"
    uv run pyinstaller packaging/scriptorium.spec --noconfirm --clean

    echo ""
    echo "========================================"
    echo "  BUILD COMPLETE  ($(elapsed))"
    echo "  Output: dist/Scriptorium.app"
    echo "========================================"
    echo ""
    echo "To run on a Mac that did not build it, clear the quarantine flag:"
    echo "  xattr -cr dist/Scriptorium.app"
}

build_windows() {
    step "Checking prerequisites"
    ensure_uv

    if ! command -v iscc &>/dev/null && ! command -v iscc.exe &>/dev/null; then
        echo "ERROR: Inno Setup compiler (iscc) not found on PATH."
        echo ""
        echo "Install Inno Setup 6+ from: https://jrsoftware.org/issetup.php"
        echo "Then ensure the install directory is on your PATH."
        exit 1
    fi
    echo "    iscc found"

    step "Running packaging/build_installer.bat"
    cmd.exe //c "packaging\\build_installer.bat"

    echo ""
    echo "========================================"
    echo "  BUILD COMPLETE  ($(elapsed))"
    echo "  Output: dist/ScriptoriumSetup.exe"
    echo "========================================"
}

build_windows_wsl() {
    local win_root
    win_root="$(wslpath -w "$(pwd)")"
    echo "    Windows path: $win_root"

    echo ""
    echo "==> Running packaging\\build_installer.bat via cmd.exe"
    cmd.exe /c "cd /d \"${win_root}\" && packaging\\build_installer.bat"

    echo ""
    echo "========================================"
    echo "  BUILD COMPLETE  ($(elapsed))"
    echo "  Output: dist\\ScriptoriumSetup.exe"
    echo "========================================"
}

OS="$(uname -s)"
case "$OS" in
    Darwin)
        echo "Initiating build. System detected: macOS. Target artifact: Scriptorium.app"
        build_macos
        ;;
    Linux)
        if grep -qi microsoft /proc/version 2>/dev/null; then
            echo "Initiating build. System detected: Windows (WSL). Target artifact: ScriptoriumSetup.exe"
            build_windows_wsl
        else
            echo "ERROR: Native Linux is not supported."
            exit 1
        fi
        ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT)
        echo "Initiating build. System detected: Windows. Target artifact: ScriptoriumSetup.exe"
        build_windows
        ;;
    *)
        echo "ERROR: Unsupported OS: $OS"
        exit 1
        ;;
esac
