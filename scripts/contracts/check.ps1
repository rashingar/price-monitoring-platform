param(
    [switch]$SkipWebTypes
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$contractsRoot = Join-Path $repoRoot "packages\contracts"
$mirrors = @(
    @{
        Name = "Product Factory"
        Mirror = (Join-Path $contractsRoot "openapi.product-factory.json")
        Source = (Join-Path $repoRoot "apps\product-factory-api\docs\contracts\openapi.product-factory.json")
    },
    @{
        Name = "Ecommerce"
        Mirror = (Join-Path $contractsRoot "openapi.ecommerce.json")
        Source = (Join-Path $repoRoot "apps\ecommerce-api\docs\contracts\openapi.ecommerce.json")
    }
)

$expected = @()
foreach ($mirror in $mirrors) {
    $expected += $mirror.Mirror
    $expected += $mirror.Source
}

$missing = @($expected | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missing.Count -gt 0) {
    Write-Error "Missing mirrored contract snapshot(s): $($missing -join ', '). Expected app-local snapshots to be mirrored from apps\product-factory-api\docs\contracts and apps\ecommerce-api\docs\contracts."
    exit 1
}

foreach ($mirror in $mirrors) {
    if ((Get-FileHash -LiteralPath $mirror.Mirror -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $mirror.Source -Algorithm SHA256).Hash) {
        Write-Error "$($mirror.Name) mirrored OpenAPI contract is stale: $($mirror.Mirror) does not match $($mirror.Source). Refresh the mirror from the app-local snapshot."
        exit 1
    }
}

Write-Host "Mirrored OpenAPI contracts are present and match app-local snapshots in packages\contracts."

if (-not $SkipWebTypes) {
    $webTypesCheck = Join-Path $PSScriptRoot "check-web-types.ps1"
    if (-not (Test-Path -LiteralPath $webTypesCheck)) {
        Write-Error "Missing generated web API type check script: $webTypesCheck"
        exit 1
    }

    & $webTypesCheck -SkipMirrorCheck
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Generated web API type check failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

exit 0
