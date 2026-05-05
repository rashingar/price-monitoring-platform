$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $RepoRoot ".tools"

function Get-LocalNodeDir {
  if (-not (Test-Path $ToolsDir)) {
    return $null
  }

  $NodeDir = Get-ChildItem -Path $ToolsDir -Directory -Filter "node-v*-win-x64" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

  if ($NodeDir) {
    return $NodeDir.FullName
  }

  return $null
}

function Get-NpmCommand {
  $LocalNodeDir = Get-LocalNodeDir
  if ($LocalNodeDir) {
    $LocalNpm = Join-Path $LocalNodeDir "npm.cmd"
    if (Test-Path $LocalNpm) {
      $env:PATH = "$LocalNodeDir;$env:PATH"
      return $LocalNpm
    }
  }

  $Npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
  if ($Npm) {
    return $Npm.Source
  }

  return $null
}

Set-Location $RepoRoot

$NpmCommand = Get-NpmCommand
if (-not $NpmCommand) {
  Write-Host "npm was not found. Run setup-windows.cmd first."
  exit 1
}

if (-not (Test-Path (Join-Path $RepoRoot ".env")) -and (Test-Path (Join-Path $RepoRoot ".env.example"))) {
  Copy-Item (Join-Path $RepoRoot ".env.example") (Join-Path $RepoRoot ".env")
}

if (-not (Test-Path (Join-Path $RepoRoot "node_modules"))) {
  Write-Host "node_modules is missing. Installing dependencies first ..."
  & $NpmCommand install
}

Write-Host "Starting Vite dev server ..."
& $NpmCommand run dev -- --host 127.0.0.1 @args
