@echo off
setlocal

set "SCRIPT_DIR=%~dp0"

echo Starting local platform windows...
echo.
echo Product-Agent API: http://127.0.0.1:8000
echo Commerce API:      http://127.0.0.1:8001
echo UI:                http://127.0.0.1:5173
echo.
start "Commerce API" cmd /k ""%SCRIPT_DIR%start-commerce-api.cmd""
start "Product-Agent API" cmd /k ""%SCRIPT_DIR%start-product-agent-api.cmd""
start "Product-Agent UI" cmd /k ""%SCRIPT_DIR%start-ui.cmd""

echo Startup windows opened.
echo Run scripts\windows\diagnose.cmd to check service health.
echo Parent-level scripts\local entrypoints are the canonical startup scripts when all sibling repos are present.
echo.

endlocal
