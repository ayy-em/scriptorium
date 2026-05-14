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

set NODE_OPTIONS=--no-deprecation

cd /d "%~dp0.."

echo Initiating build. Target artifact: ScriptoriumSetup.exe
echo.

echo ==^> [1/5] Checking prerequisites...
where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv not found on PATH.
    echo Install uv from: https://docs.astral.sh/uv/
    exit /b 1
)
echo     uv found
where iscc >nul 2>&1
if errorlevel 1 (
    echo ERROR: Inno Setup compiler ^(iscc^) not found on PATH.
    echo.
    echo Install Inno Setup 6+ from: https://jrsoftware.org/issetup.php
    echo Then ensure the install directory is on your PATH.
    exit /b 1
)
echo     iscc found

echo.
echo ==^> [2/5] Installing dependencies (uv sync --all-extras)...
uv sync --all-extras || exit /b 1

echo.
echo ==^> [3/5] Cleaning previous build artifacts...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
echo     Done.

echo.
echo ==^> [4/5] Building application bundle (this may take a while)...
uv pip install pyinstaller || exit /b 1
uv run pyinstaller packaging/scriptorium-win.spec --noconfirm --clean || exit /b 1

echo.
echo ==^> [5/5] Building installer (Inno Setup)...
iscc packaging\installer.iss || exit /b 1

echo.
echo ========================================
echo   BUILD COMPLETE
echo   Output: dist\ScriptoriumSetup.exe
echo ========================================
