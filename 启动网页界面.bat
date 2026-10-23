@echo off
chcp 936 >nul 2>&1
cd /d "%~dp0"
REM 这个文件只是 start_webui.bat 的入口，逻辑全部在主脚本里，
REM 避免两份实现各自漂移（曾经因此出现 No module named yt_dlp）。
call "%~dp0start_webui.bat" %*
