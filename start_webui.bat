@echo off
setlocal enabledelayedexpansion
chcp 936 >nul 2>&1
cd /d "%~dp0"
title SSS 工具

echo ============================================
echo   SSS 工具 - 正在启动
echo ============================================
echo.

REM ---- 1. 找一个装了 yt-dlp 的 Python ----
REM 系统里可能有多个 Python，只有装了 yt-dlp 的才能用。
set "PYEXE="
set "C1=C:\Users\P775\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
set "C2=C:\Users\P775\.workbuddy\binaries\python\versions\3.13.12\python.exe"

if exist "!C1!" (
    "!C1!" -c "import yt_dlp" >nul 2>&1
    if not errorlevel 1 set "PYEXE=!C1!"
)
if "!PYEXE!"=="" (
    if exist "!C2!" (
        "!C2!" -c "import yt_dlp" >nul 2>&1
        if not errorlevel 1 set "PYEXE=!C2!"
    )
)
if "!PYEXE!"=="" (
    python -c "import yt_dlp" >nul 2>&1
    if not errorlevel 1 set "PYEXE=python"
)

if "!PYEXE!"=="" goto NOYTDLP
echo [1/3] Python OK

REM ---- 2. 检查端口 ----
netstat -ano | findstr ":8765" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 goto PORTBUSY
echo [2/3] 端口空闲

REM ---- 3. 启动 ----
echo [3/3] 启动服务...
echo.
echo ============================================
echo   服务地址:  http://127.0.0.1:8765
echo   浏览器会自动打开，没打开就手动输上面的地址
echo.
echo   这个黑窗口不要关，关掉服务就停了
echo ============================================
echo.

"!PYEXE!" webui.py --lan
goto END

:NOYTDLP
echo [错误] 找不到装好依赖的 Python
echo.
echo 系统里的 python 缺少 yt_dlp 模块，工具无法工作。
echo.
echo 解决办法：打开命令行，执行下面这行安装依赖
echo.
echo    pip install -U yt-dlp openpyxl imageio-ffmpeg
echo.
echo 装完再双击本工具即可。
echo.
pause
exit /b 1

:PORTBUSY
echo.
echo [提示] 端口 8765 已被占用，服务可能已经在运行了
echo.
echo   如果服务已经在跑: 直接在浏览器打开
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
"!PYEXE!" webui.py --lan
goto END

:END
echo.
echo ============================================
echo   服务已停止
echo ============================================
echo.
echo 如果是意外退出，上面会有错误信息。
echo.
pause
