$ErrorActionPreference = "Stop"

# Codex-safe aggregate fast verification. Delegated app scripts keep runtime,
# db_integration, postgres_required, external, e2e, legacy, and slow checks out
# of the default path where applicable. Do not add runtime, DB integration,
# PostgreSQL, or golden profile scripts here.
$tests = @(
    @{ Name = "snapshot hygiene"; Script = Join-Path $PSScriptRoot "check-snapshots.ps1" },
    @{ Name = "fast marker hygiene"; Script = Join-Path $PSScriptRoot "check-fast-marker-hygiene.ps1" },
    @{ Name = "product-factory-api"; Script = Join-Path $PSScriptRoot "product-factory-api.ps1" },
    @{ Name = "ecommerce-api"; Script = Join-Path $PSScriptRoot "ecommerce-api.ps1" },
    @{ Name = "web"; Script = Join-Path $PSScriptRoot "web.ps1" },
    @{ Name = "contract mirrors"; Script = Join-Path $PSScriptRoot "..\contracts\check.ps1" }
)

foreach ($test in $tests) {
    Write-Host "Running $($test.Name) tests..."
    & $test.Script
    if ($LASTEXITCODE -ne 0) {
        Write-Error "$($test.Name) tests failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

Write-Host "Codex-safe aggregate fast verification completed successfully."
exit 0
