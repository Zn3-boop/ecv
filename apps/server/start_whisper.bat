@echo off
chcp 65001 >nul
echo 启动本地Whisper STT服务 (端口 9001)...
cd /d "d:\ecv\local-whisper-stt"
python server.py
