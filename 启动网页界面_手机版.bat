@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title SSS Toolkit - LAN mode
echo.
echo Starting in LAN mode: phones on the same WiFi can control it.
echo.
python webui.py --lan
if errorlevel 1 (
    echo.
    echo Failed. Run: python webui.py --lan
    pause
)
