$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\product-factory-api"
$srcRoot = Join-Path $appRoot "src"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Missing root virtual environment Python: $python. Create the monorepo virtual environment from the repository root with: py -3.13 -m venv .venv"
    exit 1
}

Set-Location $srcRoot
& $python -m pytest -vv -ra -m "not external and not e2e and not slow"
exit $LASTEXITCODE
