from __future__ import annotations

import base64
import os
from typing import Any

_langfuse_instance = None
_langfuse_handler = None


def init_langfuse() -> tuple[Any, Any] | None:
    global _langfuse_instance, _langfuse_handler
    if _langfuse_instance is not None:
        return _langfuse_instance, _langfuse_handler
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)

        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        host = os.getenv("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://jp.cloud.langfuse.com")).strip()

        if not (secret_key and public_key):
            print("[LangFuse] 环境变量缺失(SECRET_KEY/PUBLIC_KEY)，已禁用追踪")
            return None

        from langfuse import Langfuse
        _langfuse_instance = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )

        try:
            from langfuse.langchain import CallbackHandler
            _langfuse_handler = CallbackHandler(public_key=public_key)
        except Exception as _cb_err:
            print(f"[LangFuse] CallbackHandler创建失败: {_cb_err}")
            _langfuse_handler = None

        s3_bucket = os.getenv("LANGFUSE_S3_MEDIA_UPLOAD_BUCKET", "").strip()
        if s3_bucket:
            print(f"[LangFuse] Media storage configured: bucket={s3_bucket}")
        else:
            print("[LangFuse] No S3/MinIO media bucket configured (image upload disabled)")

        print(f"[LangFuse] 初始化成功 host={host}")
        return _langfuse_instance, _langfuse_handler

    except Exception as e:
        print(f"[Observability] LangFuse初始化失败（非致命）: {e}")
        _langfuse_instance = None
        _langfuse_handler = None
        return None


def get_langfuse_handler() -> Any:
    return _langfuse_handler


class _LangfuseProxy:
    def __getattr__(self, name: str) -> Any:
        if _langfuse_instance is None:
            return _Noop()
        return getattr(_langfuse_instance, name)

    def __bool__(self) -> bool:
        return _langfuse_instance is not None


class _Noop:
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return _Noop()

    def __getattr__(self, name: str) -> Any:
        return _Noop()

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def __bool__(self) -> bool:
        return False


langfuse = _LangfuseProxy()


def create_langfuse_trace(
    name: str,
    conversation_id: str | None = None,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    if _langfuse_instance is None:
        return _Noop()
    try:
        from langfuse.types import TraceContext
        trace_id = _langfuse_instance.create_trace_id(seed=conversation_id or name)
        return _langfuse_instance.start_observation(
            name=name,
            as_type="chain",
            trace_context=TraceContext(trace_id=trace_id),
            input=metadata or {},
            metadata={"user_id": user_id or "", "conversation_id": conversation_id or ""},
        )
    except Exception:
        return _Noop()


def create_langfuse_span(
    trace_obj: Any,
    name: str,
    input_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    if _langfuse_instance is None or isinstance(trace_obj, _Noop):
        return _Noop()
    try:
        return _langfuse_instance.start_observation(
            name=name,
            as_type="span",
            input=input_data or {},
            metadata=metadata or {},
        )
    except Exception:
        return _Noop()


def wrap_image_for_langfuse(
    image_source: str | bytes,
    *,
    mime_type: str = "image/png",
    label: str | None = None,
) -> dict[str, Any]:
    if isinstance(image_source, bytes):
        b64 = base64.b64encode(image_source).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64}"
        result: dict[str, Any] = {
            "type": "image_url",
            "image_url": {"url": data_uri},
        }
        if label:
            result["label"] = label
        return result

    source_str = str(image_source)

    if source_str.startswith(("http://", "https://", "data:")):
        result = {
            "type": "image_url",
            "image_url": {"url": source_str},
        }
        if label:
            result["label"] = label
        return result

    if os.path.isfile(source_str):
        ext = os.path.splitext(source_str)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".webp": "image/webp", ".bmp": "image/bmp",
        }
        actual_mime = mime_map.get(ext, mime_type)
        with open(source_str, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        data_uri = f"data:{actual_mime};base64,{b64}"
        result = {
            "type": "image_url",
            "image_url": {"url": data_uri},
        }
        if label:
            result["label"] = label
        return result

    return {
        "type": "image_url",
        "image_url": {"url": source_str},
        "label": label or "unknown_source",
    }


def build_multimodal_input(
    text: str,
    images: list[str | bytes] | None = None,
    *,
    mime_type: str = "image/png",
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    if images:
        for i, img in enumerate(images):
            parts.append(wrap_image_for_langfuse(img, mime_type=mime_type, label=f"image_{i}"))
    return parts