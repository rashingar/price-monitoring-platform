$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$webRoot = Join-Path $repoRoot "apps\web"
$nodeModules = Join-Path $webRoot "node_modules"
$failures = 0

function Invoke-LocalCheck {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Check
    )

    Write-Host ""
    Write-Host "== $Name =="
    try {
        & $Check
        Write-Host "OK: $Name"
    }
    catch {
        $script:failures += 1
        Write-Host "FAIL: $Name"
        Write-Host $_.Exception.Message
    }
}

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

$productFactoryImportCheck = @'
from importlib import metadata
import sys

try:
    metadata.distribution('product-factory')
    import pipeline
    import pipeline.dev.start
except Exception as exc:
    print(f'Product Factory import failed: {exc}', file=sys.stderr)
    sys.exit(1)
print('Product Factory import OK.')
'@

$ecommerceImportCheck = @'
from importlib import metadata
import sys

try:
    metadata.distribution('ecommerce')
    import ecommerce
    import ecommerce.dev.start
except Exception as exc:
    print(f'Ecommerce API import failed: {exc}', file=sys.stderr)
    sys.exit(1)
print('Ecommerce API import OK.')
'@

Write-Host "Checking local startup prerequisites from $repoRoot"
Write-Host "This script does not start servers and does not mutate the database."

Invoke-LocalCheck "Root .venv" {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Missing root virtual environment Python: $python. Create it with: python -m venv .venv"
    }
    Invoke-NativeCommand { & $python --version } "Root .venv Python is not runnable."
}

Invoke-LocalCheck "Product Factory editable import" {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Cannot check Product Factory import because root .venv is missing."
    }
    Invoke-NativeCommand { & $python -c $productFactoryImportCheck } "Product Factory import check failed. Run: .\.venv\Scripts\python.exe -m pip install -r apps\product-factory-api\requirements.txt; .\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps"
}

Invoke-LocalCheck "Ecommerce API editable import" {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Cannot check Ecommerce API import because root .venv is missing."
    }
    Invoke-NativeCommand { & $python -c $ecommerceImportCheck } "Ecommerce API import check failed. Run: .\.venv\Scripts\python.exe -m pip install -r apps\ecommerce-api\requirements-lock.txt; .\.venv\Scripts\python.exe -m pip install -e apps\ecommerce-api --no-deps"
}

Invoke-LocalCheck "Web node_modules" {
    if (-not (Test-Path -LiteralPath $nodeModules)) {
        throw "Missing web dependencies: $nodeModules. Run: Push-Location apps\web; npm ci; Pop-Location"
    }
}

Invoke-LocalCheck "Mirrored OpenAPI contracts" {
    Invoke-NativeCommand { & (Join-Path $repoRoot "scripts\contracts\check.ps1") -SkipWebTypes } "Mirrored OpenAPI contract check failed."
}

if (Test-Path -LiteralPath $nodeModules) {
    Invoke-LocalCheck "Generated web API types" {
        Invoke-NativeCommand { & (Join-Path $repoRoot "scripts\contracts\check-web-types.ps1") -SkipMirrorCheck } "Generated web API type freshness check failed."
    }
} else {
    Write-Host ""
    Write-Host "== Generated web API types =="
    Write-Host "SKIP: apps\web\node_modules is missing, so generated web API type freshness cannot be checked."
}

Write-Host ""
if ($failures -gt 0) {
    Write-Host "Local startup diagnostics failed: $failures check(s) need attention."
    exit 1
}

Write-Host "Local startup diagnostics passed."
exit 0
