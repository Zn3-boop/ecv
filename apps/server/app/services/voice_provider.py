from __future__ import annotations

import asyncio
import base64
import io
import os
import tempfile
import wave
from pathlib import Path
from typing import Any

import httpx


class VoiceProviderError(RuntimeError):
    """Raised when the configured voice provider request fails."""


class VoiceProvider:
    def __init__(self) -> None:
        self.provider = os.getenv('VOICE_PROVIDER', 'mock').strip().lower()
        self.api_key = os.getenv('VOICE_API_KEY', '').strip()
        self.base_url = os.getenv('VOICE_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
        self.stt_base_url = os.getenv('VOICE_STT_BASE_URL', self.base_url).rstrip('/')
        self.stt_model = os.getenv('VOICE_STT_MODEL', 'gpt-4o-mini-transcribe')
        self.tts_model = os.getenv('VOICE_TTS_MODEL', 'gpt-4o-mini-tts')
        self.tts_voice = os.getenv('VOICE_TTS_VOICE', 'alloy')
        self.timeout = float(os.getenv('VOICE_TIMEOUT_SECONDS', '60'))
        self.local_whisper_model_size = os.getenv('LOCAL_WHISPER_MODEL_SIZE', 'small').strip() or 'small'
        self.local_whisper_compute_type = os.getenv('LOCAL_WHISPER_COMPUTE_TYPE', 'int8').strip() or 'int8'
        self.local_whisper_device = os.getenv('LOCAL_WHISPER_DEVICE', 'auto').strip() or 'auto'
        self.local_whisper_language = os.getenv('LOCAL_WHISPER_LANGUAGE', 'zh').strip() or 'zh'
        self.last_error: str | None = None
        self.last_error_stage: str | None = None
        self.last_error_type: str | None = None
        self.last_error_code: str | None = None
        self.last_upload_mime_type: str | None = None
        self._local_whisper_model: Any | None = None
        self.enabled = self.provider == 'local_whisper' or (self.provider != 'mock' and bool(self.api_key))
        
        # 预加载 Whisper 模型（异步，不阻塞启动）
        if self.provider == 'local_whisper':
            import threading
            def _preload():
                try:
                    self._load_local_whisper_model()
                    print("[VoiceProvider] Whisper model preloaded successfully")
                except Exception as e:
                    print(f"[VoiceProvider] Whisper preload failed: {e}")
                    self._remember_error(str(e), stage='stt')
            threading.Thread(target=_preload, daemon=True).start()

    def _build_unavailable_stt_response(self) -> dict[str, Any]:
        return {
            'provider': 'mock',
            'text': '',
            'model': 'mock-browser-fallback',
            'fallback_used': True,
            'stt_available': False,
            'manual_input_required': True,
            'error': 'stt_not_configured',
            'message': '后端 STT 未启用，请保留录音并允许用户手动确认或编辑转写文本。',
            'raw': {},
        }

    def _build_error_stt_response(self, *, message: str, error: str) -> dict[str, Any]:
        return {
            'provider': 'mock',
            'text': '',
            'model': 'mock-browser-fallback',
            'fallback_used': True,
            'stt_available': False,
            'manual_input_required': True,
            'error': error,
            'message': message,
            'raw': {},
        }

    def _classify_error(self, error: str | None) -> tuple[str | None, str | None]:
        normalized = (error or '').lower()
        if not normalized:
            return None, None
        if any(token in normalized for token in {'401', '403', 'api key', 'unauthorized', 'forbidden'}):
            return 'auth', 'auth_error'
        if any(token in normalized for token in {'429', 'rate limit', 'too many requests'}):
            return 'rate_limit', 'rate_limited'
        if any(token in normalized for token in {'404', 'model', 'not found', 'disabled', 'unavailable'}):
            return 'model', 'model_unavailable'
        if any(token in normalized for token in {'timeout', 'timed out'}):
            return 'timeout', 'timeout'
        if any(token in normalized for token in {'connect', 'network', 'dns', 'refused'}):
            return 'network', 'network_error'
        if 'audio_too_small' in normalized:
            return 'input', 'audio_too_small'
        if 'empty_wav_frames' in normalized:
            return 'input', 'empty_wav_frames'
        return 'unknown', 'unknown_error'

    def _remember_error(self, error: str | None, *, stage: str | None = None) -> None:
        self.last_error = error.strip() if isinstance(error, str) and error.strip() else None
        self.last_error_stage = stage
        self.last_error_type, self.last_error_code = self._classify_error(self.last_error)

    def _clear_error(self) -> None:
        self.last_error = None
        self.last_error_stage = None
        self.last_error_type = None
        self.last_error_code = None

    def _get_effective_stt_model(self) -> str:
        return self.local_whisper_model_size if self.provider == 'local_whisper' else self.stt_model

    def _get_effective_base_url(self) -> str:
        if self.provider == 'local_whisper':
            return 'local://faster-whisper'
        return self.base_url

    def _get_effective_stt_enabled(self) -> bool:
        return self.provider == 'local_whisper' or self.enabled

    def _get_effective_tts_enabled(self) -> bool:
        return self.enabled and bool(self.api_key or self.base_url != 'https://api.openai.com/v1')

    def get_runtime_config(self) -> dict[str, Any]:
        return {
            'provider': self.provider,
            'enabled': self.enabled,
            'stt_enabled': self._get_effective_stt_enabled(),
            'tts_enabled': self._get_effective_tts_enabled(),
            'stt_model': self._get_effective_stt_model(),
            'tts_model': self.tts_model,
            'tts_voice': self.tts_voice,
            'base_url': self._get_effective_base_url(),
            'stt_base_url': 'local://faster-whisper' if self.provider == 'local_whisper' else self.stt_base_url,
        }

    def get_status(self) -> dict[str, Any]:
        stt_enabled = self._get_effective_stt_enabled()
        tts_enabled = self._get_effective_tts_enabled()
        local_model_loaded = self._local_whisper_model is not None if self.provider == 'local_whisper' else None
        stt_available = stt_enabled and (self.provider != 'local_whisper' or bool(local_model_loaded) or self.last_error_stage != 'stt')
        tts_available = tts_enabled and self.last_error_stage != 'tts'
        return {
            'provider': self.provider,
            'enabled': self.enabled,
            'stt_enabled': stt_enabled,
            'tts_enabled': tts_enabled,
            'stt_model': self._get_effective_stt_model(),
            'tts_model': self.tts_model,
            'tts_voice': self.tts_voice,
            'base_url': self._get_effective_base_url(),
            'stt_base_url': 'local://faster-whisper' if self.provider == 'local_whisper' else self.stt_base_url,
            'available': stt_available or tts_available,
            'stt_available': stt_available,
            'tts_available': tts_available,
            'last_error': self.last_error,
            'last_error_stage': self.last_error_stage,
            'last_error_type': self.last_error_type,
            'last_error_code': self.last_error_code,
            'last_upload_mime_type': self.last_upload_mime_type,
            'local_whisper_compute_type': self.local_whisper_compute_type,
            'local_whisper_device': self.local_whisper_device,
            'local_whisper_model_loaded': local_model_loaded,
        }

    def _load_local_whisper_model(self):
        if self._local_whisper_model is None:
            from faster_whisper import WhisperModel

            device = self.local_whisper_device
            if device == 'auto':
                device = 'cpu'

            self._local_whisper_model = WhisperModel(
                self.local_whisper_model_size,
                device=device,
                compute_type=self.local_whisper_compute_type,
            )
        return self._local_whisper_model

    def _decode_audio_to_wav_bytes(self, audio_bytes: bytes) -> bytes:
        """
        通用音频解码：支持 webm, mp4, ogg, wav 等格式转为 16kHz 单声道 PCM WAV
        优先使用 ffmpeg（最可靠，支持 webm/opus），降级使用 soundfile 或 pydub
        """
        import subprocess
        
        # 🆕 优先使用 ffmpeg（最可靠，支持 webm/opus）
        infile_path = None
        outfile_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as infile:
                infile.write(audio_bytes)
                infile_path = infile.name
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as outfile:
                outfile_path = outfile.name
            
            result = subprocess.run(
                ['ffmpeg', '-y', '-i', infile_path, '-ac', '1', '-ar', '16000', '-acodec', 'pcm_s16le', outfile_path],
                capture_output=True, timeout=30
            )
            if result.returncode == 0:
                with open(outfile_path, 'rb') as f:
                    wav_data = f.read()
                if len(wav_data) > 1000:
                    print(f"[VoiceProvider] ffmpeg 解码成功: {len(wav_data)} bytes")
                    return wav_data
            else:
                print(f"[VoiceProvider] ffmpeg 解码失败: {result.stderr[:200]}")
        except FileNotFoundError:
            print("[VoiceProvider] ffmpeg 未安装，尝试其他解码方式...")
        except Exception as e:
            print(f"[VoiceProvider] ffmpeg 解码失败: {e}")
        finally:
            try:
                if infile_path:
                    os.unlink(infile_path)
                if outfile_path:
                    os.unlink(outfile_path)
            except:
                pass
        
        # 降级：soundfile
        try:
            import soundfile as sf
            data, samplerate = sf.read(io.BytesIO(audio_bytes), dtype='float32', always_2d=False)
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, data, samplerate, format='WAV', subtype='PCM_16')
            return wav_buffer.getvalue()
        except Exception as sf_err:
            print(f"[VoiceProvider] soundfile 解码失败: {sf_err}")
        
        # 降级：pydub
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
            audio = audio.set_channels(1).set_frame_rate(16000)
            wav_buffer = io.BytesIO()
            audio.export(wav_buffer, format='wav')
            return wav_buffer.getvalue()
        except Exception as pydub_err:
            print(f"[VoiceProvider] pydub 解码失败: {pydub_err}")
        
        raise ValueError("无法解码音频。请先在 WSL 执行：sudo apt install ffmpeg -y")

    def _ensure_wave_file(self, wav_bytes: bytes) -> bytes:
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wav_file:
            frame_count = wav_file.getnframes()
            if frame_count <= 0:
                raise ValueError('empty_wav_frames')
        return wav_bytes

    def _transcribe_with_local_whisper(self, audio_bytes: bytes) -> dict[str, Any]:
        model = self._load_local_whisper_model()
        wav_bytes = self._ensure_wave_file(self._decode_audio_to_wav_bytes(audio_bytes))

        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_audio:
            temp_audio.write(wav_bytes)
            temp_audio_path = Path(temp_audio.name)

        try:
            segments, info = model.transcribe(
                str(temp_audio_path),
                language=self.local_whisper_language,
                vad_filter=True,
            )
            transcript = ' '.join(segment.text.strip() for segment in segments).strip()
            self._clear_error()
            return {
                'provider': 'local_whisper',
                'text': transcript,
                'model': self.local_whisper_model_size,
                'fallback_used': False,
                'stt_available': True,
                'manual_input_required': False,
                'raw': {
                    'language': getattr(info, 'language', self.local_whisper_language),
                    'duration': getattr(info, 'duration', None),
                },
            }
        finally:
            try:
                temp_audio_path.unlink(missing_ok=True)
            except Exception:
                pass

    async def transcribe_bytes(self, *, audio_bytes: bytes, filename: str, mime_type: str) -> dict[str, Any]:
        self.last_upload_mime_type = mime_type

        if not self._get_effective_stt_enabled():
            self._remember_error('stt_not_configured', stage='stt')
            return self._build_unavailable_stt_response()

        if not audio_bytes or len(audio_bytes) < 1024:
            self._remember_error('audio_too_small', stage='stt')
            return self._build_error_stt_response(
                message='录音内容过短或为空，请重新录音后再试。',
                error='audio_too_small',
            )

        if self.provider == 'local_whisper':
            try:
                # 使用 run_in_executor 将同步的 Whisper 调用放到线程池执行，避免阻塞事件循环
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self._transcribe_with_local_whisper, audio_bytes)
            except Exception as exc:
                self._remember_error(str(exc), stage='stt')
                return self._build_error_stt_response(
                    message='本地 Whisper 转写失败，已降级为手动确认文本模式。',
                    error=str(exc),
                )

        headers = {
            'Authorization': f'Bearer {self.api_key}',
        }

        files = {
            'file': (filename, audio_bytes, mime_type),
        }
        data = {
            'model': self.stt_model,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f'{self.stt_base_url}/audio/transcriptions', headers=headers, files=files, data=data)
        except httpx.HTTPError as exc:
            self._remember_error(str(exc), stage='stt')
            return self._build_error_stt_response(
                message='语音服务网络异常，已降级为手动确认文本模式。',
                error=str(exc),
            )
        except Exception as exc:
            self._remember_error(str(exc), stage='stt')
            return self._build_error_stt_response(
                message='语音服务异常，已降级为手动确认文本模式。',
                error=str(exc),
            )

        if response.status_code >= 400:
            self._remember_error(f'{response.status_code} {response.text}', stage='stt')
            return self._build_error_stt_response(
                message='语音服务返回错误，已降级为手动确认文本模式。',
                error=f'{response.status_code} {response.text}',
            )

        payload = response.json()
        self._clear_error()
        return {
            'provider': self.provider,
            'text': payload.get('text', '').strip(),
            'model': self.stt_model,
            'fallback_used': False,
            'stt_available': True,
            'manual_input_required': False,
            'raw': payload,
        }

    async def synthesize_text(self, *, text: str, format: str = 'mp3') -> dict[str, Any]:
        if not self._get_effective_tts_enabled():
            self._remember_error('tts_not_configured', stage='tts')
            return {
                'provider': 'browser',
                'text': text,
                'model': 'browser-speech-synthesis',
                'voice': 'browser-speech-synthesis',
                'mime_type': 'text/plain',
                'audio_base64': '',
                'fallback_used': True,
                'error': 'tts_not_configured',
            }

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.tts_model,
            'voice': self.tts_voice,
            'input': text,
            'format': format,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f'{self.base_url}/audio/speech', headers=headers, json=payload)
        except httpx.ConnectError as exc:
            self._remember_error(f'Voice Bridge 连接失败 ({self.base_url}): {exc}', stage='tts')
            return {
                'provider': 'mock',
                'text': text,
                'model': 'mock-browser-fallback',
                'voice': 'browser-speech-synthesis',
                'mime_type': 'text/plain',
                'audio_base64': '',
                'fallback_used': True,
                'error': f'Voice Bridge 未启动 ({self.base_url})，已降级为浏览器语音',
            }
        except httpx.HTTPError as exc:
            self._remember_error(str(exc), stage='tts')
            return {
                'provider': 'mock',
                'text': text,
                'model': 'mock-browser-fallback',
                'voice': 'browser-speech-synthesis',
                'mime_type': 'text/plain',
                'audio_base64': '',
                'fallback_used': True,
                'error': str(exc),
            }
        except Exception as exc:
            self._remember_error(str(exc), stage='tts')
            return {
                'provider': 'mock',
                'text': text,
                'model': 'mock-browser-fallback',
                'voice': 'browser-speech-synthesis',
                'mime_type': 'text/plain',
                'audio_base64': '',
                'fallback_used': True,
                'error': str(exc),
            }

        if response.status_code >= 400:
            self._remember_error(f'{response.status_code} {response.text}', stage='tts')
            return {
                'provider': 'mock',
                'text': text,
                'model': 'mock-browser-fallback',
                'voice': 'browser-speech-synthesis',
                'mime_type': 'text/plain',
                'audio_base64': '',
                'fallback_used': True,
                'error': f'{response.status_code} {response.text}',
            }

        audio_bytes = response.content
        self._clear_error()
        return {
            'provider': self.provider,
            'audio_base64': base64.b64encode(audio_bytes).decode('utf-8'),
            'mime_type': 'audio/mpeg',
            'model': self.tts_model,
            'voice': self.tts_voice,
        }


voice_provider = VoiceProvider()