$ErrorActionPreference = "Stop"

$Repo = $env:XUSHI_REPO
if (-not $Repo) {
    $Repo = "https://github.com/Polaris-d/xushi.git"
}

$InstallDir = $env:XUSHI_INSTALL_DIR
if (-not $InstallDir) {
    $InstallDir = Join-Path $env:USERPROFILE ".xushi\app"
}

function Require-Command {
    param([string] $Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

Require-Command git
Require-Command uv

if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Host "Updating xushi in $InstallDir"
    Push-Location $InstallDir
    git pull --ff-only
    Pop-Location
} elseif (Test-Path $InstallDir) {
    throw "Install directory exists but is not a git repository: $InstallDir"
} else {
    Write-Host "Installing xushi into $InstallDir"
    New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) | Out-Null
    git clone $Repo $InstallDir
}

Push-Location $InstallDir
uv sync
uv run xushi init --show-token
uv run xushi doctor
Pop-Location

Write-Host ""
Write-Host "xushi is installed."
Write-Host "Start daemon:"
Write-Host "  cd `"$InstallDir`""
Write-Host "  uv run xushi-daemon"
