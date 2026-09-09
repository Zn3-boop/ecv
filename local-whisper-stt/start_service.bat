@echo off
REM 本地 Whisper STT 服务启动脚本
REM 用于启动语音转文字服务

echo 正在启动本地 Whisper STT 服务...
echo 服务地址: http://localhost:5051

REM 检查模型是否存在
if not exist "models\base" (
    echo.
    echo 错误: 未找到模型文件！
    echo 请先在联网环境中下载模型，详情见 MODEL_DOWNLOAD_GUIDE.md
    echo.
    pause
    exit /b 1
)

echo.
echo 检测到本地模型，正在启动服务...
echo.

REM 启动服务
python server.py

pause