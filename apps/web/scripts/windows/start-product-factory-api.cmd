@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "REPO_ROOT=%%~fI"

echo Starting Product Factory API from:
echo %REPO_ROOT%\apps\product-factory-api\src
echo.

if not exist "%REPO_ROOT%\scripts\dev\product-factory-api.ps1" (
  echo ERROR: Could not find root Product Factory dev script.
  pause
  exit /b 1
)

if not exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
  echo ERROR: Missing root virtual environment Python: %REPO_ROOT%\.venv\Scripts\python.exe
  echo Create it from the repository root with:
  echo   python --version
  echo   python -m venv .venv
  echo   .\.venv\Scripts\python.exe --version
  echo   .\.venv\Scripts\python.exe -m pip install -r apps\product-factory-api\requirements.txt
  echo   .\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps
  echo Python 3.11 or newer is required. If python is missing or too old, install a supported Python version and reopen PowerShell.
  pause
  exit /b 1
)

echo Running: scripts\dev\product-factory-api.ps1
echo Health: http://127.0.0.1:8000/api/health
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\dev\product-factory-api.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: Product Factory API exited with an error.
  pause
  exit /b 1
)

endlocal
