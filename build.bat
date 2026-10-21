@echo off
setlocal
cd /d "%~dp0"
set "PYINSTALLER_CONFIG_DIR=%~dp0build\pyinstaller-cache"
if exist ".build-venv\Scripts\pyinstaller.exe" (
    ".build-venv\Scripts\pyinstaller.exe" --noconfirm FMEDA.spec
) else (
    pyinstaller --noconfirm FMEDA.spec
)
if errorlevel 1 exit /b 1
echo Build ready: dist\FMEDA Tool\FMEDA Tool.exe
exit /b 0
