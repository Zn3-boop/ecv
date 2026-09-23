"""
快慢脑 System One 决策层 —— 本地 Ollama + 小模型 logprob 版 Jev。

背景(J1-J4)：Jev 不是聊天大模型、不生成文本，是专门做结构化决策的 System One 模型，
输出带置信概率的 Choice/Score/Boolean，代码可直接解析。官方 Jev 无开源权重，
本实现用最贴近的「本地小模型 + logprob」复刻（Ollama 在 Windows 可直接跑，无需 Apple Silicon）：

    快脑  qwen3:1.7b / qwen3:4b   只问"下一个 token 是 A/B/C 的概率"(logprobs)，不让它说话
    慢脑  qwen3:14b / 云端         真生成解释、复杂推理、写代码

核心原语(对应 Jev Choice/Score/Boolean)：
    jev_choice(state, options)  -> (best, probs)   多选一(每选项一个字母，取 logprob 归一化概率)
    boolean                      -> A/B 二选一
    score                        -> A/B/C/D/E 五档桶归一化到 0~1

快慢脑降级(J8 / 反馈规则)：
    prob[best] >= 0.9        直接采信快脑，继续执行
    0.6 <= prob[best] < 0.9  交给慢脑 LLM 复核该判断
    prob[best] < 0.6         人工审核 / 规则兜底(fail-open，本实现降级到调用方规则)

fail-open：ollama 未安装 / 未运行 / 模型缺失 → decide() 返回 None，上层降级到规则，
与 guard registry 一致。默认不开启(FAST_BRAIN_ENABLED=1 才启用)。
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# 快慢脑降级阈值(J8 / 反馈规则)：>=TRUST 采信，>=RECHECK 慢脑复核，否则人工/规则
CONFIDENCE_TRUST = 0.9
CONFIDENCE_RECHECK = 0.6

# 快脑小模型(可被 FAST_BRAIN_MODEL 覆盖)
_DEFAULT_MODEL = os.getenv("FAST_BRAIN_MODEL", "qwen3:4b")


def _fast_brain_enabled() -> bool:
    """快脑是否启用。默认关闭；设 FAST_BRAIN_ENABLED=1/true 开启。"""
    raw = os.getenv("FAST_BRAIN_ENABLED", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


@dataclass
class Decision:
    """一条结构化决策结果(J4：Choice/Score/Boolean 原语)。"""

    id: str
    kind: str  # "choice" | "score" | "boolean"
    value: Any
    probability: float
    source: str = "fast_brain"  # "fast_brain" | "slow_brain" | "rule"

    @property
    def confident(self) -> bool:
        return self.probability >= CONFIDENCE_TRUST

    @property
    def needs_recheck(self) -> bool:
        return CONFIDENCE_RECHECK <= self.probability < CONFIDENCE_TRUST

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"Decision(id={self.id}, kind={self.kind}, value={self.value!r}, prob={self.probability:.2f}, src={self.source})"

class OllamaFastBrainClient:
    """
    本地快脑客户端：用 Ollama 小模型 + logprob 做结构化决策(Jev 式 System One)。

    不生成文本：只让模型在固定选项字母上打分，取 top_logprobs 归一化为各选项概率。
    """

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        timeout: float = 10.0,
        top_logprobs: int = 20,
    ) -> None:
        self.model = model or _DEFAULT_MODEL
        self.host = host
        self.timeout = timeout
        self.top_logprobs = top_logprobs
        self._client: Any = None

    def _lazy_client(self) -> Any:
        """惰性加载 ollama 客户端；未安装返回 None(上层据此降级)。"""
        if self._client is not None:
            return self._client
        try:
            import ollama  # type: ignore
            self._client = ollama.Client(host=self.host) if self.host else ollama
        except Exception as e:  # pragma: no cover - ollama 未安装
            logger.warning(f"FastBrain: ollama SDK 不可用, 降级到规则/慢脑: {e}")
            self._client = False
        return self._client

    async def decide(
        self,
        state: dict[str, Any],
        questions: list[dict[str, Any]],
    ) -> Optional[list[Decision]]:
        """并行执行多条结构化决策，返回带 probability 的 Decision 列表；失败返回 None。"""
        client = self._lazy_client()
        if not client:
            return None
        try:
            results = await asyncio.wait_for(
                self._decide_all(client, state, questions), timeout=self.timeout
            )
            return results
        except asyncio.TimeoutError:
            logger.warning(f"FastBrain: 快脑 decide 超时({self.timeout}s), 降级到规则/慢脑")
            return None
        except Exception as e:  # pragma: no cover
            logger.warning(f"FastBrain: 快脑 decide 失败, 降级到规则/慢脑: {e}")
            return None

    async def _decide_all(self, client, state, questions) -> list[Decision]:
        state_str = _state_to_prompt(state)
        out: list[Decision] = []
        for q in questions:
            kind = q.get("type", "boolean")
            qid = q.get("id", "")
            if kind == "choice":
                options = list(q.get("options", []))
                best, probs = await asyncio.to_thread(self._choice, client, state_str, options)
                out.append(Decision(id=qid, kind="choice", value=best,
                                    probability=probs.get(best, 0.0), source="fast_brain"))
            elif kind == "score":
                lo, hi = float(q.get("min", 0.0)), float(q.get("max", 1.0))
                score, prob = await asyncio.to_thread(self._score, client, state_str, lo, hi)
                out.append(Decision(id=qid, kind="score", value=score,
                                    probability=prob, source="fast_brain"))
            else:  # boolean
                val, prob = await asyncio.to_thread(self._boolean, client, state_str)
                out.append(Decision(id=qid, kind="boolean", value=val,
                                    probability=prob, source="fast_brain"))
        return out

    # ---- logprob 决策原语(与 Jev Choice/Boolean/Score 对应) ----
    def _choice(self, client, state: str, options: list[str]) -> tuple[Any, dict[str, float]]:
        """多选一：每个选项一个字母，取 logprob 归一化概率。返回 (best, probs)。"""
        if not options:
            return None, {}
        letters = [chr(65 + i) for i in range(len(options))]
        prompt = (
            "State:\n" + state + "\n\n"
            "Choose the best option. Answer with ONLY the letter.\n"
            + "\n".join(f"{letter}: {opt}" for letter, opt in zip(letters, options))
        )
        scores = self._logprobs(client, prompt, letters)
        probs = _normalize(scores)
        best_letter = max(probs, key=probs.get)
        letter_to_option = dict(zip(letters, options))
        best_option = letter_to_option.get(best_letter, best_letter)
        return best_option, probs

    def _boolean(self, client, state: str) -> tuple[bool, float]:
        """布尔判断：A=yes / B=no 二选一。返回 (bool, probability)。"""
        options = ["yes", "no"]
        best, probs = self._choice(client, state, options)
        return best == "yes", probs.get(best, 0.0)

    def _score(self, client, state: str, lo: float, hi: float) -> tuple[float, float]:
        """打分：A/B/C/D/E 五档桶归一化到 [lo, hi]。返回 (score, probability)。"""
        buckets = [("A", 0.0), ("B", 0.25), ("C", 0.5), ("D", 0.75), ("E", 1.0)]
        letters = [letter for letter, _ in buckets]
        prompt = (
            "State:\n" + state + "\n\n"
            "Rate the risk/score from A (lowest) to E (highest). Answer with ONLY the letter."
        )
        scores = self._logprobs(client, prompt, letters)
        probs = _normalize(scores)
        best = max(probs, key=probs.get)
        frac = dict(buckets)[best]
        return lo + (hi - lo) * frac, probs.get(best, 0.0)

    def _logprobs(self, client, prompt: str, letters: list[str]) -> dict[str, float]:
        """调用 ollama 取 top_logprobs，把每个选项字母的 logprob 转成概率分数(未归一化)。"""
        resp = client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0, "num_predict": 1},
            think=False,
            logprobs=True,
            top_logprobs=self.top_logprobs,
        )
        logprobs_data = resp.get("logprobs", []) or []
        if not logprobs_data:
            msg_logprobs = resp.get("message", {}).get("logprobs", {})
            top = (msg_logprobs or {}).get("top_logprobs", [])
            if not top:
                raise ValueError("ollama 未返回 logprobs，请确认模型支持 logprobs 参数")
            top_map = top[0]
        else:
            first_token = logprobs_data[0]
            top_list = first_token.get("top_logprobs", [])
            top_map = {item["token"]: item["logprob"] for item in top_list}
        scores: dict[str, float] = {}
        for letter in letters:
            lp = top_map.get(letter)
            scores[letter] = math.exp(lp) if lp is not None else 0.0
        return scores


def _state_to_prompt(state: dict[str, Any]) -> str:
    """把 Agent State 映射成快脑可读的文本(只保留关键字段，避免超长)。"""
    lines: list[str] = []
    for k, v in state.items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        lines.append(f"{k}: {_trim(str(v))}")
    return "\n".join(lines) if lines else "(empty state)"


def _trim(s: str, limit: int = 400) -> str:
    return s if len(s) <= limit else s[:limit] + "...[truncated]"


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values()) or 1.0
    return {k: v / total for k, v in scores.items()}


class FastBrain:
    """
    快慢脑编排器：快脑(logprob 小模型) + 置信度阈值降级(慢脑 LLM / 规则兜底)。

    decide_choice / decide_boolean / decide_score 三种原语方法。
    置信度不足时调用 recheck(慢脑) 或退回 rule_fallback(规则)。
    """

    def __init__(
        self,
        client: Optional[OllamaFastBrainClient] = None,
        trust: float = CONFIDENCE_TRUST,
        recheck: float = CONFIDENCE_RECHECK,
        enabled: Optional[bool] = None,
    ) -> None:
        self.enabled = _fast_brain_enabled() if enabled is None else enabled
        self.client = client or OllamaFastBrainClient()
        self.trust = trust
        self.recheck = recheck

    async def decide(
        self,
        state: dict[str, Any],
        questions: list[dict[str, Any]],
        recheck: Callable[[str], Awaitable[Any]] | None = None,
        rule_fallback: Callable[[str], Any] | None = None,
    ) -> list[Decision]:
        """快慢脑主入口(J8 / 反馈 0.9/0.6 规则)。

        - 未启用 / 快脑不可用 → 全部走 rule_fallback(规则) 或标记 slow_brain。
        - prob>=trust → 采信快脑。
        - recheck<=prob<trust 或 prob<recheck → 交给慢脑(recheck) 或规则兜底。
        """
        out: list[Decision] = []
        if not self.enabled:
            for q in questions:
                out.append(self._fallback(q, recheck, rule_fallback, reason="disabled"))
            return out

        results = await self.client.decide(state, questions)
        if results is None:
            for q in questions:
                out.append(self._fallback(q, recheck, rule_fallback, reason="unavailable"))
            return out

        results_by_id = {d.id: d for d in results}
        for q in questions:
            d = results_by_id.get(q.get("id", ""))
            if d is None or d.probability < self.recheck:
                out.append(self._fallback(q, recheck, rule_fallback, reason="low_confidence", d=d))
                continue
            if d.probability < self.trust:
                val = await self._recheck_one(q, recheck)
                out.append(
                    Decision(id=q.get("id", ""), kind=q.get("type", "boolean"),
                             value=val[0], probability=val[1], source="slow_brain")
                )
                continue
            out.append(d)
        return out

    async def decide_choice(
        self,
        state: dict[str, Any],
        question: dict[str, Any],
        options: list[str],
        recheck: Callable[[str], Awaitable[Any]] | None = None,
        rule_fallback: Callable[[], Any] | None = None,
    ) -> Decision:
        q = {**question, "type": "choice", "options": options}
        res = await self.decide(state, [q], recheck=recheck, rule_fallback=rule_fallback)
        return res[0]

    async def decide_boolean(
        self,
        state: dict[str, Any],
        question: dict[str, Any],
        recheck: Callable[[str], Awaitable[Any]] | None = None,
        rule_fallback: Callable[[], Any] | None = None,
    ) -> Decision:
        q = {**question, "type": "boolean"}
        res = await self.decide(state, [q], recheck=recheck, rule_fallback=rule_fallback)
        return res[0]

    async def decide_score(
        self,
        state: dict[str, Any],
        question: dict[str, Any],
        minimum: float = 0.0,
        maximum: float = 1.0,
        recheck: Callable[[str], Awaitable[Any]] | None = None,
        rule_fallback: Callable[[], Any] | None = None,
    ) -> Decision:
        q = {**question, "type": "score", "min": minimum, "max": maximum}
        res = await self.decide(state, [q], recheck=recheck, rule_fallback=rule_fallback)
        return res[0]

    # ---- 内部 ----
    def _fallback(self, q, recheck, rule_fallback, reason, d=None) -> Decision:
        qid = q.get("id", "")
        kind = q.get("type", "boolean")
        if rule_fallback:
            try:
                value = rule_fallback(qid)
                return Decision(id=qid, kind=kind, value=value, probability=0.0, source="rule")
            except Exception as e:  # pragma: no cover
                logger.warning(f"FastBrain: rule_fallback 失败 {e}")
        if d is not None:
            return Decision(id=qid, kind=kind, value=d.value, probability=d.probability, source="slow_brain")
        return Decision(id=qid, kind=kind, value=None, probability=0.0, source="slow_brain")

    async def _recheck_one(self, q, recheck) -> tuple[Any, float]:
        if recheck is None:
            return None, 0.0
        try:
            val = await recheck(q.get("id", ""))
            if isinstance(val, tuple):
                return val
            return val, 0.0
        except Exception as e:  # pragma: no cover
            logger.warning(f"FastBrain: 慢脑复核失败 {e}")
            return None, 0.0


_singleton: Optional[FastBrain] = None


def get_fast_brain() -> FastBrain:
    """进程级单例快脑。"""
    global _singleton
    if _singleton is None:
        _singleton = FastBrain()
    return _singleton