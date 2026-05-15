param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$DeprecatedAppEnvPath,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

function Read-EnvFileEntries {
    param([Parameter(Mandatory = $true)][string]$Path)

    $entries = [ordered]@{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $entries
    }

    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }

        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        if ($key -notmatch "^[A-Za-z_][A-Za-z0-9_]*$") {
            continue
        }

        $value = $parts[1].Trim()
        if ($value.Length -ge 2) {
            $first = $value.Substring(0, 1)
            $last = $value.Substring($value.Length - 1, 1)
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        $entries[$key] = $value
    }

    return $entries
}

function Set-MissingEnvValues {
    param(
        [Parameter(Mandatory = $true)]$Entries,
        [Parameter(Mandatory = $true)][string]$Source,
        [string[]]$BlockedKeys = @()
    )

    $loaded = New-Object System.Collections.Generic.List[string]
    $skippedExisting = New-Object System.Collections.Generic.List[string]
    $skippedDuplicate = New-Object System.Collections.Generic.List[string]

    foreach ($key in $Entries.Keys) {
        if ($BlockedKeys -contains $key) {
            $skippedDuplicate.Add($key) | Out-Null
            continue
        }
        if ($null -ne [Environment]::GetEnvironmentVariable($key, "Process")) {
            $skippedExisting.Add($key) | Out-Null
            continue
        }
        Set-Item -Path "Env:$key" -Value $Entries[$key]
        $loaded.Add($key) | Out-Null
    }

    if (-not $Quiet) {
        if ($loaded.Count -gt 0) {
            Write-Host "Loaded $Source env keys: $($loaded -join ', ')"
        }
        if ($skippedExisting.Count -gt 0) {
            Write-Host "Skipped $Source env keys already set by OS/process env: $($skippedExisting -join ', ')"
        }
        if ($skippedDuplicate.Count -gt 0) {
            Write-Host "Skipped deprecated app-local duplicate env keys because repo-root .env is preferred: $($skippedDuplicate -join ', ')"
        }
    }

    return [pscustomobject]@{
        loaded = @($loaded)
        skipped_existing = @($skippedExisting)
        skipped_duplicate = @($skippedDuplicate)
    }
}

$rootEnvPath = Join-Path $RepoRoot ".env"
$rootEntries = Read-EnvFileEntries -Path $rootEnvPath
$rootResult = Set-MissingEnvValues -Entries $rootEntries -Source "repo-root"

$appResult = $null
if ($DeprecatedAppEnvPath -and (Test-Path -LiteralPath $DeprecatedAppEnvPath)) {
    if (-not $Quiet) {
        Write-Warning "Deprecated app-local .env detected at $DeprecatedAppEnvPath. Move values to repo-root .env. OS env vars still override both; repo-root .env is preferred."
    }
    $appEntries = Read-EnvFileEntries -Path $DeprecatedAppEnvPath
    $appResult = Set-MissingEnvValues -Entries $appEntries -Source "deprecated app-local" -BlockedKeys @($rootEntries.Keys)
}

[pscustomobject]@{
    repo_root_env = $rootEnvPath
    root_loaded_keys = @($rootResult.loaded)
    root_skipped_existing_keys = @($rootResult.skipped_existing)
    deprecated_app_env = $DeprecatedAppEnvPath
    deprecated_app_detected = [bool]($DeprecatedAppEnvPath -and (Test-Path -LiteralPath $DeprecatedAppEnvPath))
    deprecated_app_loaded_keys = if ($appResult) { @($appResult.loaded) } else { @() }
    deprecated_app_skipped_existing_keys = if ($appResult) { @($appResult.skipped_existing) } else { @() }
    deprecated_app_skipped_duplicate_keys = if ($appResult) { @($appResult.skipped_duplicate) } else { @() }
}
