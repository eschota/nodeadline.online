#Requires -Version 5.1
<#
  Локальная выкладка без SSH: сборка payload + rsync public/ в каталог nginx (eschota.nodeadline.online и т.д.) + verify.

  В корне репозитория:
    deploy_local.bat
    deploy_local.bat --bump-version
    deploy_local.bat --nopause

  Нужен deploy_local.env (см. deploy_local.env.example): NODEADLINE_LOCAL_DEST — Windows-путь к docroot public.
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
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Read-DeployEnvFile {
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

function ConvertTo-GitBashPath {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Path not found: $Path"
    }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $resolved = $resolved -replace '\\', '/'
    if ($resolved -match '^([A-Za-z]):') {
        $d = $Matches[1].ToLower()
        $rest = $resolved.Substring(2).TrimStart('/')
        return "${d}:/${rest}"
    }
    return $resolved
}

function Resolve-GitBash {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Git\bin\bash.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Git\bin\bash.exe")
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    $cmd = Get-Command bash -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    throw "bash not found. Install Git for Windows or add Git\bin to PATH."
}

$envFile = Join-Path $RepoRoot "deploy_local.env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Host "Missing deploy_local.env - copy deploy_local.env.example to deploy_local.env and set NODEADLINE_LOCAL_DEST." -ForegroundColor Yellow
    exit 1
}

Read-DeployEnvFile $envFile

$localDest = $env:NODEADLINE_LOCAL_DEST
if ([string]::IsNullOrWhiteSpace($localDest)) {
    throw "deploy_local.env: set NODEADLINE_LOCAL_DEST (Windows path to nginx public dir)"
}

$env:NODEADLINE_RSYNC_NO_SUDO = "1"
$env:NODEADLINE_LOCAL_DEST = ConvertTo-GitBashPath $localDest.Trim()

if (-not $env:NODEADLINE_VERIFY_BASE) {
    $env:NODEADLINE_VERIFY_BASE = "https://eschota.nodeadline.online"
}

$bash = Resolve-GitBash
$repoBash = ConvertTo-GitBashPath $RepoRoot

Write-Host "==> repo: $RepoRoot"
Write-Host "==> NODEADLINE_LOCAL_DEST=$($env:NODEADLINE_LOCAL_DEST)"
Write-Host "==> NODEADLINE_VERIFY_BASE=$($env:NODEADLINE_VERIFY_BASE)"
if ($BumpVersion) { Write-Host "==> ship: --bump-version" }

$ship = "./tools/ship.sh"
if ($BumpVersion) { $ship = "./tools/ship.sh --bump-version" }

Write-Host ""
Write-Host '==> ship (local, no SSH)'
$bashCmd = ('cd "{0}"; {1}' -f $repoBash, $ship)
& $bash -lc $bashCmd
if ($LASTEXITCODE -ne 0) {
    if (-not $NoPause) { $null = Read-Host "Press Enter" }
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host 'Done. Other nodes pull payload from master on schedule; /site/ updates when site_channel bundle_sha256 changes.' -ForegroundColor Green
if (-not $NoPause) {
    $null = Read-Host "Press Enter to close"
}
