$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\product-factory-api"
$srcRoot = Join-Path $appRoot "src"
$python = Join-Path $appRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Missing Product Factory virtual environment Python: $python. Setup: cd apps\product-factory-api; py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

Set-Location $srcRoot
& $python -m pytest -vv -m "not external and not e2e and not slow"
exit $LASTEXITCODE
