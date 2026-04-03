#Requires -Version 5.1
<#
  Nodeadline (Windows): venv → pip install зависимостей → запуск node_main.py.
  Корень установки — каталог с runtime\ (как у Go-инсталлятора) или корень репозитория с node_main.py.

  Таймауты по умолчанию короткие, чтобы зависания pip/сети ловились быстро.

  Примеры:
    .\tools\windows\install-nodeadline.ps1
    .\tools\windows\install-nodeadline.ps1 -InstallRoot "$env:LOCALAPPDATA\nodeadline-v2"
    .\tools\windows\install-nodeadline.ps1 -Offline -Mirror "https://nodeadline.online/Nodeadline/Core/requirements/"
    .\tools\windows\install-nodeadline.ps1 -NoStart -RecreateVenv
#>
[CmdletBinding()]
param(
  [string]$InstallRoot = "",
  [switch]$Offline,
  [switch]$NoStart,
  [switch]$RecreateVenv,
  [int]$PipTimeoutSec = 25,
  [int]$PipRetries = 2,
  [string]$Mirror = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Log([string]$Msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Write-Host "[$ts] $Msg"
}

function Resolve-InstallRoot {
  param([string]$Root)
  if ($Root -and $Root.Trim()) {
    return (Resolve-Path -LiteralPath $Root.Trim()).Path
  }
  return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
}

function Find-RequirementsFile {
  param([string]$Root)
  $app = Join-Path $Root "runtime\app\requirements-node.txt"
  if (Test-Path -LiteralPath $app) { return $app }
  $repo = Join-Path $Root "requirements-node.txt"
  if (Test-Path -LiteralPath $repo) { return $repo }
  return $null
}

function Find-NodeMain {
  param([string]$Root)
  $a = Join-Path $Root "runtime\app\node_main.py"
  if (Test-Path -LiteralPath $a) { return $a }
  $b = Join-Path $Root "node_main.py"
  if (Test-Path -LiteralPath $b) { return $b }
  return $null
}

function Find-PythonExe {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    $out = & py -3 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) { return $out.Trim() }
  }
  foreach ($name in @("python", "python3")) {
    if (Get-Command $name -ErrorAction SilentlyContinue) {
      $out = & $name -c "import sys; print(sys.executable)" 2>$null
      if ($LASTEXITCODE -eq 0 -and $out) { return $out.Trim() }
    }
  }
  throw "Python 3 не найден. Установите python.org (галочка Add to PATH) или Python Launcher (py)."
}

$root = Resolve-InstallRoot -Root $InstallRoot
Write-Log "InstallRoot: $root"

$reqFile = Find-RequirementsFile -Root $root
if (-not $reqFile) {
  throw "Не найден requirements-node.txt (ожидалось runtime\app\ или корень репозитория)."
}
$nodeMain = Find-NodeMain -Root $root
if (-not $nodeMain) {
  throw "Не найден node_main.py (ожидалось runtime\app\node_main.py или node_main.py в корне)."
}

$venvDir = Join-Path $root "runtime\venv"
$pyVenv = Join-Path $venvDir "Scripts\python.exe"

if ($RecreateVenv -and (Test-Path -LiteralPath $venvDir)) {
  Write-Log "RecreateVenv: удаляю $venvDir"
  Remove-Item -LiteralPath $venvDir -Recurse -Force
}

$systemPython = Find-PythonExe
Write-Log "Системный Python: $systemPython"

if (-not (Test-Path -LiteralPath $venvDir)) {
  Write-Log "Создаю venv: $venvDir"
  & $systemPython -m venv $venvDir
  if ($LASTEXITCODE -ne 0) { throw "python -m venv завершился с кодом $LASTEXITCODE" }
}

if (-not (Test-Path -LiteralPath $pyVenv)) {
  throw "Нет $pyVenv после создания venv."
}

# Короткие таймауты pip — быстрый отказ при сетевых проблемах
$env:PIP_DEFAULT_TIMEOUT = "$PipTimeoutSec"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PYTHONUNBUFFERED = "1"

if ($Offline) {
  $m = $Mirror
  if (-not $m) { $m = $env:NODEADLINE_REQUIREMENTS_MIRROR }
  if (-not $m) {
    throw "Offline: укажите -Mirror 'https://.../requirements/' или NODEADLINE_REQUIREMENTS_MIRROR."
  }
  $m = $m.TrimEnd("/")
  Write-Log "Offline: --no-index --find-links $m"
  $pipArgs = @(
    "install",
    "--timeout", "$PipTimeoutSec",
    "--retries", "$PipRetries",
    "--no-index",
    "--find-links", $m,
    "-r", $reqFile
  )
} else {
  Write-Log "Online: pip из PyPI (таймаут ${PipTimeoutSec}s, попыток: $PipRetries)"
  $pipArgs = @(
    "install",
    "--timeout", "$PipTimeoutSec",
    "--retries", "$PipRetries",
    "-r", $reqFile
  )
}

Write-Log "pip: python -m pip $($pipArgs -join ' ')"
& $pyVenv -m pip @pipArgs
if ($LASTEXITCODE -ne 0) { throw "pip install завершился с кодом $LASTEXITCODE" }

Write-Log "Проверка импортов (быстро)…"
& $pyVenv -c "import waitress, psutil, miniupnpc, cryptography, jwt" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
  & $pyVenv -c "import waitress, psutil, miniupnpc, cryptography, jwt"
  throw "Импорт обязательных модулей не прошёл."
}

if ($NoStart) {
  Write-Log "NoStart: нода не запускается."
  exit 0
}

$runtimeDir = Join-Path $root "runtime"
$appDir = Split-Path -Parent $nodeMain
if (-not (Test-Path -LiteralPath $runtimeDir)) {
  New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
}

Write-Log "Запуск ноды: $nodeMain"
Write-Log "Рабочий каталог: $appDir  NODEADLINE_RUNTIME_DIR=$runtimeDir"
Push-Location $appDir
try {
  $env:NODEADLINE_RUNTIME_DIR = $runtimeDir
  if (-not $env:NODEADLINE_CONFIG) {
    $cfg = Join-Path $root "nodeadline.json"
    if (-not (Test-Path -LiteralPath $cfg)) {
      $ex = Join-Path $root "nodeadline.example.json"
      if (Test-Path -LiteralPath $ex) { $env:NODEADLINE_CONFIG = $ex }
    } else {
      $env:NODEADLINE_CONFIG = $cfg
    }
  }
  & $pyVenv -u $nodeMain
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
