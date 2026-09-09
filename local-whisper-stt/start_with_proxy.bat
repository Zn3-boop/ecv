@echo off
chcp 65001 >nul
echo ========================================
echo   Faster-Whisper 模型下载器
echo ========================================
echo.

REM === 使用 HuggingFace 国内镜像（无需代理）===
set HF_ENDPOINT=https://hf-mirror.com

REM === 模型缓存目录配置 ===
set HF_HOME=D:\hf_cache

REM === 下载的模型大小 ===
set WHISPER_MODEL=base

echo [配置信息]
echo   镜像: %HF_ENDPOINT%
echo   模型: %WHISPER_MODEL%
echo.

REM 进入脚本目录
cd /d "%~dp0"

REM 创建缓存目录
if not exist "%HF_HOME%" mkdir "%HF_HOME%"
if not exist "models\base" mkdir "models\base"

REM 开始下载
echo 正在下载模型，请耐心等待（约需 1-2 小时）...
echo.
python download_model.py

echo.
echo ========================================
if %errorlevel%==0 (
    echo   ✓ 模型下载成功！
) else (
    echo   ✗ 模型下载失败
)
echo ========================================
pause
