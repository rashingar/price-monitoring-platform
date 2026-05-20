$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$devRequirements = Join-Path $repoRoot "requirements-dev.txt"
$productFactoryRoot = Join-Path $repoRoot "apps\product-factory-api"
$ecommerceRoot = Join-Path $repoRoot "apps\ecommerce-api"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Command,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage Exit code: $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "Root .venv is required before installing Python dependencies."
    Write-Host "Run from the repository root: .\scripts\setup\root-venv.ps1"
    Write-Error "Missing root virtual environment Python: $python"
    exit 1
}

Write-Host "Using root .venv Python:"
Invoke-NativeCommand { & $python --version } "Root .venv Python is not runnable."

Write-Host ""
Write-Host "Installing Product Factory requirements..."
Invoke-NativeCommand { & $python -m pip install -r (Join-Path $productFactoryRoot "requirements.txt") } "Product Factory requirements install failed."

Write-Host ""
Write-Host "Installing Product Factory editable package..."
Invoke-NativeCommand { & $python -m pip install -e $productFactoryRoot --no-deps } "Product Factory editable install failed."

Write-Host ""
Write-Host "Installing Ecommerce API locked requirements..."
Invoke-NativeCommand { & $python -m pip install -r (Join-Path $ecommerceRoot "requirements-lock.txt") } "Ecommerce API requirements install failed."

Write-Host ""
Write-Host "Installing Ecommerce API editable package..."
Invoke-NativeCommand { & $python -m pip install -e $ecommerceRoot --no-deps } "Ecommerce API editable install failed."

Write-Host ""
Write-Host "Installing root developer requirements..."
Invoke-NativeCommand { & $python -m pip install -r $devRequirements } "Root developer requirements install failed."

Write-Host ""
Write-Host "Python dependency setup complete. No unified Python lockfile was created."
exit 0
