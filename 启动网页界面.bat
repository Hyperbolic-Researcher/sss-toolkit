@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动本地控制台...
python webui.py
if errorlevel 1 pause
