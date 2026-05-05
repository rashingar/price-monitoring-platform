@echo off
setlocal

set "SCRIPT_DIR=%~dp0"

echo Starting local platform windows...
echo.
echo Product Factory API: http://127.0.0.1:8000
echo Ecommerce API:       http://127.0.0.1:8001
echo Web:                 http://127.0.0.1:5173
echo.
start "Commerce API" cmd /k ""%SCRIPT_DIR%start-commerce-api.cmd""
start "Product Factory API" cmd /k ""%SCRIPT_DIR%start-product-factory-api.cmd""
start "Web" cmd /k ""%SCRIPT_DIR%start-ui.cmd""

echo Startup windows opened.
echo Run scripts\windows\diagnose.cmd to check service health.
echo.

endlocal
