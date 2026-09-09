from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

app = FastAPI(title="Voice Bridge", version="1.0.0")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_STT_MODEL = os.getenv("OPENAI_STT_MODEL", os.getenv("VOICE_STT_MODEL", "gpt-4o-mini-transcribe"))
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", os.getenv("VOICE_TTS_MODEL", "tts-1"))
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", os.getenv("VOICE_TTS_VOICE", "alloy"))
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "90"))


def _headers() -> dict[str, str]:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured")
    return {"Authorization": f"Bearer {OPENAI_API_KEY}"}


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "base_url": OPENAI_BASE_URL,
        "stt_model": OPENAI_STT_MODEL,
        "tts_model": OPENAI_TTS_MODEL,
        "tts_voice": OPENAI_TTS_VOICE,
        "has_api_key": bool(OPENAI_API_KEY),
    }


@app.post("/v1/audio/transcriptions")
async def audio_transcriptions(
    file: UploadFile = File(...),
    model: str = Form(default=OPENAI_STT_MODEL),
):
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty")

    files = {"file": (file.filename or "voice.webm", audio_bytes, file.content_type or "audio/webm")}
    data = {"model": model or OPENAI_STT_MODEL}

    try:
        async with httpx.AsyncClient(timeout=OPENAI_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{OPENAI_BASE_URL}/audio/transcriptions",
                headers=_headers(),
                files=files,
                data=data,
            )
    except httpx.HTTPError as exc:
        # 语音服务不可用时，返回降级响应，不卡住token
        import json
        fallback_response = {
            "text": "语音服务暂不可用，已自动降级为文字对话模式，请直接输入文字。",
            "fallback_used": True,
            "error": str(exc)
        }
        return Response(
            content=json.dumps(fallback_response, ensure_ascii=False).encode('utf-8'),
            status_code=200,
            media_type="application/json; charset=utf-8",
        )
    except Exception as exc:
        # 捕获所有异常，防止卡住token
        import json
        fallback_response = {
            "text": "语音服务异常，已自动降级为文字对话模式，请直接输入文字。",
            "fallback_used": True,
            "error": str(exc)
        }
        return Response(
            content=json.dumps(fallback_response, ensure_ascii=False).encode('utf-8'),
            status_code=200,
            media_type="application/json; charset=utf-8",
        )

    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )


@app.post("/v1/audio/speech")
async def audio_speech(payload: dict):
    model = payload.get("model") or OPENAI_TTS_MODEL
    voice = payload.get("voice") or OPENAI_TTS_VOICE
    text = str(payload.get("input") or "").strip()
    fmt = payload.get("format") or "mp3"

    if not text:
        raise HTTPException(status_code=400, detail="input text is required")

    upstream_payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": fmt,
    }

    try:
        async with httpx.AsyncClient(timeout=OPENAI_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{OPENAI_BASE_URL}/audio/speech",
                headers={**_headers(), "Content-Type": "application/json"},
                json=upstream_payload,
            )
    except httpx.HTTPError as exc:
        # 语音服务不可用时，返回降级响应，不卡住token
        import json
        fallback_response = {
            "text": text,
            "fallback_used": True,
            "error": str(exc),
            "message": "语音服务暂不可用，已自动降级为文字对话模式"
        }
        return Response(
            content=json.dumps(fallback_response, ensure_ascii=False).encode('utf-8'),
            status_code=200,
            media_type="application/json; charset=utf-8",
        )
    except Exception as exc:
        # 捕获所有异常，防止卡住token
        import json
        fallback_response = {
            "text": text,
            "fallback_used": True,
            "error": str(exc),
            "message": "语音服务异常，已自动降级为文字对话模式"
        }
        return Response(
            content=json.dumps(fallback_response, ensure_ascii=False).encode('utf-8'),
            status_code=200,
            media_type="application/json; charset=utf-8",
        )

    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "audio/mpeg"),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("VOICE_BRIDGE_PORT", "5050")))
