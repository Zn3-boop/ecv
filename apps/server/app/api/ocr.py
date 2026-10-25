from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.ocr.service import get_ocr_service

router = APIRouter(prefix="/ocr", tags=["ocr"])


class OCRImageRequest(BaseModel):
    image_path: str = Field(..., description="图片文件路径")


class OCRResultResponse(BaseModel):
    success: bool
    text: str = ""
    blocks: list[dict] = []
    latency_ms: float = 0.0
    engine: str = ""
    error: str = ""


class ScreenElementsResponse(BaseModel):
    success: bool
    elements: list[dict] = []
    count: int = 0
    error: str = ""


@router.post("/recognize", response_model=OCRResultResponse)
async def recognize_image(request: OCRImageRequest):
    """
    对图片文件执行OCR识别

    示例: POST /ocr/recognize
    {"image_path": "C:/Users/user/Pictures/screenshot.png"}
    """
    ocr = get_ocr_service()
    result = await asyncio.to_thread(ocr.recognize_image, request.image_path)
    return OCRResultResponse(
        success=result.success,
        text=result.text,
        blocks=result.blocks,
        latency_ms=result.latency_ms,
        engine=result.engine,
        error=result.error,
    )


@router.post("/screen-elements", response_model=ScreenElementsResponse)
async def extract_screen_elements(request: OCRImageRequest):
    """
    对截图提取结构化屏幕元素（文字+坐标+置信度）

    示例: POST /ocr/screen-elements
    {"image_path": "C:/Users/user/Pictures/screenshot.png"}
    """
    ocr = get_ocr_service()
    ocr_result = await asyncio.to_thread(ocr.recognize_image, request.image_path)
    if not ocr_result.success:
        return ScreenElementsResponse(success=False, error=ocr_result.error)

    elements = ocr.extract_screen_elements(ocr_result)
    return ScreenElementsResponse(
        success=True,
        elements=[e.to_dict() for e in elements],
        count=len(elements),
    )