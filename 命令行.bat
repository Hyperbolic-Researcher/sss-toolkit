@echo off
setlocal enabledelayedexpansion
chcp 936 >nul 2>&1
cd /d "%~dp0"
set "PYEXE="
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -c "import yt_dlp" >nul 2>&1
    if not errorlevel 1 set "PYEXE=%~dp0.venv\Scripts\python.exe"
)
if "!PYEXE!"=="" (
    python -c "import yt_dlp" >nul 2>&1
    if not errorlevel 1 set "PYEXE=python"
)
if "!PYEXE!"=="" (
    echo [错误] 找不到装了 yt-dlp 的 Python
    echo        先执行: pip install -U yt-dlp openpyxl imageio-ffmpeg
    pause
    exit /b 1
)
"!PYEXE!" sss.py %*
echo.
pause
