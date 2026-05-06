$ErrorActionPreference = "Stop"

Write-Host "Running Codex-targeted Product Factory fast checks..."
& (Join-Path $PSScriptRoot "product-factory-api.ps1")
exit $LASTEXITCODE
