#!/usr/bin/env bash
# Build the Scriptorium Linux binary.
#
# Prerequisites:
#   uv (https://docs.astral.sh/uv/getting-started/installation/)
#
# Usage:
#   cd /path/to/scriptorium
#   bash packaging/build_linux.sh
#
# Output:
#   dist/scriptorium/           — standalone directory
#   dist/scriptorium-linux-x86_64.tar.gz  — distributable tarball

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
echo "Scriptorium build — Linux — target: scriptorium-linux-x86_64.tar.gz"
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

step "Analysing & building Linux binary"
echo "    Spec:      packaging/scriptorium-linux.spec"
echo "    Output:    dist/scriptorium/"
echo "    Log level: INFO"
echo ""
uv run pyinstaller packaging/scriptorium-linux.spec \
    --noconfirm \
    --clean \
    --log-level INFO

step "Creating distributable tarball"
echo "    Creating: dist/scriptorium-linux-x86_64.tar.gz"
tar -czf dist/scriptorium-linux-x86_64.tar.gz -C dist scriptorium
SIZE="$(du -sh dist/scriptorium-linux-x86_64.tar.gz 2>/dev/null | cut -f1)"
echo "    Done. Size: $SIZE"

finish_step

echo ""
echo "========================================"
echo "  BUILD COMPLETE  ($(elapsed))"
echo "  Directory: dist/scriptorium/"
echo "  Tarball:   dist/scriptorium-linux-x86_64.tar.gz  ($SIZE)"
echo "========================================"
echo ""
echo "To run:"
echo "  ./dist/scriptorium/scriptorium"
