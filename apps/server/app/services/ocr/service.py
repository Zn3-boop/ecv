from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_ocr_instance: OCRService | None = None


@dataclass
class OCRResult:
    success: bool
    text: str = ""
    blocks: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    engine: str = ""
    error: str = ""


@dataclass
class ScreenElement:
    text: str
    bbox: list[int]
    confidence: float
    block_type: str = "text"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "bbox": self.bbox,
            "confidence": round(self.confidence, 4),
            "block_type": self.block_type,
        }


class OCRService:
    """
    OCR服务：截图 → 文字识别 → 结构化屏幕元素
    优先PaddleOCR（中文效果好），降级Tesseract，再降级空实现
    """

    def __init__(self, engine: str = "", lang: str = "ch"):
        self._engine = engine or os.getenv("OCR_ENGINE", "auto")
        self._lang = lang or os.getenv("OCR_LANG", "ch")
        self._ts_lang = os.getenv(
            "OCR_TESSERACT_LANG",
            "chi_sim+eng" if self._lang in ("ch", "chi_sim") else self._lang,
        )
        self._paddle_ocr: Any = None
        self._tesseract_available: bool = False
        self._initialized: bool = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        if self._engine in ("paddle", "auto"):
            try:
                from paddleocr import PaddleOCR
                use_angle_cls = os.getenv("OCR_USE_ANGLE_CLS", "true").lower() in ("true", "1")
                self._paddle_ocr = PaddleOCR(
                    use_angle_cls=use_angle_cls,
                    lang=self._lang,
                    show_log=False,
                )
                self._engine = "paddle"
                logger.info("OCR: PaddleOCR initialized")
                return
            except ImportError:
                logger.info("OCR: PaddleOCR not installed, trying tesseract")
            except Exception as e:
                logger.warning(f"OCR: PaddleOCR init failed: {e}, trying tesseract")

        if self._engine in ("tesseract", "auto"):
            try:
                import pytesseract
                pytesseract.get_tesseract_version()
                self._tesseract_available = True
                self._engine = "tesseract"
                logger.info("OCR: Tesseract available")
                return
            except Exception:
                logger.info("OCR: Tesseract not available")

        if self._engine == "auto":
            self._engine = "none"
            logger.warning("OCR: No OCR engine available, OCR will return empty results")

    def recognize_image(self, image_path: str) -> OCRResult:
        """
        对图片文件执行OCR识别（同步方法，调用方用 asyncio.to_thread 包装）
        """
        self._ensure_initialized()
        start = time.monotonic()

        if not os.path.exists(image_path):
            return OCRResult(success=False, error=f"Image not found: {image_path}", engine=self._engine)

        if self._engine == "paddle" and self._paddle_ocr is not None:
            result = self._recognize_paddle(image_path)
        elif self._engine == "tesseract" and self._tesseract_available:
            result = self._recognize_tesseract(image_path)
        else:
            result = OCRResult(success=False, error="No OCR engine available", engine="none")

        result.latency_ms = (time.monotonic() - start) * 1000
        return result

    def recognize_screenshot_data(self, image_bytes: bytes) -> OCRResult:
        """
        对截图二进制数据执行OCR识别（同步方法，调用方用 asyncio.to_thread 包装）
        """
        self._ensure_initialized()
        start = time.monotonic()

        if self._engine == "paddle" and self._paddle_ocr is not None:
            import numpy as np
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(image_bytes))
                img_array = np.array(img)
                result = self._recognize_paddle_array(img_array)
            except Exception as e:
                result = OCRResult(success=False, error=str(e), engine=self._engine)
        elif self._engine == "tesseract" and self._tesseract_available:
            try:
                import pytesseract
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(image_bytes))
                text = pytesseract.image_to_string(img, lang=self._ts_lang)
                result = OCRResult(success=True, text=text.strip(), engine="tesseract")
            except Exception as e:
                result = OCRResult(success=False, error=str(e), engine="tesseract")
        else:
            result = OCRResult(success=False, error="No OCR engine available", engine="none")

        result.latency_ms = (time.monotonic() - start) * 1000
        return result

    def _recognize_paddle(self, image_path: str) -> OCRResult:
        try:
            raw_result = self._paddle_ocr.ocr(image_path, cls=True)
            return self._parse_paddle_result(raw_result)
        except Exception as e:
            logger.warning(f"PaddleOCR failed: {e}")
            return OCRResult(success=False, error=str(e), engine="paddle")

    def _recognize_paddle_array(self, img_array: Any) -> OCRResult:
        try:
            raw_result = self._paddle_ocr.ocr(img_array, cls=True)
            return self._parse_paddle_result(raw_result)
        except Exception as e:
            logger.warning(f"PaddleOCR array failed: {e}")
            return OCRResult(success=False, error=str(e), engine="paddle")

    def _parse_paddle_result(self, raw_result: Any) -> OCRResult:
        blocks: list[dict[str, Any]] = []
        all_text: list[str] = []

        if not raw_result:
            return OCRResult(success=True, text="", blocks=[], engine="paddle")

        for page in raw_result:
            if not page:
                continue
            for line in page:
                if not line or len(line) < 2:
                    continue
                bbox_points = line[0]
                text_and_conf = line[1]
                text = text_and_conf[0] if len(text_and_conf) > 0 else ""
                conf = text_and_conf[1] if len(text_and_conf) > 1 else 0.0

                if not text.strip():
                    continue

                bbox = self._flatten_bbox(bbox_points)
                blocks.append({
                    "text": text,
                    "bbox": bbox,
                    "confidence": round(float(conf), 4),
                    "block_type": "text",
                })
                all_text.append(text)

        return OCRResult(
            success=True,
            text="\n".join(all_text),
            blocks=blocks,
            engine="paddle",
        )

    def _recognize_tesseract(self, image_path: str) -> OCRResult:
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, lang=self._ts_lang)
            data = pytesseract.image_to_data(img, lang=self._ts_lang, output_type=pytesseract.Output.DICT)

            blocks: list[dict[str, Any]] = []
            n_boxes = len(data.get("text", []))
            for i in range(n_boxes):
                t = data["text"][i].strip()
                if not t:
                    continue
                conf = float(data["conf"][i])
                if conf < 0:
                    continue
                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                blocks.append({
                    "text": t,
                    "bbox": [x, y, x + w, y + h],
                    "confidence": round(conf / 100.0, 4),
                    "block_type": "text",
                })

            return OCRResult(
                success=True,
                text=text.strip(),
                blocks=blocks,
                engine="tesseract",
            )
        except Exception as e:
            logger.warning(f"Tesseract OCR failed: {e}")
            return OCRResult(success=False, error=str(e), engine="tesseract")

    @staticmethod
    def _flatten_bbox(bbox_points: list) -> list[int]:
        if len(bbox_points) == 4 and isinstance(bbox_points[0], (list, tuple)):
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
        if len(bbox_points) == 4:
            return [int(v) for v in bbox_points]
        return [0, 0, 0, 0]

    def extract_screen_elements(self, ocr_result: OCRResult) -> list[ScreenElement]:
        """
        从OCR结果提取结构化屏幕元素
        过滤低置信度结果，按位置排序
        """
        if not ocr_result.success or not ocr_result.blocks:
            return []

        min_conf = float(os.getenv("OCR_MIN_CONFIDENCE", "0.5"))
        elements: list[ScreenElement] = []
        for block in ocr_result.blocks:
            if block.get("confidence", 0) < min_conf:
                continue
            elements.append(ScreenElement(
                text=block["text"],
                bbox=block.get("bbox", [0, 0, 0, 0]),
                confidence=block.get("confidence", 0.0),
                block_type=block.get("block_type", "text"),
            ))

        elements.sort(key=lambda e: (e.bbox[1], e.bbox[0]))
        return elements


def get_ocr_service() -> OCRService:
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = OCRService()
    return _ocr_instance