$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$maxJsonBytes = 128KB
$allowlistPath = Join-Path $PSScriptRoot "snapshot-allowlist.json"
$snapshotDirs = @(
    "apps\product-factory-api\src\product_factory\tests\fixtures\golden_snapshots",
    "apps\ecommerce-api\tests\fixtures\golden_snapshots"
)

function ConvertTo-RepoRelativePath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = (Resolve-Path -LiteralPath $Path).Path
    return $fullPath.Substring($repoRoot.Length + 1) -replace "\\", "/"
}

function Read-LargeSnapshotAllowlist {
    if (-not (Test-Path -LiteralPath $allowlistPath)) {
        return @()
    }

    try {
        $raw = Get-Content -LiteralPath $allowlistPath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return @()
        }

        $parsed = $raw | ConvertFrom-Json
        if ($parsed -is [array]) {
            return @($parsed | ForEach-Object { ([string]$_) -replace "\\", "/" })
        }
        if ($null -ne $parsed.large_files) {
            return @($parsed.large_files | ForEach-Object { ([string]$_) -replace "\\", "/" })
        }
        return @()
    }
    catch {
        throw "Invalid snapshot allowlist JSON at ${allowlistPath}: $($_.Exception.Message)"
    }
}

$largeSnapshotAllowlist = @(Read-LargeSnapshotAllowlist)
$failures = New-Object System.Collections.Generic.List[string]
$checkedFiles = 0

foreach ($relativeDir in $snapshotDirs) {
    $snapshotDir = Join-Path $repoRoot $relativeDir
    if (-not (Test-Path -LiteralPath $snapshotDir)) {
        Write-Host "SKIP: $relativeDir does not exist."
        continue
    }

    Write-Host "Scanning golden snapshots in $relativeDir"
    $files = @(
        Get-ChildItem -LiteralPath $snapshotDir -Recurse -File -ErrorAction Stop |
            Where-Object { $_.Extension -ieq ".json" }
    )

    foreach ($file in $files) {
        $checkedFiles += 1
        $relativePath = ConvertTo-RepoRelativePath -Path $file.FullName

        if (($file.Length -gt $maxJsonBytes) -and ($largeSnapshotAllowlist -notcontains $relativePath)) {
            $failures.Add("${relativePath}: JSON snapshot is $($file.Length) bytes, above $maxJsonBytes bytes. Add a focused fixture or explicitly allowlist it in scripts/test/snapshot-allowlist.json.") | Out-Null
        }

        try {
            $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
        }
        catch {
            $failures.Add("${relativePath}: unable to read as UTF-8 text: $($_.Exception.Message)") | Out-Null
            continue
        }

        try {
            $null = $content | ConvertFrom-Json
        }
        catch {
            $failures.Add("${relativePath}: invalid JSON: $($_.Exception.Message)") | Out-Null
        }

        $patterns = @(
            @{ Reason = "contains a Windows absolute path"; Pattern = "(?i)\b[A-Z]:\\" },
            @{ Reason = "contains a repo-local temp path fragment"; Pattern = "(?i)(/tmp/|\\Temp\\|\\\\Temp\\\\|AppData\\Local\\Temp|AppData\\\\Local\\\\Temp)" },
            @{ Reason = "contains an obvious secret-bearing key"; Pattern = '(?i)"(authorization|cookie|set-cookie|api_key|access_token|refresh_token|password)"\s*:' }
        )

        foreach ($pattern in $patterns) {
            if ($content -match $pattern.Pattern) {
                $failures.Add("${relativePath}: $($pattern.Reason).") | Out-Null
            }
        }
    }
}

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "Golden snapshot hygiene failed:"
    foreach ($failure in $failures) {
        Write-Host "  - $failure"
    }
    exit 1
}

Write-Host "Golden snapshot hygiene passed. Checked $checkedFiles JSON snapshot file(s)."
exit 0
