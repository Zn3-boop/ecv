from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_env_file = Path(__file__).parent.parent.parent.parent / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)


class VLMError(RuntimeError):
    """Raised when the local VLM fails."""


class VLMProvider:
    """
    本地多模态视觉语言模型（transformers 加载，CPU/GPU 自适应）。

    替代原 vLLM 方案：没有 GPU 的环境直接加载 Qwen2.5-VL-3B-Instruct 级别的小模型。
    模型在首次调用时惰性加载，同步推理放到线程池避免阻塞事件循环。

    环境变量：
        VLM_ENABLED          是否启用，默认 "true"
        VLM_MODEL            HF 模型名，默认 "Qwen/Qwen2.5-VL-3B-Instruct"
        VLM_DEVICE           "cpu" / "cuda" / "auto"，默认 "cpu"
        VLM_MAX_NEW_TOKENS   最大生成 token，默认 256
        VLM_MAX_IMAGE_SIDE   图片最长边压缩（CPU 下提速明显），默认 640，0 关闭
        VLM_TORCH_DTYPE      "auto" / "float32" / "bfloat16" / "float16"
    """

    def __init__(self) -> None:
        self.model_name = os.getenv("VLM_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
        self.device = os.getenv("VLM_DEVICE", "cpu")
        self.max_new_tokens = int(os.getenv("VLM_MAX_NEW_TOKENS", "256"))
        self.max_image_side = int(os.getenv("VLM_MAX_IMAGE_SIDE", "640"))
        self.torch_dtype = os.getenv("VLM_TORCH_DTYPE", "auto")
        self._model = None
        self._processor = None
        self._load_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return os.getenv("VLM_ENABLED", "true").strip().lower() == "true"

    @property
    def loaded(self) -> bool:
        return self._model is not None

    async def warmup(self) -> None:
        await self._ensure_loaded()

    async def describe_image(
        self,
        *,
        prompt: str,
        image: Any,
        max_new_tokens: int | None = None,
    ) -> str:
        """
        对单张图片做视觉问答。

        image 支持：
            - 本地文件路径 (str / Path)
            - http(s) URL
            - base64 字符串（可带 data:image 前缀）
            - PIL.Image 对象
        """
        if not self.enabled:
            raise VLMError("VLM is disabled. Set VLM_ENABLED=true.")
        await self._ensure_loaded()
        return await asyncio.to_thread(
            self._generate, prompt, image, max_new_tokens or self.max_new_tokens
        )

    async def _ensure_loaded(self) -> None:
        async with self._load_lock:
            if self._model is None:
                await asyncio.to_thread(self._load)

    def _load(self) -> None:
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        logger.info(f"[VLM] loading {self.model_name} on {self.device} ...")
        dtype = "auto" if self.torch_dtype == "auto" else getattr(torch, self.torch_dtype)

        self._processor = AutoProcessor.from_pretrained(self.model_name)
        self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
            device_map=self.device,
            low_cpu_mem_usage=True,
        )
        self._model.eval()
        logger.info("[VLM] model loaded.")

    def _to_pil(self, image: Any):
        from PIL import Image

        if isinstance(image, Image.Image):
            pil = image.convert("RGB")
        elif isinstance(image, (bytes, bytearray)):
            pil = Image.open(io.BytesIO(image)).convert("RGB")
        elif isinstance(image, Path):
            pil = Image.open(image).convert("RGB")
        elif isinstance(image, str):
            s = image
            if s.startswith("data:image"):
                s = s.split(",", 1)[1]
                pil = Image.open(io.BytesIO(base64.b64decode(s))).convert("RGB")
            elif os.path.exists(s):
                pil = Image.open(s).convert("RGB")
            elif s.startswith(("http://", "https://")):
                import httpx
                resp = httpx.get(s, timeout=30)
                resp.raise_for_status()
                pil = Image.open(io.BytesIO(resp.content)).convert("RGB")
            else:
                pil = Image.open(io.BytesIO(base64.b64decode(s))).convert("RGB")
        else:
            raise VLMError(f"Unsupported image type: {type(image)}")

        if self.max_image_side > 0 and max(pil.size) > self.max_image_side:
            pil.thumbnail((self.max_image_side, self.max_image_side))
        return pil

    def _to_image_ref(self, image: Any) -> Any:
        if isinstance(image, str):
            return image
        if isinstance(image, Path):
            return str(image)
        pil = self._to_pil(image)
        buf = io.BytesIO()
        pil.save(buf, format="JPEG")
        return base64.b64encode(buf.getvalue()).decode()

    def _generate(self, prompt: str, image: Any, max_new_tokens: int) -> str:
        import torch
        from qwen_vl_utils import process_vision_info

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": self._to_image_ref(image)},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        text = self._processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self._processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            return_tensors="pt",
        ).to(self._model.device)

        with torch.no_grad():
            generated = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
        new_tokens = generated[:, inputs["input_ids"].shape[1]:]
        result = self._processor.batch_decode(new_tokens, skip_special_tokens=True)[0]
        return result.strip()


provider = VLMProvider()