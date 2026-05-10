param(
    [string] $AgentSkills = $env:XUSHI_INSTALL_AGENT_SKILLS,
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

function Install-XushiSkillsPackage {
    param(
        [string] $Name,
        [string] $SkillsDir
    )
    $target = Join-Path $skillsDir "xushi-skills"
    $tempDir = Join-Path $skillsDir ".xushi-skills-download"
    $archive = Join-Path $skillsDir "xushi-skills.zip"
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $url = Get-ReleaseUrl "xushi-skills.zip"

    Write-Host "Installing xushi-skills for $Name"
    New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null
    if (Test-Path $tempDir) {
        Remove-Item -Recurse -Force -LiteralPath $tempDir
    }
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
    Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
    Expand-Archive -Force -Path $archive -DestinationPath $tempDir
    if (-not (Test-Path (Join-Path $tempDir "xushi-skills\SKILL.md"))) {
        throw "Invalid xushi-skills archive: missing SKILL.md"
    }
    if (Test-Path $target) {
        Move-Item -Force -Path $target -Destination (Join-Path $skillsDir "xushi-skills.backup-$timestamp")
    }
    Move-Item -Force -Path (Join-Path $tempDir "xushi-skills") -Destination $target
    Remove-Item -Recurse -Force -LiteralPath $tempDir
    Remove-Item -Force -LiteralPath $archive
}

function Install-XushiSkillsForOpenClaw {
    $skillsDir = $OpenClawSkillsDir
    if (-not $skillsDir) {
        $skillsDir = $env:OPENCLAW_SKILLS_DIR
    }
    if (-not $skillsDir) {
        $openclawHome = $env:OPENCLAW_HOME
        if (-not $openclawHome) {
            $openclawHome = Join-Path $env:USERPROFILE ".openclaw"
        }
        $skillsDir = Join-Path $openclawHome "skills"
    }
    Install-XushiSkillsPackage "OpenClaw" $skillsDir
}

function Install-XushiSkillsForHermes {
    $skillsDir = $HermesSkillsDir
    if (-not $skillsDir) {
        $skillsDir = $env:HERMES_SKILLS_DIR
    }
    if (-not $skillsDir) {
        $hermesHome = $env:HERMES_HOME
        if (-not $hermesHome) {
            $hermesHome = Join-Path $env:USERPROFILE ".hermes"
        }
        $skillsDir = Join-Path $hermesHome "skills"
    }
    Install-XushiSkillsPackage "Hermes" $skillsDir
}

function Install-AgentSkills {
    if (-not $AgentSkills) {
        return
    }
    foreach ($target in ($AgentSkills -split ",")) {
        switch ($target.Trim().ToLowerInvariant()) {
            "openclaw" { Install-XushiSkillsForOpenClaw }
            "hermes" { Install-XushiSkillsForHermes }
            "" { }
            default { throw "Unsupported XUSHI_INSTALL_AGENT_SKILLS target: $target" }
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
Install-AgentSkills

& (Join-Path $BinDir "xushi.exe") init --show-token
& (Join-Path $BinDir "xushi.exe") doctor

Write-Host ""
Write-Host "xushi is installed into $BinDir."
Write-Host "Global command path has been configured for new PowerShell sessions."
if ($AgentSkills) {
    Write-Host "Agent skills installed for: $AgentSkills"
}
Write-Host "Start daemon:"
Write-Host "  xushi-daemon"
