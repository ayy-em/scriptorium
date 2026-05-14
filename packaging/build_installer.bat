@echo off
rem Build the Scriptorium Windows installer from source.
rem
rem Prerequisites:
rem   - Python 3.14 (via uv or standalone)
rem   - uv (https://docs.astral.sh/uv/)
rem   - Inno Setup 6+ with iscc on PATH (https://jrsoftware.org/issetup.php)
rem
rem Usage:
rem   packaging\build_installer.bat
rem
rem Output:
rem   dist\ScriptoriumSetup.exe

setlocal
cd /d "%~dp0.."

echo ==^> Installing all optional dependencies...
uv sync --all-extras || exit /b 1

echo ==^> Installing PyInstaller...
uv pip install pyinstaller || exit /b 1

echo ==^> Building folder bundle...
uv run pyinstaller packaging/scriptorium-win.spec --noconfirm --clean || exit /b 1

echo ==^> Building installer...
iscc packaging\installer.iss || exit /b 1

echo.
echo ==^> Build complete: dist\ScriptoriumSetup.exe
