from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VisionResult:
    success: bool
    description: str = ""
    elements: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    model: str = ""
    error: str = ""


class VisionService:
    """
    VLM视觉理解服务：截图 → VLM → 自然语言描述 + 元素坐标
    通过OpenAI兼容API调用视觉语言模型（Qwen2-VL/GLM-4V等）
    """

    def __init__(self):
        self._base_url = os.getenv("VLM_BASE_URL", os.getenv("LLM_BASE_URL", "http://localhost:8001/v1"))
        self._model = os.getenv("VLM_MODEL", "qwen2.5-vl-7b-instruct")
        self._api_key = os.getenv("VLM_API_KEY", os.getenv("LLM_API_KEY", ""))
        self._timeout = float(os.getenv("VLM_TIMEOUT", "60"))

    async def analyze_image(
        self,
        image_path: str,
        prompt: str = "请描述这张截图的内容，包括可见的文字、按钮、输入框等UI元素及其位置。",
    ) -> VisionResult:
        start = time.monotonic()
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            return await self._analyze_bytes(image_bytes, prompt, start)
        except FileNotFoundError:
            return VisionResult(success=False, error=f"Image not found: {image_path}")
        except Exception as e:
            return VisionResult(success=False, error=str(e), latency_ms=(time.monotonic() - start) * 1000)

    async def analyze_screenshot_bytes(
        self,
        image_bytes: bytes,
        prompt: str = "请描述这张截图的内容，包括可见的文字、按钮、输入框等UI元素及其位置。",
    ) -> VisionResult:
        start = time.monotonic()
        return await self._analyze_bytes(image_bytes, prompt, start)

    async def locate_element(
        self,
        image_path: str,
        element_description: str,
    ) -> VisionResult:
        prompt = (
            f"在截图中找到以下UI元素，并返回其位置信息：\n"
            f"目标元素：{element_description}\n\n"
            f'请以JSON格式输出：\n'
            f'{{"found": true, "element": "{element_description}", "bbox": [x1, y1, x2, y2], "center": [cx, cy], "description": "..."}}\n'
            f'如果找不到该元素，输出：{{"found": false}}'
        )
        return await self.analyze_image(image_path, prompt)

    async def _analyze_bytes(
        self,
        image_bytes: bytes,
        prompt: str,
        start_time: float,
    ) -> VisionResult:
        import httpx

        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        ext = "png"
        if image_bytes[:3] == b'\xff\xd8\xff':
            ext = "jpeg"

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{ext};base64,{b64_image}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.1,
        }

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        url = self._base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)

            latency = (time.monotonic() - start_time) * 1000

            if resp.status_code != 200:
                return VisionResult(
                    success=False,
                    error=f"VLM API error: HTTP {resp.status_code} {resp.text[:200]}",
                    latency_ms=latency,
                    model=self._model,
                )

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            elements = self._extract_elements(content)

            return VisionResult(
                success=True,
                description=content,
                elements=elements,
                latency_ms=latency,
                model=self._model,
            )
        except Exception as e:
            return VisionResult(
                success=False,
                error=str(e),
                latency_ms=(time.monotonic() - start_time) * 1000,
                model=self._model,
            )

    @staticmethod
    def _extract_elements(content: str) -> list[dict[str, Any]]:
        import json
        import re

        elements: list[dict[str, Any]] = []

        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                if "found" in parsed or "bbox" in parsed:
                    elements.append(parsed)
            except json.JSONDecodeError:
                pass

        json_array_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_array_match and not elements:
            try:
                parsed = json.loads(json_array_match.group())
                if isinstance(parsed, list):
                    elements = parsed
            except json.JSONDecodeError:
                pass

        return elements


_vision_service: VisionService | None = None


def get_vision_service() -> VisionService:
    global _vision_service
    if _vision_service is None:
        _vision_service = VisionService()
    return _vision_service