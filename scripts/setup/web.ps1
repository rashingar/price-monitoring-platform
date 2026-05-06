$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$webRoot = Join-Path $repoRoot "apps\web"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "npm was not found on PATH. Install Node.js/npm, reopen PowerShell, and rerun this script."
    exit 1
}

Write-Host "Checking npm..."
npm --version
if ($LASTEXITCODE -ne 0) {
    Write-Error "npm is installed but did not run successfully."
    exit $LASTEXITCODE
}

Push-Location $webRoot
try {
    Write-Host "Installing web dependencies with npm ci in $webRoot"
    npm ci
    if ($LASTEXITCODE -ne 0) {
        Write-Error "npm ci failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}

Write-Host "Web dependency setup complete. node_modules remains a local ignored folder and must not be committed."
exit 0
