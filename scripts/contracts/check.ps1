$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$contractsRoot = Join-Path $repoRoot "packages\contracts"
$expected = @(
    (Join-Path $contractsRoot "openapi.product-factory.json"),
    (Join-Path $contractsRoot "openapi.ecommerce.json")
)

$missing = @($expected | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missing.Count -gt 0) {
    Write-Error "Missing mirrored contract snapshot(s): $($missing -join ', '). Expected app-local snapshots to be mirrored from apps\product-factory-api\docs\contracts and apps\ecommerce-api\docs\contracts."
    exit 1
}

Write-Host "Mirrored OpenAPI contracts are present in packages\contracts."
exit 0
