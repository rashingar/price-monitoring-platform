$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\ecommerce-api"
$srcRoot = Join-Path $appRoot "src"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

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

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcRoot;$appRoot;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = "$srcRoot;$appRoot"
}

$checkCode = @'
try:
    import ecommerce.api.app
except ImportError as exc:
    raise SystemExit("Ecommerce API import check failed: " + str(exc))
'@

$checkPath = New-TemporaryFile
try {
    Set-Content -LiteralPath $checkPath -Value $checkCode -Encoding UTF8
    & $python $checkPath
    if ($LASTEXITCODE -ne 0) {
        Write-EcommerceSetupInstructions
        exit $LASTEXITCODE
    }
}
finally {
    Remove-Item -LiteralPath $checkPath -ErrorAction SilentlyContinue
}

Set-Location $appRoot
& $python -m pytest -vv -ra -m "not slow and not external and not e2e and not legacy and not runtime and not db_integration and not postgres_required"
exit $LASTEXITCODE
