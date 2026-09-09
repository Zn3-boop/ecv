@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo AI Desktop Agent - 启动脚本 (Windows)
echo ========================================

:: 加载 .env 环境变量
if exist ".env" (
    echo [start] 加载 .env 配置...
    for /f "usebackq tokens=1,* delims==" %%a in ("\.env") do (
        set "%%a=%%b"
    )
)

:: 设置 HF 缓存目录
if not defined HF_HOME set "HF_HOME=d:\hf_cache"
if not exist "%HF_HOME%" mkdir "%HF_HOME%"
echo [start] HF_HOME=%HF_HOME%

:: 显示代理配置
if defined HTTP_PROXY echo [start] HTTP_PROXY=%HTTP_PROXY%
if defined HF_ENDPOINT echo [start] HF_ENDPOINT=%HF_ENDPOINT%

echo.
echo 启动后端服务 (端口 8000)...
cd apps\server

if exist "d:\ecv\venv\Scripts\python.exe" (
    d:\ecv\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
) else (
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
)

pause