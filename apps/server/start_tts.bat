@echo off
chcp 65001 >nul
echo 启动边缘TTS API服务 (端口 8080)...
cd /d "d:\ecv\edge-tts-api"
python -m uvicorn main:app --host 127.0.0.1 --port 8080 --reload
