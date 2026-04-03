# Build installers into public/downloads/ (names from public/version.json semver).
# Windows: CGO on (tray). Linux/Darwin: CGO off.
# Requires: Go, Python on PATH (or standard py launcher), repo root as cwd or pass -RepoRoot.
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $RepoRoot "apps\installer")

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher py not found. Install Python 3 or add to PATH."
}
$verLine = py -3 -c "import json; from pathlib import Path; print(json.loads((Path(r'$RepoRoot') / 'public' / 'version.json').read_text(encoding='utf-8'))['version'])"
$base = ($verLine.Trim().Split("-")[0]).Trim().Replace("/", "-")
$out = Join-Path $RepoRoot "public\downloads"
New-Item -ItemType Directory -Force -Path $out | Out-Null

$win = "nodeadline-installer-windows-amd64-v$base.exe"
$lin = "nodeadline-installer-linux-amd64-v$base"
$dar = "nodeadline-installer-darwin-arm64-v$base"

Write-Host "build_installers.ps1: version=$base -> $out"

$env:CGO_ENABLED = "1"
Remove-Item Env:GOOS -ErrorAction SilentlyContinue
Remove-Item Env:GOARCH -ErrorAction SilentlyContinue
go build -trimpath -ldflags "-s -w" -o (Join-Path $out $win) .

$env:GOOS = "linux"
$env:GOARCH = "amd64"
$env:CGO_ENABLED = "0"
go build -trimpath -ldflags "-s -w" -o (Join-Path $out $lin) .

$env:GOOS = "darwin"
$env:GOARCH = "arm64"
$env:CGO_ENABLED = "0"
go build -trimpath -ldflags "-s -w" -o (Join-Path $out $dar) .

Remove-Item Env:GOOS -ErrorAction SilentlyContinue
Remove-Item Env:GOARCH -ErrorAction SilentlyContinue
$env:CGO_ENABLED = "1"

Write-Host "OK: $win $lin $dar"
