@echo off
rem Build the Scriptorium Windows installer payload.
rem
rem Prerequisites:
rem   - Python 3.14 (via uv or standalone)
rem   - uv (https://docs.astral.sh/uv/)
rem
rem Usage:
rem   packaging\build.bat
rem
rem Output:
rem   dist\scriptorium\scriptorium.exe   (folder bundle)

setlocal
cd /d "%~dp0.."

echo ==^> Installing all optional dependencies...
uv sync --all-extras || exit /b 1

echo ==^> Installing PyInstaller...
uv pip install pyinstaller || exit /b 1

echo ==^> Building folder bundle...
uv run pyinstaller packaging/scriptorium-win.spec --noconfirm --clean || exit /b 1

echo.
echo ==^> Build complete: dist\scriptorium\scriptorium.exe
echo.
echo To build the Inno Setup installer, run:
echo   iscc packaging\installer.iss
