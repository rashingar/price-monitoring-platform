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

Set-Location $appRoot
$package = Get-Content -LiteralPath "package.json" -Raw | ConvertFrom-Json
$scripts = $package.scripts.PSObject.Properties.Name

if ($scripts -contains "test:fast") {
    npm run test:fast -- --reporter=verbose
} else {
    npm test -- --reporter=verbose
}
exit $LASTEXITCODE
