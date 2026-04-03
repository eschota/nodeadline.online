#Requires -Version 5.1
# Заливает локальный public/ на сервер в каталог репозитория (как в deploy.env), чтобы затем
# на VPS сработал ./tools/ship.sh (rsync в nginx, build_site_channel при необходимости).
# Требует: deploy.env с DEPLOY_SSH, DEPLOY_REMOTE_DIR; опционально DEPLOY_SSH_IDENTITY.
param([string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path)

$ErrorActionPreference = "Stop"
function Read-DeployEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { throw "Missing $Path" }
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
Read-DeployEnv $envFile
$ssh = $env:DEPLOY_SSH
$remoteDir = $env:DEPLOY_REMOTE_DIR
if (-not $ssh -or -not $remoteDir) { throw "deploy.env: DEPLOY_SSH and DEPLOY_REMOTE_DIR required" }

function Expand-DeployPath {
    param([string]$P)
    if ([string]::IsNullOrWhiteSpace($P)) { return "" }
    $x = $P.Trim()
    if ($x -match "(?i)^%USERPROFILE%") { $x = $x -replace "(?i)^%USERPROFILE%", $env:USERPROFILE }
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
    if (-not (Test-Path -LiteralPath $p)) { throw "DEPLOY_SSH_IDENTITY not found: $p" }
    return (Resolve-Path -LiteralPath $p).Path
}

$identityPath = Resolve-SshIdentityPath
$dest = "${ssh}:${remoteDir}/public/"
$src = Join-Path $RepoRoot "public"
Write-Host "==> scp -r $src/. -> $dest"

$scpArgs = @("-o", "BatchMode=yes")
if ($identityPath) {
    $scpArgs += "-i", $identityPath, "-o", "IdentitiesOnly=yes"
}
$scpArgs += "-r", "$src/.", $dest
& scp @scpArgs
if ($LASTEXITCODE -ne 0) { throw "scp failed (exit $LASTEXITCODE)" }
Write-Host "OK: public synced to server repo."
