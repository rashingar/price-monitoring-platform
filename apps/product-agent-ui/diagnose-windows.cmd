@echo off
setlocal

echo Product-Agent API: http://127.0.0.1:8000
echo Commerce API:      http://127.0.0.1:8001
echo UI:                http://127.0.0.1:5173
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$checks = @(" ^
  "@{Name='Product-Agent health'; Url='http://127.0.0.1:8000/api/health'}," ^
  "@{Name='Commerce catalog summary'; Url='http://127.0.0.1:8001/api/catalog/summary'}," ^
  "@{Name='Commerce file roots'; Url='http://127.0.0.1:8001/api/files/roots'}" ^
  "); foreach ($check in $checks) { try { $response = Invoke-WebRequest -UseBasicParsing -Uri $check.Url -TimeoutSec 5; Write-Host ('OK    ' + $check.Name + ' -> HTTP ' + $response.StatusCode) } catch { $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'no response' }; Write-Host ('FAIL  ' + $check.Name + ' -> ' + $status + ' (' + $_.Exception.Message + ')') } }"

endlocal
