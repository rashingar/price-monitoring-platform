$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$webNodeModules = Join-Path $repoRoot "apps\web\node_modules"

function Invoke-CheckScript {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$ScriptPath
    )

    Write-Host ""
    Write-Host "== Running $Name =="
    & $ScriptPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "$Name failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

Invoke-CheckScript -Name "hygiene checks" -ScriptPath (Join-Path $repoRoot "scripts\check\hygiene.ps1")
Invoke-CheckScript -Name "contract mirror checks" -ScriptPath (Join-Path $repoRoot "scripts\contracts\check.ps1")

if (Test-Path -LiteralPath $webNodeModules) {
    Invoke-CheckScript -Name "generated web API type checks" -ScriptPath (Join-Path $repoRoot "scripts\contracts\check-web-types.ps1")
} else {
    Write-Host ""
    Write-Host "== Generated web API type checks =="
    Write-Host "SKIP: apps\web\node_modules is missing. Run .\scripts\setup\web.ps1 to enable this check."
}

if ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $webNodeModules)) {
    Invoke-CheckScript -Name "fast tests" -ScriptPath (Join-Path $repoRoot "scripts\test\fast.ps1")
} else {
    Write-Host ""
    Write-Host "== Fast tests =="
    Write-Host "SKIP: root .venv and apps\web\node_modules are required. Run setup scripts before fast tests."
}

Write-Host ""
Write-Host "All available root checks completed successfully."
exit 0
