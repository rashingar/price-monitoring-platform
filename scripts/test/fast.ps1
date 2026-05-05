$ErrorActionPreference = "Stop"

$tests = @(
    @{ Name = "product-factory-api"; Script = Join-Path $PSScriptRoot "product-factory-api.ps1" },
    @{ Name = "ecommerce-api"; Script = Join-Path $PSScriptRoot "ecommerce-api.ps1" },
    @{ Name = "web"; Script = Join-Path $PSScriptRoot "web.ps1" }
)

foreach ($test in $tests) {
    Write-Host "Running $($test.Name) tests..."
    & $test.Script
    if ($LASTEXITCODE -ne 0) {
        Write-Error "$($test.Name) tests failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

Write-Host "All fast app test scripts completed successfully."
exit 0
