$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\web"
$nodeModules = Join-Path $appRoot "node_modules"
$envLoader = Join-Path $repoRoot "scripts\dev\load-root-env.ps1"

if (-not (Test-Path -LiteralPath $nodeModules)) {
    Write-Error "Missing web dependencies: $nodeModules. Setup: cd apps\web; npm ci"
    exit 1
}

& $envLoader -RepoRoot $repoRoot -DeprecatedAppEnvPath (Join-Path $appRoot ".env") | Out-Null

Set-Location $appRoot
Write-Host "Starting web dev server on http://127.0.0.1:5173"
Write-Host "/api proxies to Product Factory API at http://127.0.0.1:8000"
Write-Host "/commerce-api proxies to Ecommerce API at http://127.0.0.1:8001"
npm run dev
exit $LASTEXITCODE
