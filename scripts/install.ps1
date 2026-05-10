param(
    [string] $AgentPlugins = $env:XUSHI_INSTALL_AGENT_PLUGINS,
    [string] $AgentSkills = $env:XUSHI_INSTALL_AGENT_SKILLS,
    [string] $OpenClawPluginsDir = $env:XUSHI_OPENCLAW_PLUGINS_DIR,
    [string] $OpenClawSkillsDir = $env:XUSHI_OPENCLAW_SKILLS_DIR,
    [string] $HermesSkillsDir = $env:XUSHI_HERMES_SKILLS_DIR
)

$ErrorActionPreference = "Stop"

$RepoSlug = $env:XUSHI_REPO_SLUG
if (-not $RepoSlug) {
    $RepoSlug = "Polaris-d/xushi"
}

$Version = $env:XUSHI_VERSION
if (-not $Version) {
    $Version = "latest"
}

$BinDir = $env:XUSHI_BIN_DIR
if (-not $BinDir) {
    $BinDir = $env:XUSHI_INSTALL_DIR
}
if (-not $BinDir) {
    $BinDir = Join-Path $env:USERPROFILE ".xushi\bin"
}

function Require-Command {
    param([string] $Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Get-PlatformTag {
    $archRaw = $env:PROCESSOR_ARCHITEW6432
    if (-not $archRaw) {
        $archRaw = $env:PROCESSOR_ARCHITECTURE
    }
    switch ($archRaw.ToLowerInvariant()) {
        "amd64" { $arch = "x64" }
        "x86_64" { $arch = "x64" }
        "arm64" { $arch = "arm64" }
        "aarch64" { $arch = "arm64" }
        default { throw "Unsupported CPU architecture: $archRaw" }
    }
    return "windows-$arch"
}

function Get-ReleaseUrl {
    param([string] $Asset)
    if ($Version -eq "latest") {
        return "https://github.com/$RepoSlug/releases/latest/download/$Asset"
    }
    return "https://github.com/$RepoSlug/releases/download/$Version/$Asset"
}

function Install-Binary {
    param(
        [string] $Name,
        [string] $PlatformTag
    )
    $asset = "$Name-$PlatformTag.exe"
    $url = Get-ReleaseUrl $asset
    $target = Join-Path $BinDir "$Name.exe"
    $temp = "$target.download"

    Write-Host "Downloading $asset"
    Invoke-WebRequest -Uri $url -OutFile $temp -UseBasicParsing
    Move-Item -Force -Path $temp -Destination $target
}

function Install-AgentSkills {
    if (-not $AgentSkills) {
        return
    }
    $args = @("skills", "install", "--targets", $AgentSkills)
    if ($OpenClawSkillsDir) {
        $args += @("--openclaw-skills-dir", $OpenClawSkillsDir)
    }
    if ($HermesSkillsDir) {
        $args += @("--hermes-skills-dir", $HermesSkillsDir)
    }
    & (Join-Path $BinDir "xushi.exe") @args
}

function Install-AgentPlugins {
    if (-not $AgentPlugins) {
        return
    }
    foreach ($target in ($AgentPlugins -split ",")) {
        switch ($target.Trim().ToLowerInvariant()) {
            "openclaw" {
                $args = @("plugins", "install", "openclaw")
                if ($OpenClawPluginsDir) {
                    $args += @("--openclaw-plugins-dir", $OpenClawPluginsDir)
                }
                & (Join-Path $BinDir "xushi.exe") @args
            }
            "" { }
            default { throw "Unsupported XUSHI_INSTALL_AGENT_PLUGINS target: $target" }
        }
    }
}

function Ensure-UserPath {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) {
        $userPath = ""
    }
    $paths = $userPath -split ";" | Where-Object { $_ }
    $alreadyConfigured = $false
    foreach ($path in $paths) {
        if ($path.TrimEnd("\") -ieq $BinDir.TrimEnd("\")) {
            $alreadyConfigured = $true
            break
        }
    }
    if (-not $alreadyConfigured) {
        $newPath = if ($userPath) { "$BinDir;$userPath" } else { $BinDir }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    }
    if ($env:Path -notlike "*$BinDir*") {
        $env:Path = "$BinDir;$env:Path"
    }
}

Require-Command Invoke-WebRequest

$platformTag = Get-PlatformTag
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

Install-Binary "xushi" $platformTag
Install-Binary "xushi-daemon" $platformTag
Ensure-UserPath
Install-AgentPlugins
Install-AgentSkills

& (Join-Path $BinDir "xushi.exe") init --show-token
& (Join-Path $BinDir "xushi.exe") doctor

Write-Host ""
Write-Host "xushi is installed into $BinDir."
Write-Host "Global command path has been configured for new PowerShell sessions."
if ($AgentPlugins) {
    Write-Host "Agent plugins installed for: $AgentPlugins"
}
if ($AgentSkills) {
    Write-Host "Agent skills installed for: $AgentSkills"
}
Write-Host "Start daemon:"
Write-Host "  xushi-daemon"
