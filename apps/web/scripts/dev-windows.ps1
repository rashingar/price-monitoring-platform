$ErrorActionPreference = "Stop"

$AppRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $AppRoot "..\..")).Path
$ToolsDir = Join-Path $AppRoot ".tools"
$EnvLoader = Join-Path $RepoRoot "scripts\dev\load-root-env.ps1"

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

Set-Location $AppRoot

$NpmCommand = Get-NpmCommand
if (-not $NpmCommand) {
  Write-Host "npm was not found. Run setup-windows.cmd first."
  exit 1
}

& $EnvLoader -RepoRoot $RepoRoot -DeprecatedAppEnvPath (Join-Path $AppRoot ".env") | Out-Null

if (-not (Test-Path (Join-Path $AppRoot "node_modules"))) {
  Write-Host "node_modules is missing. Installing dependencies first ..."
  & $NpmCommand install
}

Write-Host "Starting Vite dev server ..."
& $NpmCommand run dev -- --host 127.0.0.1 @args
