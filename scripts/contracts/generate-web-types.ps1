param()

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appRoot = Join-Path $repoRoot "apps\web"
$nodeModules = Join-Path $appRoot "node_modules"

if (-not (Test-Path -LiteralPath $nodeModules)) {
    Write-Host "Web setup commands from the repository root:"
    Write-Host "Push-Location apps\web"
    Write-Host "npm ci"
    Write-Host "Pop-Location"
    Write-Error "Missing web dependencies: $nodeModules"
    exit 1
}

Write-Host "Checking mirrored OpenAPI contracts before generating web API types..."
& (Join-Path $PSScriptRoot "check.ps1") -SkipWebTypes
if ($LASTEXITCODE -ne 0) {
    Write-Error "Mirrored OpenAPI contract check failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Push-Location $appRoot
try {
    npm run generate:api-types
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
