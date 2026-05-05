$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\ecommerce-api"
$python = Join-Path $appRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Missing ecommerce-api virtual environment Python: $python. Setup: cd apps\ecommerce-api; py -3.11 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt; .\.venv\Scripts\python.exe -m pip install -e . --no-deps"
    exit 1
}

Set-Location $appRoot
& $python -m pytest -vv -m "not external and not slow"
exit $LASTEXITCODE
