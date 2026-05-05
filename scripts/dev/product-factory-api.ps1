$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\product-factory-api"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$consoleScript = Join-Path $repoRoot ".venv\Scripts\product-factory-api.exe"

function Write-ProductFactorySetupInstructions {
    Write-Host "Product Factory setup commands from the repository root:"
    Write-Host "python --version"
    Write-Host "python -m venv .venv"
    Write-Host ".\.venv\Scripts\python.exe --version"
    Write-Host ".\.venv\Scripts\python.exe -m pip install -r apps\product-factory-api\requirements.txt"
    Write-Host ".\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps"
    Write-Host "Python 3.11 or newer is required. If python is missing or too old, install a supported Python version and reopen PowerShell."
}

if (-not (Test-Path -LiteralPath $python)) {
    Write-ProductFactorySetupInstructions
    Write-Error "Missing root virtual environment Python: $python"
    exit 1
}

$checkCode = @'
from importlib import metadata
import sys

try:
    dist = metadata.distribution("product-factory")
except metadata.PackageNotFoundError:
    print("Product Factory editable install is missing: distribution 'product-factory' is not installed.", file=sys.stderr)
    sys.exit(10)

try:
    import pipeline
    import pipeline.dev.start
except ImportError as exc:
    print(f"Product Factory import check failed: {exc}", file=sys.stderr)
    sys.exit(11)

matches = [
    entry_point
    for entry_point in dist.entry_points
    if entry_point.group == "console_scripts" and entry_point.name == "product-factory-api"
]
if not matches:
    print("Product Factory console script metadata is missing: product-factory-api.", file=sys.stderr)
    sys.exit(12)
if matches[0].value != "pipeline.dev.start:main":
    print(
        "Product Factory console script target is unexpected: "
        f"{matches[0].value!r}; expected 'pipeline.dev.start:main'.",
        file=sys.stderr,
    )
    sys.exit(13)
'@

& $python -c $checkCode
if ($LASTEXITCODE -ne 0) {
    Write-ProductFactorySetupInstructions
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $consoleScript)) {
    Write-Host "Missing Product Factory console script: $consoleScript"
    Write-ProductFactorySetupInstructions
    exit 1
}

Set-Location $appRoot
Write-Host "Starting Product Factory API on http://127.0.0.1:8000"
Write-Host "Health URL: http://127.0.0.1:8000/api/health"
& $consoleScript --host 127.0.0.1 --port 8000 --reload
exit $LASTEXITCODE
