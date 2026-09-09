@echo off
echo 正在部署Edge-TTS服务...
cd /d d:\ecv
echo 1. 克隆Edge-TTS项目...
if not exist edge-tts-api (
    git clone https://github.com/rany2/edge-tts.git edge-tts-api
) else (
    echo Edge-TTS项目已存在
)
echo 2. 安装依赖...
cd edge-tts-api
pip install -r requirements.txt
echo 3. 更新.env配置...
cd ..\apps\server
echo LLM_API_KEY=%OPENROUTER_API_KEY% > .env
echo LLM_BASE_URL=https://openrouter.ai/api/v1 >> .env
echo LLM_MODEL=google/gemma-3-27b-it:free >> .env
echo LLM_TIMEOUT_SECONDS=45 >> .env
echo LLM_APP_NAME=AI Desktop Agent >> .env
echo LLM_HTTP_REFERER=http://localhost:5178 >> .env
echo. >> .env
echo VOICE_PROVIDER=openai >> .env
echo VOICE_API_KEY=sk-edge-tts-mock-key >> .env
echo VOICE_BASE_URL=http://localhost:5050/v1 >> .env
echo VOICE_STT_MODEL=gpt-4o-mini-transcribe >> .env
echo VOICE_TTS_MODEL=tts-1 >> .env
echo VOICE_TTS_VOICE=zh-CN-XiaoyiNeural >> .env
echo VOICE_TIMEOUT_SECONDS=60 >> .env
echo.
echo 部署完成！
echo.
echo 请按以下步骤启动服务：
echo 1. 在新窗口运行: cd d:\ecv\edge-tts-api && python main.py
echo 2. 在新窗口运行: cd d:\ecv && pnpm dev:server
echo 3. 在新窗口运行: cd d:\ecv && pnpm dev:desktop
echo 4. 在新窗口运行: cd d:\ecv && pnpm --dir apps/desktop dev:electron
echo.
pause