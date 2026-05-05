@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "UI_ROOT=%%~fI"

if defined PRODUCT_AGENT_DIR (
  set "PRODUCT_AGENT_ROOT=%PRODUCT_AGENT_DIR%"
) else (
  set "PRODUCT_AGENT_ROOT=%UI_ROOT%\..\Product-Agent"
)

for %%I in ("%PRODUCT_AGENT_ROOT%") do set "PRODUCT_AGENT_ROOT=%%~fI"
set "PRODUCT_AGENT_SCRAPER=%PRODUCT_AGENT_ROOT%\scraper"

echo Starting Product-Agent API from:
echo %PRODUCT_AGENT_SCRAPER%
echo.

if not exist "%PRODUCT_AGENT_ROOT%" (
  echo ERROR: Product-Agent directory was not found.
  echo Set PRODUCT_AGENT_DIR to the local Product-Agent repository path.
  echo.
  pause
  exit /b 1
)

if not exist "%PRODUCT_AGENT_SCRAPER%" (
  echo ERROR: Missing Product-Agent scraper folder.
  pause
  exit /b 1
)

cd /d "%PRODUCT_AGENT_SCRAPER%" || (
  echo ERROR: Could not change directory to %PRODUCT_AGENT_SCRAPER%.
  pause
  exit /b 1
)

if defined PRODUCT_AGENT_API_CMD (
  echo Running PRODUCT_AGENT_API_CMD override:
  echo %PRODUCT_AGENT_API_CMD%
  echo.
  call %PRODUCT_AGENT_API_CMD%
  if errorlevel 1 (
    echo.
    echo ERROR: Product-Agent API command exited with an error.
    pause
    exit /b 1
  )
  exit /b 0
)

if not exist "..\.venv\Scripts\python.exe" (
  echo ERROR: Missing Product-Agent virtual environment: Product-Agent\.venv
  echo Setup hints from the Product-Agent folder:
  echo   py -3.13 -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements-lock.txt
  echo   .venv\Scripts\python.exe -m playwright install chromium
  pause
  exit /b 1
)

echo Running: ..\.venv\Scripts\python.exe -m pipeline.dev.start --host 127.0.0.1 --port 8000 --reload
echo Health: http://127.0.0.1:8000/api/health
echo.

"..\.venv\Scripts\python.exe" -m pipeline.dev.start --host 127.0.0.1 --port 8000 --reload
if errorlevel 1 (
  echo.
  echo ERROR: Product-Agent API exited with an error.
  pause
  exit /b 1
)

endlocal
