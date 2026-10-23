@echo off
chcp 936 >nul 2>&1
cd /d "%~dp0"
title SSS 工具

echo ============================================
echo   SSS 工具 - 正在启动
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 goto NOPY
echo [1/3] Python 检查通过

netstat -ano | findstr ":8765" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 goto PORTBUSY
echo [2/3] 端口空闲

echo [3/3] 启动服务...
echo.
echo ============================================
echo   服务地址:  http://127.0.0.1:8765
echo   浏览器会自动打开，没打开就手动输上面的地址
echo.
echo   这个黑窗口不要关，关掉服务就停了
echo ============================================
echo.

python webui.py --lan
goto END

:NOPY
echo.
echo [错误] 找不到 python 命令
echo.
echo 说明: 本工具需要 Python。如果装过 Python，
echo       可能是没加入 PATH，需要重装并勾选 Add Python to PATH。
echo.
pause
exit /b 1

:PORTBUSY
echo.
echo [提示] 端口 8765 已被占用，服务可能已经在运行了
echo.
echo   如果服务已经在跑: 直接在浏览器打开下面地址
echo       http://127.0.0.1:8765
echo.
echo   如果要重新启动: 按任意键清理占用后再启动
echo.
pause
echo 正在清理占用端口的进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 >nul
echo.
echo 清理完成，重新启动...
echo.
python webui.py --lan
goto END

:END
echo.
echo ============================================
echo   服务已停止
echo ============================================
echo.
echo 如果是意外退出，上面会有错误信息。常见原因:
echo   1. 端口 8765 被别的程序占用
echo   2. Python 缺依赖，执行下面这行安装:
echo      pip install -U yt-dlp openpyxl imageio-ffmpeg
echo.
pause
