$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\ecommerce-api"
$srcRoot = Join-Path $appRoot "src"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$envLoader = Join-Path $repoRoot "scripts\dev\load-root-env.ps1"

function Write-EcommerceSetupInstructions {
    Write-Host "Ecommerce API setup commands from the repository root:"
    Write-Host "python --version"
    Write-Host "python -m venv .venv"
    Write-Host ".\.venv\Scripts\python.exe --version"
    Write-Host ".\.venv\Scripts\python.exe -m pip install -r apps\ecommerce-api\requirements-lock.txt"
    Write-Host ".\.venv\Scripts\python.exe -m pip install -e apps\ecommerce-api --no-deps"
    Write-Host "Python 3.11 or newer is required. If python is missing or too old, install a supported Python version and reopen PowerShell."
}

if (-not (Test-Path -LiteralPath $python)) {
    Write-EcommerceSetupInstructions
    Write-Error "Missing root virtual environment Python: $python"
    exit 1
}

$checkCode = @'
from importlib import metadata
import sys

try:
    metadata.distribution('ecommerce')
except metadata.PackageNotFoundError:
    print('Ecommerce API editable install is missing: distribution ecommerce is not installed.', file=sys.stderr)
    sys.exit(10)

try:
    import ecommerce
    import ecommerce.dev.start
except ImportError as exc:
    print(f'Ecommerce API import check failed. Install dependencies into the root .venv and reinstall the editable project. Import error: {exc}', file=sys.stderr)
    sys.exit(11)
'@

& $python -c $checkCode
if ($LASTEXITCODE -ne 0) {
    Write-EcommerceSetupInstructions
    exit $LASTEXITCODE
}

& $envLoader -RepoRoot $repoRoot -DeprecatedAppEnvPath (Join-Path $appRoot ".env") | Out-Null

Set-Location $appRoot

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcRoot;$appRoot;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = "$srcRoot;$appRoot"
}

if (-not $env:ECOMMERCE_DATABASE_URL) {
    Write-Host "ECOMMERCE_DATABASE_URL is not set. The API can still start and /api/health should respond."
    Write-Host "DB-backed Ecommerce workflows will report not ready until PostgreSQL is configured, migrations are applied, and catalog data is imported."
    Write-Host "Set ECOMMERCE_DATABASE_URL, then run alembic upgrade head from apps\ecommerce-api."
} else {
    Write-Host "ECOMMERCE_DATABASE_URL is set. If PostgreSQL is stopped, credentials are wrong, or migrations are missing, the API should still start and /api/price-monitoring/db/status will show setup hints."
}

& $python -m ecommerce.dev.start --host 127.0.0.1 --port 8001 --reload
exit $LASTEXITCODE
