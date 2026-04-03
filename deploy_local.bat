@echo off
setlocal
cd /d "%~dp0"

where bash >nul 2>&1
if errorlevel 1 (
  echo [ERROR] bash not found. Install Git for Windows ^(Git\bin\bash.exe^) or add it to PATH.
  exit /b 1
)

REM deploy_local.bat   deploy_local.bat --bump-version   deploy_local.bat --nopause
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\deploy_local.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" exit /b %EXITCODE%
exit /b 0
