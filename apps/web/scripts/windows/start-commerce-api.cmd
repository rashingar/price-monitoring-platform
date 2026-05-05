@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "REPO_ROOT=%%~fI"

echo Starting Ecommerce API from:
echo %REPO_ROOT%\apps\ecommerce-api
echo.

if not exist "%REPO_ROOT%\scripts\dev\ecommerce-api.ps1" (
  echo ERROR: Could not find root ecommerce-api dev script.
  pause
  exit /b 1
)

if not exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
  echo ERROR: Missing root virtual environment Python: %REPO_ROOT%\.venv\Scripts\python.exe
  echo Create it from the repository root with:
  echo   py -3.13 -m venv .venv
  pause
  exit /b 1
)

echo Running: scripts\dev\ecommerce-api.ps1
echo Health: http://127.0.0.1:8001/api/health
echo Catalog summary: http://127.0.0.1:8001/api/catalog/summary
echo Price Monitoring DB status: http://127.0.0.1:8001/api/price-monitoring/db/status
echo NOTE: PostgreSQL is required for Catalog browsing and Price Monitoring workflows.
echo NOTE: PostgreSQL is not required for backend startup, health, CSV/Bridge, files, paths, or artifacts.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\dev\ecommerce-api.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: Ecommerce API exited with an error.
  pause
  exit /b 1
)

endlocal
