$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$forbiddenMarkers = @(
    "runtime",
    "db_integration",
    "postgres_required",
    "external",
    "e2e",
    "legacy",
    "slow"
)

function Write-RootVenvSetupInstructions {
    Write-Host "Root Python setup commands from the repository root:"
    Write-Host "python --version"
    Write-Host "python -m venv .venv"
    Write-Host ".\.venv\Scripts\python.exe --version"
    Write-Host ".\.venv\Scripts\python.exe -m pip install -r apps\product-factory-api\requirements.txt"
    Write-Host ".\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps"
    Write-Host ".\.venv\Scripts\python.exe -m pip install -r apps\ecommerce-api\requirements-lock.txt"
    Write-Host ".\.venv\Scripts\python.exe -m pip install -e apps\ecommerce-api --no-deps"
    Write-Host "Python 3.11 or newer is required. If python is missing or too old, install a supported Python version and reopen PowerShell."
}

if (-not (Test-Path -LiteralPath $python)) {
    Write-RootVenvSetupInstructions
    Write-Error "Missing root virtual environment Python: $python"
    exit 1
}

$helperCode = @'
import argparse
import os
import sys

import pytest


class FastMarkerHygienePlugin:
    def __init__(self, forbidden):
        self.forbidden = set(forbidden)
        self.violations = []
        self.selected_count = 0

    def pytest_collection_finish(self, session):
        self.selected_count = len(session.items)
        for item in session.items:
            marker_names = {marker.name for marker in item.iter_markers()}
            forbidden = sorted(marker_names & self.forbidden)
            if forbidden:
                self.violations.append((item.nodeid, forbidden))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", required=True)
    parser.add_argument("--config")
    parser.add_argument("--expression", required=True)
    parser.add_argument("--test-path", required=True)
    parser.add_argument("--forbidden", required=True, nargs="+")
    args = parser.parse_args()

    os.chdir(args.app_root)
    plugin = FastMarkerHygienePlugin(args.forbidden)
    pytest_args = [
        "--collect-only",
        "-vv",
        "-ra",
        "--color=no",
        "-m",
        args.expression,
        args.test_path,
    ]
    if args.config:
        pytest_args.extend(["-c", args.config])

    print("Collecting pytest items without running tests:")
    print("  python -m pytest " + " ".join(pytest_args))
    exit_code = pytest.main(pytest_args, plugins=[plugin])
    print(f"Selected {plugin.selected_count} item(s) for fast marker hygiene.")

    if plugin.violations:
        print("")
        print("Forbidden markers were selected by the fast profile:")
        for nodeid, markers in plugin.violations:
            print(f"  - {nodeid}: {', '.join(markers)}")
        return 20

    if exit_code != 0:
        return exit_code

    print("No forbidden markers were selected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'@

$helperPath = New-TemporaryFile

function Invoke-FastMarkerCheck {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$AppRoot,
        [string]$ConfigPath,
        [Parameter(Mandatory = $true)][string]$TestPath,
        [Parameter(Mandatory = $true)][string]$Expression
    )

    Write-Host ""
    Write-Host "== $Name fast marker hygiene =="
    if ($ConfigPath) {
        & $python $helperPath --app-root $AppRoot --config $ConfigPath --expression $Expression --test-path $TestPath --forbidden $forbiddenMarkers
    }
    else {
        & $python $helperPath --app-root $AppRoot --expression $Expression --test-path $TestPath --forbidden $forbiddenMarkers
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "$Name fast marker hygiene failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

try {
    Set-Content -LiteralPath $helperPath -Value $helperCode -Encoding UTF8

    $productFactoryRoot = Join-Path $repoRoot "apps\product-factory-api"
    $productFactorySrc = Join-Path $productFactoryRoot "src"
    $ecommerceRoot = Join-Path $repoRoot "apps\ecommerce-api"
    $ecommerceSrc = Join-Path $ecommerceRoot "src"

    Invoke-FastMarkerCheck `
        -Name "Product Factory" `
        -AppRoot $productFactoryRoot `
        -ConfigPath (Join-Path $productFactorySrc "pytest.ini") `
        -TestPath "src\product_factory\tests" `
        -Expression "not slow and not external and not e2e and not legacy and not runtime"

    $oldPythonPath = $env:PYTHONPATH
    try {
        if ($env:PYTHONPATH) {
            $env:PYTHONPATH = "$ecommerceSrc;$ecommerceRoot;$env:PYTHONPATH"
        }
        else {
            $env:PYTHONPATH = "$ecommerceSrc;$ecommerceRoot"
        }

        Invoke-FastMarkerCheck `
            -Name "Ecommerce API" `
            -AppRoot $ecommerceRoot `
            -TestPath "tests" `
            -Expression "not slow and not external and not e2e and not legacy and not runtime and not db_integration and not postgres_required"
    }
    finally {
        $env:PYTHONPATH = $oldPythonPath
    }
}
finally {
    Remove-Item -LiteralPath $helperPath -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Fast marker hygiene passed."
exit 0
