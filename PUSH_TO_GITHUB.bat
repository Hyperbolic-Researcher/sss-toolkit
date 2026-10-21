@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

python push.py
if errorlevel 1 (
    echo.
    echo --------------------------------------------------
    echo Python not found or script error.
    echo Try running: python push.py
    echo --------------------------------------------------
    pause
)
