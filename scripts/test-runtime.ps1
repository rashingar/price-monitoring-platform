$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$appRoot = Join-Path $repoRoot "apps\product-factory-api"

Set-Location $appRoot
& ..\..\.venv\Scripts\python.exe -m pytest -vv -c src\pytest.ini -m "runtime or integration or job_lifecycle"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

exit 0
