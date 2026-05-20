param(
    [switch]$Staged
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$webNodeModules = Join-Path $repoRoot "apps\web\node_modules"
$blackPaths = @(
    "apps\ecommerce-api",
    "apps\product-factory-api",
    "scripts"
)
$failures = 0

function Invoke-HygieneCheck {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Check
    )

    Write-Host ""
    Write-Host "== $Name =="
    try {
        & $Check
        Write-Host "OK: $Name"
    }
    catch {
        $script:failures += 1
        Write-Host "FAIL: $Name"
        Write-Host $_.Exception.Message
    }
}

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

function Get-CheckedPaths {
    if ($Staged) {
        return @(git diff --cached --name-only --diff-filter=ACMRT)
    }
    return @(git ls-files)
}

function Test-PathPattern {
    param(
        [string[]]$Paths = @(),
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][string[]]$Patterns
    )

    $matches = New-Object System.Collections.Generic.List[string]
    foreach ($path in $Paths) {
        $normalized = $path -replace "\\", "/"
        foreach ($pattern in $Patterns) {
            if ($normalized -match $pattern) {
                $matches.Add($path) | Out-Null
                break
            }
        }
    }

    if ($matches.Count -gt 0) {
        $display = ($matches | Sort-Object -Unique) -join "`n  "
        throw "$Description found:`n  $display"
    }
}

function Test-NoGitlinksUnderApps {
    $gitlinks = @(
        git ls-files -s apps |
            Where-Object { $_ -match "^160000\s" } |
            ForEach-Object { ($_ -split "\s+", 4)[3] }
    )
    if ($gitlinks.Count -gt 0) {
        throw "Gitlink/submodule entries under apps are not allowed:`n  $($gitlinks -join "`n  ")"
    }
}

function Test-NoNestedGitDirsUnderApps {
    $nested = @(
        Get-ChildItem -LiteralPath (Join-Path $repoRoot "apps") -Force -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq ".git" } |
            ForEach-Object { $_.FullName.Substring($repoRoot.Length + 1) }
    )
    if ($nested.Count -gt 0) {
        throw "Nested .git filesystem entries under apps are not allowed:`n  $($nested -join "`n  ")"
    }
}

$paths = @(Get-CheckedPaths)
$scope = if ($Staged) { "staged files" } else { "tracked files" }

Write-Host "Running monorepo hygiene checks from $repoRoot"
Write-Host "Path scope: $scope"
Write-Host "This script does not start servers and does not mutate the database."

Invoke-HygieneCheck "No gitlinks under apps" {
    Test-NoGitlinksUnderApps
}

Invoke-HygieneCheck "No nested .git entries under apps" {
    Test-NoNestedGitDirsUnderApps
}

Invoke-HygieneCheck "No unsafe tracked paths" {
    Test-PathPattern -Paths $paths -Description "Unsafe path(s)" -Patterns @(
        "(^|/)\.env$",
        "(^|/)\.env\.(?!example$).+",
        "(^|/)\.secrets($|/)",
        "(^|/)\.venv($|/)",
        "(^|/)node_modules($|/)",
        "(^|/)work($|/)",
        "(^|/)output($|/)",
        "(^|/)products($|/)",
        "\.(db|sqlite|dump|backup|pem|key)$",
        "(^|/)(raw|capture|captures|html-capture|html-captures)(/|$)",
        "(^|/)(raw|capture|captures|html-capture|html-captures)[^/]*\.html$",
        "(^|/)[^/]*(raw-provider|provider-raw|provider-capture|provider-html-capture)[^/]*\.html$"
    )
}

Invoke-HygieneCheck "Black formatting" {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Missing root virtual environment Python: $python. Run: .\scripts\setup\root-venv.ps1; .\scripts\setup\python-deps.ps1"
    }
    Push-Location $repoRoot
    try {
        Invoke-NativeCommand { & $python -m black --check @blackPaths } "Black formatting check failed."
    }
    finally {
        Pop-Location
    }
}

Invoke-HygieneCheck "Mirrored OpenAPI contracts" {
    Invoke-NativeCommand { & (Join-Path $repoRoot "scripts\contracts\check.ps1") -SkipWebTypes } "Mirrored OpenAPI contract check failed."
}

if (Test-Path -LiteralPath $webNodeModules) {
    Invoke-HygieneCheck "Generated web API types" {
        Invoke-NativeCommand { & (Join-Path $repoRoot "scripts\contracts\check-web-types.ps1") -SkipMirrorCheck } "Generated web API type freshness check failed."
    }
} else {
    Write-Host ""
    Write-Host "== Generated web API types =="
    Write-Host "SKIP: apps\web\node_modules is missing, so generated web API type freshness cannot be checked."
}

Invoke-HygieneCheck "Git diff whitespace" {
    if ($Staged) {
        Invoke-NativeCommand { git diff --cached --check } "git diff --cached --check failed."
    } else {
        Invoke-NativeCommand { git diff --check } "git diff --check failed."
    }
}

Write-Host ""
if ($failures -gt 0) {
    Write-Host "Monorepo hygiene failed: $failures check(s) need attention."
    exit 1
}

Write-Host "Monorepo hygiene passed."
exit 0
