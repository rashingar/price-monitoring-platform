$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$NodeVersion = "22.12.0"
$NodeFolderName = "node-v$NodeVersion-win-x64"
$ToolsDir = Join-Path $RepoRoot ".tools"
$LocalNodeDir = Join-Path $ToolsDir $NodeFolderName
$LocalNodeExe = Join-Path $LocalNodeDir "node.exe"
$LocalNpmCmd = Join-Path $LocalNodeDir "npm.cmd"

function Get-CommandPath {
  param([string] $Name)

  $Command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($Command) {
    return $Command.Source
  }

  return $null
}

function Use-LocalNode {
  $env:PATH = "$LocalNodeDir;$env:PATH"
}

Set-Location $RepoRoot

$NodePath = Get-CommandPath "node.exe"
$NpmPath = Get-CommandPath "npm.cmd"

if (-not $NodePath -or -not $NpmPath) {
  if (-not (Test-Path $LocalNodeExe) -or -not (Test-Path $LocalNpmCmd)) {
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

    $ZipPath = Join-Path $ToolsDir "$NodeFolderName.zip"
    $NodeUrl = "https://nodejs.org/dist/v$NodeVersion/$NodeFolderName.zip"

    Write-Host "Node/npm were not found on PATH."
    Write-Host "Downloading portable Node.js $NodeVersion to $ToolsDir ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $NodeUrl -OutFile $ZipPath -UseBasicParsing

    Write-Host "Extracting portable Node.js ..."
    Expand-Archive -Path $ZipPath -DestinationPath $ToolsDir -Force
    Remove-Item $ZipPath -Force
  }

  Use-LocalNode
  $NodePath = $LocalNodeExe
  $NpmPath = $LocalNpmCmd
} else {
  Write-Host "Using Node from PATH: $NodePath"
  Write-Host "Using npm from PATH: $NpmPath"
}

if (-not (Test-Path (Join-Path $RepoRoot ".env")) -and (Test-Path (Join-Path $RepoRoot ".env.example"))) {
  Copy-Item (Join-Path $RepoRoot ".env.example") (Join-Path $RepoRoot ".env")
  Write-Host "Created .env from .env.example"
}

Write-Host "Node version:"
& $NodePath --version
Write-Host "npm version:"
& $NpmPath --version

Write-Host "Installing frontend dependencies ..."
if (Test-Path (Join-Path $RepoRoot "package-lock.json")) {
  & $NpmPath ci
} else {
  Write-Host "package-lock.json was not found; falling back to npm install."
  & $NpmPath install
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Run dev-windows.cmd to start the Vite dev server."
