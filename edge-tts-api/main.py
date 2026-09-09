import sys
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import edge_tts
import io
import uvicorn

# 强制 UTF-8 编码
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

app = FastAPI(title="Edge-TTS API")

# 全局中间件：确保响应是 UTF-8
@app.middleware("http")
async def ensure_utf8(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response

class TTSRequest(BaseModel):
    input: str
    voice: str = "zh-CN-XiaoyiNeural"
    model: str = "tts-1"

@app.post("/v1/audio/speech")
async def text_to_speech(request: TTSRequest):
    """
    OpenAI兼容的TTS端点
    """
    try:
        # 使用edge-tts生成音频
        communicate = edge_tts.Communicate(request.input, request.voice)

        # 将音频数据写入内存
        audio_data = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.write(chunk["data"])

        audio_data.seek(0)

        # 返回音频流
        return StreamingResponse(
            io.BytesIO(audio_data.getvalue()),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f'attachment; filename="speech.mp3"',
                "Content-Type": "audio/mpeg; charset=utf-8"
            }
        )
    except Exception as e:
        # 语音服务异常时，返回降级响应，不抛出HTTP异常
        import json
        fallback_response = {
            "text": request.input,
            "fallback_used": True,
            "error": str(e),
            "message": "语音服务异常，已自动降级为文字对话模式"
        }
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=fallback_response,
            status_code=200,
            media_type="application/json; charset=utf-8"
        )

@app.get("/v1/models")
async def list_models():
    """
    列出可用的模型
    """
    return {
        "object": "list",
        "data": [
            {
                "id": "tts-1",
                "object": "model",
                "created": 1677610602,
                "owned_by": "edge-tts"
            }
        ]
    }

@app.get("/health")
async def health_check():
    """
    健康检查端点
    """
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5050)
