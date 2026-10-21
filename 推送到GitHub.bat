@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================
echo   推送 sss-toolkit 到 GitHub
echo ==========================================
echo.

set /p GHUSER=请输入你的 GitHub 用户名 [Hyperbolic-Researcher]: 
if "!GHUSER!"=="" set GHUSER=Hyperbolic-Researcher

echo.
echo 请在浏览器打开下面地址生成令牌：
echo   https://github.com/settings/tokens/new
echo   Note 随便填，Expiration 选 7 days，勾选 repo 这一整组
echo.
set /p GHTOKEN=粘贴令牌后回车（输入时不显示）: 

if "!GHTOKEN!"=="" (
    echo 未输入令牌，退出。
    pause
    exit /b 1
)

echo.
echo [1/3] 配置远程仓库...
git remote remove origin 2>nul
git remote add origin https://!GHUSER!:!GHTOKEN!@github.com/!GHUSER!/sss-toolkit.git
if errorlevel 1 goto FAIL

echo [2/3] 设置主分支...
git branch -M main
if errorlevel 1 goto FAIL

echo [3/3] 推送...
git push -u origin main
if errorlevel 1 goto FAIL

echo.
echo ==========================================
echo   推送成功
echo ==========================================
echo   仓库地址：https://github.com/!GHUSER!/sss-toolkit
echo.
echo 正在清除本地保存的令牌...
git remote set-url origin https://github.com/!GHUSER!/sss-toolkit.git
echo 已清除（令牌不再保存在项目里）
echo.
echo 提醒：推送完成后请去 GitHub 撤销这个令牌
echo       https://github.com/settings/tokens
echo.
pause
exit /b 0

:FAIL
echo.
echo 推送失败。常见原因：
echo   1. 仓库还没创建，或名字不是 sss-toolkit
echo   2. 令牌没勾 repo 权限
echo   3. 用户名写错
echo.
pause
exit /b 1
