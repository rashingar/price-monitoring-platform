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
    import product_factory
    import product_factory.dev.start
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

Write-Host "Checking local setup prerequisites from $repoRoot"
Write-Host "This script does not start servers and does not mutate the database."

Invoke-LocalCheck "Root .venv" {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Missing root virtual environment Python: $python. Run: .\scripts\setup\root-venv.ps1"
    }
    Invoke-NativeCommand { & $python --version } "Root .venv Python is not runnable."
}

Invoke-LocalCheck "Product Factory editable import" {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Cannot check Product Factory import because root .venv is missing."
    }
    Invoke-NativeCommand { & $python -c $productFactoryImportCheck } "Product Factory import check failed. Run: .\scripts\setup\python-deps.ps1"
}

Invoke-LocalCheck "Ecommerce API editable import" {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Cannot check Ecommerce API import because root .venv is missing."
    }
    Invoke-NativeCommand { & $python -c $ecommerceImportCheck } "Ecommerce API import check failed. Run: .\scripts\setup\python-deps.ps1"
}

Invoke-LocalCheck "Web node_modules" {
    if (-not (Test-Path -LiteralPath $nodeModules)) {
        throw "Missing web dependencies: $nodeModules. Run: .\scripts\setup\web.ps1"
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
    Write-Host "Local setup diagnostics failed: $failures check(s) need attention."
    exit 1
}

Write-Host "Local setup diagnostics passed."
exit 0
