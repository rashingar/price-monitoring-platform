$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\product-factory-api"
$srcRoot = Join-Path $appRoot "src"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

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
    import product_factory
    import product_factory.dev.start
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
if matches[0].value != "product_factory.dev.start:main":
    print(
        "Product Factory console script target is unexpected: "
        f"{matches[0].value!r}; expected 'product_factory.dev.start:main'.",
        file=sys.stderr,
    )
    sys.exit(13)
'@

$checkPath = New-TemporaryFile
try {
    Set-Content -LiteralPath $checkPath -Value $checkCode -Encoding UTF8
    & $python $checkPath
    if ($LASTEXITCODE -ne 0) {
        Write-ProductFactorySetupInstructions
        exit $LASTEXITCODE
    }
}
finally {
    Remove-Item -LiteralPath $checkPath -ErrorAction SilentlyContinue
}

Set-Location $appRoot
& $python -m pytest -vv -ra -c (Join-Path $srcRoot "pytest.ini") -m "not slow and not external and not e2e and not legacy"
exit $LASTEXITCODE
