#Requires -Version 5.1
<#
  One-click: optional git push + SSH to VPS: git pull + tools/ship.sh + tools/restart_master.sh.

  Usage (repo root):
    .\deploy.bat
    .\deploy.bat --bump-version
    .\deploy.bat --nopause

  Requires: deploy.env (see deploy.env.example), SSH key to VPS.
#>
param(
    [switch]$BumpVersion,
    [switch]$NoPause,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

foreach ($a in ($ExtraArgs | ForEach-Object { $_ })) {
    if ($a -eq "--bump-version" -or $a -eq "-bump-version") { $BumpVersion = $true }
    if ($a -eq "--nopause" -or $a -eq "-nopause") { $NoPause = $true }
}

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

function Read-DeployEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { return }
        $i = $line.IndexOf("=")
        if ($i -lt 1) { return }
        $k = $line.Substring(0, $i).Trim()
        $v = $line.Substring($i + 1).Trim()
        if ($k) { Set-Item -Path "Env:$k" -Value $v }
    }
}

$envFile = Join-Path $RepoRoot "deploy.env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Host "Missing deploy.env - copy deploy.env.example to deploy.env and set DEPLOY_SSH, DEPLOY_REMOTE_DIR, NODEADLINE_LOCAL_DEST." -ForegroundColor Yellow
    exit 1
}

Read-DeployEnv $envFile

function Expand-DeployPath {
    param([string]$P)
    if ([string]::IsNullOrWhiteSpace($P)) { return "" }
    $x = $P.Trim()
    if ($x -match "(?i)^%USERPROFILE%") {
        $x = $x -replace "(?i)^%USERPROFILE%", $env:USERPROFILE
    }
    if ($x.StartsWith("~") -or $x.StartsWith("~/") -or $x.StartsWith("~\")) {
        $rest = $x.Substring(1).TrimStart("/", "\")
        $x = Join-Path $env:USERPROFILE $rest
    }
    return $x
}

function Resolve-SshIdentityPath {
    $raw = $env:DEPLOY_SSH_IDENTITY
    if ([string]::IsNullOrWhiteSpace($raw)) {
        $def = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
        if (Test-Path -LiteralPath $def) { return (Resolve-Path -LiteralPath $def).Path }
        return $null
    }
    $p = Expand-DeployPath $raw
    if (-not (Test-Path -LiteralPath $p)) {
        throw "DEPLOY_SSH_IDENTITY not found: $p"
    }
    return (Resolve-Path -LiteralPath $p).Path
}

$ssh = $env:DEPLOY_SSH
if (-not $ssh) { throw "deploy.env: set DEPLOY_SSH (user@host)" }
$remoteDir = $env:DEPLOY_REMOTE_DIR
if (-not $remoteDir) { throw "deploy.env: set DEPLOY_REMOTE_DIR" }
$localDest = $env:NODEADLINE_LOCAL_DEST
if (-not $localDest) { throw "deploy.env: set NODEADLINE_LOCAL_DEST (nginx public dir on VPS)" }
$branch = if ($env:DEPLOY_BRANCH) { $env:DEPLOY_BRANCH } else { "main" }
$doPush = $true
if ($env:DEPLOY_GIT_PUSH -eq "0") { $doPush = $false }

$shipExtra = ""
if ($BumpVersion) { $shipExtra = "--bump-version" }

$identityPath = Resolve-SshIdentityPath

Write-Host "==> repo: $RepoRoot"
Write-Host "==> SSH: $ssh"
if ($identityPath) { Write-Host "==> SSH identity: $identityPath" }
Write-Host "==> remote: $remoteDir (branch $branch) -> NODEADLINE_LOCAL_DEST=$localDest"
if ($shipExtra) { Write-Host "==> ship: $shipExtra" }

if ($doPush) {
    Write-Host ""
    Write-Host "==> git push origin HEAD"
    git push origin HEAD
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed: commit changes or set DEPLOY_GIT_PUSH=0 in deploy.env"
    }
} else {
    Write-Host ""
    Write-Host "==> git push skipped (DEPLOY_GIT_PUSH=0)"
}

# Avoid expandable here-strings (encoding/substitution issues on PS 5.1): placeholders + pipe to bash.
$remoteScript = @'
set -euo pipefail
cd __REMOTE_DIR__
git fetch origin
git pull origin __BRANCH__
export NODEADLINE_LOCAL_DEST=__LOCAL_DEST__
./tools/ship.sh __SHIP_EXTRA__
./tools/restart_master.sh
echo OK_remote_ship
'@
$remoteScript = $remoteScript.Replace("__REMOTE_DIR__", $remoteDir).Replace("__BRANCH__", $branch).Replace("__LOCAL_DEST__", $localDest).Replace("__SHIP_EXTRA__", $shipExtra.Trim())

Write-Host ""
Write-Host "==> SSH: git pull + ship.sh + restart_master.sh"
$sshArgs = @()
if ($identityPath) {
    $sshArgs += "-i", $identityPath
    $sshArgs += "-o", "IdentitiesOnly=yes"
}
$sshArgs += $ssh, "bash", "-s"
$remoteScript | & ssh @sshArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "SSH failed. Check key, host, paths on server." -ForegroundColor Red
    if (-not $NoPause) { $null = Read-Host "Press Enter" }
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done. Nodes pull payload in about 30-90s; /site/ updates when site_channel bundle_sha256 changes." -ForegroundColor Green
if (-not $NoPause) {
    $null = Read-Host "Press Enter to close"
}
