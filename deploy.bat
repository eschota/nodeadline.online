@echo off
setlocal
cd /d "%~dp0"

where ssh >nul 2>&1
if errorlevel 1 (
  echo [ERROR] ssh not found. Install OpenSSH Client ^(Windows Optional Features^) or use Git SSH.
  exit /b 1
)

REM Примеры: deploy.bat   deploy.bat --bump-version   deploy.bat --nopause
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\deploy_one_click.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" exit /b %EXITCODE%
exit /b 0
