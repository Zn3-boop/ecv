"""
本地 Whisper STT 服务 (使用 faster-whisper)
兼容 OpenAI /v1/audio/transcriptions API
运行端口：5051
"""

import os
import subprocess
import tempfile

import uvicorn
from faster_whisper import WhisperModel
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI(title="Local Whisper STT")

MODEL_NAME = os.getenv("WHISPER_MODEL", "base")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE", "float32")  # float32, int8, etc. 默认使用CPU友好的类型

# 配置模型下载路径到本地
local_model_path = os.path.join(os.path.dirname(__file__), "models")

print(f"Loading Faster-Whisper model ({MODEL_NAME}, compute={COMPUTE_TYPE})...")

# 只尝试从本地加载模型，不自动下载
model_path = os.path.join(local_model_path, MODEL_NAME)
if os.path.exists(model_path):
    # 如果本地模型存在，直接加载
    model = WhisperModel(model_path, compute_type=COMPUTE_TYPE)
    print("Faster-Whisper model loaded from local cache.")
else:
    # 如果本地模型不存在，抛出错误并提供清晰的指导
    print(f"Model '{MODEL_NAME}' not found in local cache at {model_path}")
    print("ERROR: Model not found locally and auto-download is disabled in offline mode.")
    print("Please download the model first using one of these methods:")
    print("1. On a machine with internet: python download_model.py")
    print("2. Manually download from https://huggingface.co/Systran/faster-whisper-{MODEL_NAME}")
    print("   and extract to:", model_path)
    print("After downloading the model, restart the service.")
    raise RuntimeError(f"Model '{MODEL_NAME}' not found. Please download it first.")


def convert_audio(input_path: str, output_path: str):
    """
    使用 ffmpeg 把任意格式转成 16kHz 单声道 wav
    """
    try:
        subprocess.run([
            'ffmpeg', '-i', input_path,
            '-ar', '16000',      # 采样率 16kHz
            '-ac', '1',          # 单声道
            '-c:a', 'pcm_s16le', # 16位 PCM 编码
            '-y',                # 覆盖输出
            output_path
        ], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg 转码失败: {e.stderr}")
        raise RuntimeError(f"Audio conversion failed: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("FFmpeg 未安装或不在 PATH 中。请先安装 ffmpeg: choco install ffmpeg")


@app.get("/health")
def health():
    return {"status": "ok", "service": "whisper-stt", "model": MODEL_NAME}


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model_name: str = Form("whisper-1"),
    language: str = Form("zh"),
    response_format: str = Form("json"),
):
    original_path = None
    wav_path = None
    try:
        # 1. 保存前端传来的原始音频（通常是 webm）
        suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            original_path = tmp.name
            content = await file.read()
            tmp.write(content)
        
        # 2. 转码为 16kHz wav
        wav_path = original_path.replace(suffix, ".wav")
        convert_audio(original_path, wav_path)
        
        # 3. 使用 Faster-Whisper 转录
        segments, info = model.transcribe(wav_path, language=language or "zh")
        text = "".join([segment.text for segment in segments])
        
        if response_format == "text":
            return PlainTextResponse(text)
        
        return JSONResponse(
            content={
                "text": text.strip(),
                "language": info.language if hasattr(info, 'language') else language or "zh",
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "detail": "STT processing failed"}
        )
    finally:
        # 4. 无论如何都要清理临时文件，防止磁盘撑爆
        if original_path and os.path.exists(original_path):
            try:
                os.unlink(original_path)
            except OSError:
                pass
        if wav_path and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except OSError:
                pass


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5051)