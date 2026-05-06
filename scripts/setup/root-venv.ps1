param(
    [switch]$Force,
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$venvRoot = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Command,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage Exit code: $LASTEXITCODE"
    }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "python was not found on PATH. Install Python 3.11 or newer, reopen PowerShell, and rerun this script."
    exit 1
}

Write-Host "Checking system Python..."
Invoke-NativeCommand { python --version } "python --version failed."

$versionCheck = @'
import sys
if sys.version_info < (3, 11):
    print(f'Python 3.11 or newer is required; found {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}.')
    sys.exit(1)
print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')
'@

$pythonVersion = @(python -c $versionCheck)
if ($LASTEXITCODE -ne 0) {
    Write-Error ($pythonVersion -join "`n")
    exit $LASTEXITCODE
}
Write-Host "System Python version: $($pythonVersion[-1])"

if ((Test-Path -LiteralPath $venvRoot) -and -not ($Force -or $Recreate)) {
    Write-Host "Root .venv already exists: $venvRoot"
    Write-Host "Use -Force or -Recreate to delete and recreate it."
} else {
    if (Test-Path -LiteralPath $venvRoot) {
        $resolvedVenv = (Resolve-Path -LiteralPath $venvRoot).Path
        if (-not $resolvedVenv.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            Write-Error "Refusing to remove .venv outside repository root: $resolvedVenv"
            exit 1
        }
        Write-Host "Removing existing root .venv: $resolvedVenv"
        Remove-Item -LiteralPath $resolvedVenv -Recurse -Force
    }

    Write-Host "Creating root .venv at $venvRoot"
    Invoke-NativeCommand { python -m venv $venvRoot } "Failed to create root .venv."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Error "Root .venv Python is missing after setup: $venvPython"
    exit 1
}

Write-Host "Root .venv Python:"
Invoke-NativeCommand { & $venvPython --version } "Root .venv Python is not runnable."
Write-Host "Root .venv setup complete. App dependencies were not installed by this script."
exit 0
