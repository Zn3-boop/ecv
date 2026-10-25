from __future__ import annotations

from app.services.vlm.provider import VLMProvider, VLMError, provider

__all__ = ["VLMProvider", "VLMError", "get_vlm_provider", "provider"]


def get_vlm_provider() -> VLMProvider:
    return provider