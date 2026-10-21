@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo Starting local console...
echo Open http://127.0.0.1:8765 in your browser if it does not open automatically.
echo Close this window to stop the service.
echo.
python webui.py
if errorlevel 1 (
    echo.
    echo Failed. Make sure Python is installed and run: python webui.py
    pause
)
