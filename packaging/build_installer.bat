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

echo.
echo Scriptorium build ^| Windows ^| target: ScriptoriumSetup.exe
echo Started: %DATE% %TIME%
echo.

echo ==^> [1/5] [%TIME%] Checking prerequisites...
where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv not found on PATH.
    echo Install uv from: https://docs.astral.sh/uv/
    exit /b 1
)
for /f "tokens=*" %%v in ('uv --version 2^>^&1') do echo     uv: %%v
where iscc >nul 2>&1
if errorlevel 1 (
    echo ERROR: Inno Setup compiler ^(iscc^) not found on PATH.
    echo.
    echo Install Inno Setup 6+ from: https://jrsoftware.org/issetup.php
    echo Then ensure its install directory is on your PATH.
    exit /b 1
)
echo     iscc: found
for /f "tokens=*" %%v in ('uv run python --version 2^>^&1') do echo     Python: %%v
echo     Dir: %CD%
echo.

echo ==^> [2/5] [%TIME%] Installing Python dependencies...
echo     Running: uv sync --all-extras
echo.
uv sync --all-extras
if errorlevel 1 exit /b 1
echo.

echo ==^> [3/5] [%TIME%] Cleaning previous build artifacts...
if exist dist (
    echo     Removing: dist\
    rmdir /s /q dist
)
if exist build (
    echo     Removing: build\
    rmdir /s /q build
)
echo     Clean.
echo.

echo ==^> [4/5] [%TIME%] Installing PyInstaller and building application bundle...
uv pip install pyinstaller
if errorlevel 1 exit /b 1
for /f "tokens=*" %%v in ('uv run pyinstaller --version 2^>^&1') do echo     PyInstaller: %%v
echo.
echo     Spec:      packaging\scriptorium-win.spec
echo     Output:    dist\scriptorium\
echo     Log level: INFO  (analysis + collection progress shown below)
echo.
uv run pyinstaller packaging/scriptorium-win.spec --noconfirm --clean --log-level INFO
if errorlevel 1 exit /b 1
echo.

echo ==^> [5/5] [%TIME%] Building installer (Inno Setup)...
echo     Script:    packaging\installer.iss
echo     Output:    dist\ScriptoriumSetup.exe
echo     Verbosity: /V5
echo.
iscc /V5 packaging\installer.iss
if errorlevel 1 exit /b 1

echo.
echo ========================================
echo   BUILD COMPLETE  ^| %TIME%
echo   Output: dist\ScriptoriumSetup.exe
echo ========================================
