"""快慢脑 System One 决策层（本地 Ollama + 小模型 logprob 版 Jev）。

把 Agent 里高频结构化判断（依赖就绪、下一步工具选择、风险分级、是否人工审核）
从「每个都让大模型慢想」抽给「快脑低成本做选择题」，慢脑只在快脑不确定时出场。
"""

from .fastbrain import (
    CONFIDENCE_TRUST,
    CONFIDENCE_RECHECK,
    Decision,
    FastBrain,
    OllamaFastBrainClient,
    get_fast_brain,
)

__all__ = [
    "CONFIDENCE_TRUST",
    "CONFIDENCE_RECHECK",
    "Decision",
    "FastBrain",
    "OllamaFastBrainClient",
    "get_fast_brain",
]