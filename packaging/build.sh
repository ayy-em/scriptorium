#!/usr/bin/env bash
# Build the Scriptorium macOS .app bundle.
#
# Prerequisites:
#   brew install python@3.14    (or use uv python install 3.14)
#   uv pip install pyinstaller
#   uv sync --all-extras        (install all optional deps into the venv)
#
# Usage:
#   cd /path/to/scriptorium
#   bash packaging/build.sh
#
# Output:
#   dist/Scriptorium.app

set -euo pipefail
cd "$(dirname "$0")/.."

BUILD_START="$SECONDS"
STEP=0
STEP_START="$SECONDS"

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

finish_step() {
    local secs=$(( SECONDS - STEP_START ))
    printf "    └─ done in %dm%02ds\n" $((secs / 60)) $((secs % 60))
}

elapsed() {
    local secs=$(( SECONDS - BUILD_START ))
    printf "%dm%02ds" $((secs / 60)) $((secs % 60))
}

echo ""
echo "Scriptorium build — macOS — target: Scriptorium.app"
echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"

step "Environment"
echo "    OS:     $(uname -srm)"
echo "    Python: $(python3 --version 2>/dev/null || echo 'not detected')"
echo "    uv:     $(uv --version 2>/dev/null || echo 'not found')"
echo "    Dir:    $(pwd)"

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
echo ""
echo "Then double-click Scriptorium.app or:"
echo "  open dist/Scriptorium.app"
