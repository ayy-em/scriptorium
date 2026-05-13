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

echo "==> Installing all optional dependencies..."
uv sync --all-extras

echo "==> Installing PyInstaller..."
uv pip install pyinstaller

echo "==> Building .app bundle..."
uv run pyinstaller packaging/scriptorium.spec --noconfirm --clean

echo ""
echo "==> Build complete: dist/Scriptorium.app"
echo ""
echo "To run on a Mac that did not build it, clear the quarantine flag:"
echo "  xattr -cr dist/Scriptorium.app"
echo ""
echo "Then double-click Scriptorium.app or run:"
echo "  open dist/Scriptorium.app"
