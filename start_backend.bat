@echo off
title 台球AR投影系统 - 后端服务
cd /d %~dp0\backend

echo ============================================
echo    台球智能AR投影系统 - 后端服务
echo ============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.11+
    pause
    exit /b 1
)

REM Install dependencies if needed
echo [安装] 检查依赖...
pip install -r requirements.txt -q
echo [完成] 依赖检查完毕
echo.

echo [启动] 正在启动系统...
echo.
echo 请确保已在 config.py 中配置好摄像头RTSP地址
echo 按 Ctrl+C 停止服务
echo.

python main.py
pause
