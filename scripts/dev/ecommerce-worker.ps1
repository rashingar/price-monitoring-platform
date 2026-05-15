$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\ecommerce-api"
$srcRoot = Join-Path $appRoot "src"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$envLoader = Join-Path $repoRoot "scripts\dev\load-root-env.ps1"

function Write-EcommerceSetupInstructions {
    Write-Host "Ecommerce worker setup commands from the repository root:"
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

& $envLoader -RepoRoot $repoRoot -DeprecatedAppEnvPath (Join-Path $appRoot ".env") | Out-Null

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcRoot;$appRoot;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = "$srcRoot;$appRoot"
}

Set-Location $appRoot
& $python -m ecommerce.jobs.worker @args
exit $LASTEXITCODE
