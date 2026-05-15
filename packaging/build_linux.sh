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

echo "[1/5] Installing all optional dependencies..."
uv sync --all-extras

echo "[2/5] Cleaning previous build artifacts..."
rm -rf dist/ build/

echo "[3/5] Installing PyInstaller..."
uv pip install pyinstaller

echo "[4/5] Building Linux binary..."
uv run pyinstaller packaging/scriptorium-linux.spec --noconfirm --clean

echo "[5/5] Creating tarball..."
tar -czf dist/scriptorium-linux-x86_64.tar.gz -C dist scriptorium

echo ""
echo "==> Build complete"
echo "    Directory: dist/scriptorium/"
echo "    Tarball:   dist/scriptorium-linux-x86_64.tar.gz"
echo ""
echo "To run:"
echo "  ./dist/scriptorium/scriptorium"
