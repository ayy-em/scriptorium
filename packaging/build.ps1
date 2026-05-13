# Build the Scriptorium Windows installer payload.
#
# Prerequisites:
#   - Python 3.14 (via uv or standalone)
#   - uv (https://docs.astral.sh/uv/)
#
# Usage:
#   cd D:\Python\scriptorium
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#
# Output:
#   dist\scriptorium\scriptorium.exe   (folder bundle)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "==> Installing all optional dependencies..."
uv sync --all-extras

Write-Host "==> Installing PyInstaller..."
uv pip install pyinstaller

Write-Host "==> Building folder bundle..."
uv run pyinstaller packaging/scriptorium-win.spec --noconfirm --clean

Write-Host ""
Write-Host "==> Build complete: dist\scriptorium\scriptorium.exe"
Write-Host ""
Write-Host "To build the Inno Setup installer, open packaging\installer.iss"
Write-Host "in Inno Setup Compiler (iscc) and compile, or run:"
Write-Host "  iscc packaging\installer.iss"
