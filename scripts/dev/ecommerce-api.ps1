$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\ecommerce-api"
$python = Join-Path $appRoot ".venv\Scripts\python.exe"

Set-Location $appRoot

if (Test-Path -LiteralPath $python) {
    & $python -m pricefetcher.dev.start
    exit $LASTEXITCODE
}

$cli = Get-Command pricefetcher-api -ErrorAction SilentlyContinue
if ($null -ne $cli) {
    & $cli.Source
    exit $LASTEXITCODE
}

Write-Error "Missing ecommerce-api dependencies. Setup: cd apps\ecommerce-api; py -3.11 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt; .\.venv\Scripts\python.exe -m pip install -e . --no-deps"
exit 1
