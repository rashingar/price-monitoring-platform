$ErrorActionPreference = "Stop"

Write-Host "Running Codex-targeted Ecommerce API fast checks..."
& (Join-Path $PSScriptRoot "ecommerce-api.ps1")
exit $LASTEXITCODE
