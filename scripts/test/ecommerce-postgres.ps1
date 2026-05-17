$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\ecommerce-api"
$srcRoot = Join-Path $appRoot "src"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Missing root virtual environment Python: $python"
    exit 1
}

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcRoot;$appRoot;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = "$srcRoot;$appRoot"
}

Set-Location $appRoot
& $python -m pytest -vv -ra -m postgres_required
$exitCode = $LASTEXITCODE
if ($exitCode -eq 5) {
    Write-Host "No postgres_required tests selected; skipping PostgreSQL profile."
    exit 0
}
exit $exitCode
