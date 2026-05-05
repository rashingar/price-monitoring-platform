@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "UI_ROOT=%%~fI"

if defined PRICE_FETCHER_DIR (
  set "PRICE_FETCHER_ROOT=%PRICE_FETCHER_DIR%"
) else (
  set "PRICE_FETCHER_ROOT=%UI_ROOT%\..\price-fetcher"
)

for %%I in ("%PRICE_FETCHER_ROOT%") do set "PRICE_FETCHER_ROOT=%%~fI"

echo Starting Commerce API from:
echo %PRICE_FETCHER_ROOT%
echo.

if not exist "%PRICE_FETCHER_ROOT%" (
  echo ERROR: Price-fetcher directory was not found.
  echo Set PRICE_FETCHER_DIR to the local price-fetcher repository path.
  echo.
  pause
  exit /b 1
)

cd /d "%PRICE_FETCHER_ROOT%" || (
  echo ERROR: Could not change directory to %PRICE_FETCHER_ROOT%.
  pause
  exit /b 1
)

set "PYTHONPATH=%CD%\src;%CD%;%PYTHONPATH%"

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
)

where pricefetcher-api >nul 2>nul
if not errorlevel 1 (
  echo Running: pricefetcher-api
  echo Health: http://127.0.0.1:8001/api/health
  echo Catalog summary: http://127.0.0.1:8001/api/catalog/summary
  echo Price Monitoring DB status: http://127.0.0.1:8001/api/price-monitoring/db/status
  echo NOTE: PostgreSQL is required for Catalog browsing and Price Monitoring workflows.
  echo NOTE: PostgreSQL is not required for backend startup, health, CSV/Bridge, files, paths, or artifacts.
  echo.
  pricefetcher-api
  if errorlevel 1 (
    echo.
    echo ERROR: pricefetcher-api exited with an error.
    echo Setup hints:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements-lock.txt
    echo   .venv\Scripts\python.exe -m pip install -e . --no-deps
    echo   .venv\Scripts\python.exe -m playwright install chromium
    pause
    exit /b 1
  )
  exit /b 0
)

echo pricefetcher-api was not found on PATH.

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

echo Falling back to: %PYTHON_EXE% -m pricefetcher.api.app
echo Health: http://127.0.0.1:8001/api/health
echo Catalog summary: http://127.0.0.1:8001/api/catalog/summary
echo Price Monitoring DB status: http://127.0.0.1:8001/api/price-monitoring/db/status
echo NOTE: PostgreSQL is required for Catalog browsing and Price Monitoring workflows.
echo NOTE: PostgreSQL is not required for backend startup, health, CSV/Bridge, files, paths, or artifacts.
echo.

"%PYTHON_EXE%" -c "import pricefetcher.api.app" >nul 2>nul
if errorlevel 1 (
  echo ERROR: Could not import pricefetcher.api.app.
  echo Setup hints:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements-lock.txt
  echo   .venv\Scripts\python.exe -m pip install -e . --no-deps
  echo   .venv\Scripts\python.exe -m playwright install chromium
  pause
  exit /b 1
)

"%PYTHON_EXE%" -m pricefetcher.api.app
if errorlevel 1 (
  echo.
  echo ERROR: Commerce API exited with an error.
  pause
  exit /b 1
)

endlocal
