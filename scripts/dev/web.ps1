$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\web"
$nodeModules = Join-Path $appRoot "node_modules"

if (-not (Test-Path -LiteralPath $nodeModules)) {
    Write-Error "Missing web dependencies: $nodeModules. Setup: cd apps\web; npm ci"
    exit 1
}

Set-Location $appRoot
npm run dev
exit $LASTEXITCODE
