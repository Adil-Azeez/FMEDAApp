@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\clean_build.ps1"
if errorlevel 1 exit /b 1
call "%~dp0build.bat"
exit /b %errorlevel%
