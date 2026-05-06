$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\product-factory-api"
$srcRoot = Join-Path $appRoot "src"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Missing root virtual environment Python: $python"
    exit 1
}

Set-Location $appRoot
& $python -m pytest -vv -ra -c (Join-Path $srcRoot "pytest.ini") -m "runtime or slow or e2e"
exit $LASTEXITCODE
