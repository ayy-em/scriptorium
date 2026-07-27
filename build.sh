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
STEP_START="$SECONDS"

# Print a step header and emit the previous step's duration.
step() {
    local now
    now=$(date '+%H:%M:%S')
    if [ "$STEP" -gt 0 ]; then
        local secs=$(( SECONDS - STEP_START ))
        printf "    └─ done in %dm%02ds\n" $((secs / 60)) $((secs % 60))
    fi
    STEP=$((STEP + 1))
    STEP_START="$SECONDS"
    echo ""
    echo "==> [$STEP] [$now] $1"
}

# Emit the current step's duration (call at the very end of the last step).
finish_step() {
    local secs=$(( SECONDS - STEP_START ))
    printf "    └─ done in %dm%02ds\n" $((secs / 60)) $((secs % 60))
}

elapsed() {
    local secs=$(( SECONDS - BUILD_START ))
    printf "%dm%02ds" $((secs / 60)) $((secs % 60))
}

ensure_uv() {
    if command -v uv &>/dev/null; then
        echo "    uv:     $(uv --version)"
        return
    fi
    echo "    uv not found — installing via astral.sh..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "    uv:     $(uv --version)"
}

print_env_info() {
    echo "    OS:     $(uname -srm)"
    echo "    Shell:  bash $BASH_VERSION"
    echo "    Dir:    $(pwd)"
    echo "    Python: $(uv run python --version 2>/dev/null || python3 --version 2>/dev/null || echo 'not detected')"
}

# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

build_macos() {
    step "Checking prerequisites"
    ensure_uv
    print_env_info

    if ! command -v brew &>/dev/null; then
        echo "    Homebrew not found — installing..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)"
        echo "    brew:   $(brew --version | head -1)"
    else
        echo "    brew:   $(brew --version | head -1)"
    fi

    if ! command -v ffmpeg &>/dev/null; then
        echo "    ffmpeg not found — installing via Homebrew..."
        brew install ffmpeg
        echo "    ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
    else
        echo "    ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
    fi

    step "Installing Python dependencies"
    echo "    Running: uv sync --all-extras"
    echo ""
    uv sync --all-extras

    step "Cleaning previous build artifacts"
    echo "    Removing: dist/  build/"
    rm -rf dist/ build/
    echo "    Clean."

    step "Installing PyInstaller"
    uv pip install pyinstaller
    echo "    PyInstaller: $(uv run pyinstaller --version 2>/dev/null)"

    step "Analysing & building .app bundle"
    echo "    Spec:      packaging/scriptorium.spec"
    echo "    Output:    dist/Scriptorium.app"
    echo "    Log level: INFO"
    echo ""
    uv run pyinstaller packaging/scriptorium.spec \
        --noconfirm \
        --clean \
        --log-level INFO

    finish_step

    SIZE=""
    if [ -d "dist/Scriptorium.app" ]; then
        SIZE="  ($(du -sh dist/Scriptorium.app 2>/dev/null | cut -f1))"
    fi

    echo ""
    echo "========================================"
    echo "  BUILD COMPLETE  ($(elapsed))"
    echo "  Output: dist/Scriptorium.app$SIZE"
    echo "========================================"
    echo ""
    echo "To run on a Mac that did not build it, clear the quarantine flag:"
    echo "  xattr -cr dist/Scriptorium.app"
}

# ---------------------------------------------------------------------------
# Windows — Git Bash / MSYS2 / Cygwin
# ---------------------------------------------------------------------------

build_windows() {
    step "Checking prerequisites"
    ensure_uv
    print_env_info

    if ! command -v iscc &>/dev/null && ! command -v iscc.exe &>/dev/null; then
        echo ""
        echo "ERROR: Inno Setup compiler (iscc) not found on PATH."
        echo ""
        echo "Install Inno Setup 6+ from: https://jrsoftware.org/issetup.php"
        echo "Then ensure its install directory is on your PATH."
        exit 1
    fi
    echo "    iscc:   found"

    step "Running packaging/build_installer.bat"
    echo "    Sub-step output from the .bat pipeline follows:"
    echo ""
    cmd.exe //c "packaging\\build_installer.bat"

    finish_step

    SIZE=""
    if [ -f "dist/ScriptoriumSetup.exe" ]; then
        SIZE="  ($(du -sh dist/ScriptoriumSetup.exe 2>/dev/null | cut -f1))"
    fi

    echo ""
    echo "========================================"
    echo "  BUILD COMPLETE  ($(elapsed))"
    echo "  Output: dist/ScriptoriumSetup.exe$SIZE"
    echo "========================================"
}

# ---------------------------------------------------------------------------
# Windows — WSL
# ---------------------------------------------------------------------------

build_windows_wsl() {
    step "Checking prerequisites"
    ensure_uv
    print_env_info

    local win_root
    win_root="$(wslpath -w "$(pwd)")"
    echo "    Windows path: $win_root"

    step "Running packaging\\build_installer.bat via cmd.exe"
    echo "    Sub-step output from the .bat pipeline follows:"
    echo ""
    cmd.exe /c "cd /d \"${win_root}\" && packaging\\build_installer.bat"

    finish_step

    echo ""
    echo "========================================"
    echo "  BUILD COMPLETE  ($(elapsed))"
    echo "  Output: dist\\ScriptoriumSetup.exe"
    echo "========================================"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

OS="$(uname -s)"
case "$OS" in
    Darwin)
        echo ""
        echo "Scriptorium build — macOS — target: Scriptorium.app"
        echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
        build_macos
        ;;
    Linux)
        if grep -qi microsoft /proc/version 2>/dev/null; then
            echo ""
            echo "Scriptorium build — Windows (WSL) — target: ScriptoriumSetup.exe"
            echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
            build_windows_wsl
        else
            echo "ERROR: Native Linux builds use packaging/build_linux.sh, not this script."
            exit 1
        fi
        ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT)
        echo ""
        echo "Scriptorium build — Windows (Git Bash) — target: ScriptoriumSetup.exe"
        echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
        build_windows
        ;;
    *)
        echo "ERROR: Unsupported OS: $OS"
        exit 1
        ;;
esac
