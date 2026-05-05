@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$checks = @(" ^
  "  @{ Name = 'Product Factory health'; Url = 'http://127.0.0.1:8000/api/health'; Hint = 'Start the Product Factory API on 127.0.0.1:8000.' }," ^
  "  @{ Name = 'Ecommerce health'; Url = 'http://127.0.0.1:8001/api/health'; Hint = 'Start ecommerce-api.' }," ^
  "  @{ Name = 'Ecommerce catalog summary'; Url = 'http://127.0.0.1:8001/api/catalog/summary'; Hint = 'If ecommerce health works, check PostgreSQL configuration, migrations, and catalog import: python -m pricefetcher.jobs.check_db_setup; alembic upgrade head; python -m pricefetcher.jobs.ingest_catalog.' }," ^
  "  @{ Name = 'Ecommerce file roots'; Url = 'http://127.0.0.1:8001/api/files/roots'; Hint = 'Check backend file roots configuration.' }," ^
  "  @{ Name = 'Ecommerce artifact roots'; Url = 'http://127.0.0.1:8001/api/artifacts/roots'; Hint = 'Check the ecommerce-api backend and artifact roots configuration.' }" ^
  ");" ^
  "$results = @{};" ^
  "foreach ($check in $checks) {" ^
  "  try {" ^
  "    $response = Invoke-WebRequest -Uri $check.Url -UseBasicParsing -TimeoutSec 5;" ^
  "    $ok = $response.StatusCode -ge 200 -and $response.StatusCode -lt 300;" ^
  "    $results[$check.Name] = $ok;" ^
  "    if ($ok) { Write-Host ('OK   ' + $check.Name + ' - HTTP ' + $response.StatusCode) -ForegroundColor Green }" ^
  "    else { Write-Host ('FAIL ' + $check.Name + ' - HTTP ' + $response.StatusCode) -ForegroundColor Red; Write-Host ('     ' + $check.Hint) }" ^
  "  } catch {" ^
  "    $results[$check.Name] = $false;" ^
  "    Write-Host ('FAIL ' + $check.Name + ' - ' + $_.Exception.Message) -ForegroundColor Red;" ^
  "    Write-Host ('     ' + $check.Hint)" ^
  "  }" ^
  "}" ^
  "if (($results['Ecommerce health'] -eq $true) -and ($results['Ecommerce catalog summary'] -ne $true)) {" ^
  "  Write-Host ''; Write-Host 'Hint: Ecommerce API is running, but catalog summary failed. Check PostgreSQL configuration, migrations, and catalog import.' -ForegroundColor Yellow;" ^
  "  Write-Host '      python -m pricefetcher.jobs.check_db_setup' -ForegroundColor Yellow;" ^
  "  Write-Host '      alembic upgrade head' -ForegroundColor Yellow;" ^
  "  Write-Host '      python -m pricefetcher.jobs.ingest_catalog' -ForegroundColor Yellow" ^
  "}"

echo.
pause
endlocal
