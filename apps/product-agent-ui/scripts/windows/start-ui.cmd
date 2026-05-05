@echo off
setlocal

set "RUN_INSTALL=0"
for %%A in (%*) do (
  if /I "%%~A"=="/install" set "RUN_INSTALL=1"
)

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "UI_ROOT=%%~fI"

cd /d "%UI_ROOT%" || (
  echo ERROR: Could not change directory to %UI_ROOT%.
  pause
  exit /b 1
)

echo Starting Product-Agent UI from:
echo %UI_ROOT%
echo.

where npm >nul 2>nul
if errorlevel 1 (
  echo ERROR: npm was not found on PATH.
  echo Install Node.js/npm, then run:
  echo   npm install
  pause
  exit /b 1
)

if not exist "node_modules\" (
  echo ERROR: node_modules is missing.
  if "%RUN_INSTALL%"=="1" (
    if exist "package-lock.json" (
      echo Running: npm ci
      call npm ci
    ) else (
      echo Running: npm install
      call npm install
    )
    if errorlevel 1 (
      echo ERROR: UI dependency install failed.
      pause
      exit /b 1
    )
  ) else (
    echo Run:
    echo   npm ci
    echo Or allow this script to install dependencies:
    echo   scripts\windows\start-ui.cmd /install
    pause
    exit /b 1
  )
)

echo Running: npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
echo URL: http://127.0.0.1:5173
if defined VITE_API_PROXY_TARGET echo VITE_API_PROXY_TARGET=%VITE_API_PROXY_TARGET%
if defined VITE_COMMERCE_API_PROXY_TARGET echo VITE_COMMERCE_API_PROXY_TARGET=%VITE_COMMERCE_API_PROXY_TARGET%
echo.

call npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
if errorlevel 1 (
  echo.
  echo ERROR: npm run dev exited with an error.
  pause
  exit /b 1
)

endlocal
