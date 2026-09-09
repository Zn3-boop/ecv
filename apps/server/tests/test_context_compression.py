"""
双层对话摘要压缩测试 - 验证 ContextManager 三种压缩策略
可量化指标：长会话 Token 消耗降低约 XX%（压30条历史 vs 压缩后对比）
"""
import sys
import time
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.services.context_manager import (
    ContextManager,
    CompressionStrategy,
    ConversationTurn,
)


def _build_long_history(turn_count: int = 30, chars_per_turn: int = 200) -> list[dict]:
    """构建长会话历史"""
    history = []
    for i in range(turn_count):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"第{i+1}轮对话：" + "这是一段测试内容。" * (chars_per_turn // 10)
        history.append({
            "role": role,
            "content": content,
            "metadata": {},
        })
    return history


def _estimate_raw_tokens(history: list[dict]) -> int:
    """估算原始历史 Token 数"""
    cm = ContextManager()
    total = 0
    for msg in history:
        total += cm.estimate_tokens(msg.get("content", ""))
    return total


def _estimate_compressed_tokens(context: list[dict]) -> int:
    """估算压缩后上下文 Token 数"""
    cm = ContextManager()
    total = 0
    for msg in context:
        total += cm.estimate_tokens(msg.get("content", ""))
    return total


class TestSlidingWindowCompression:
    """滑动窗口压缩策略"""

    def test_basic_compression(self):
        cm = ContextManager(
            max_turns=6,
            max_tokens=6000,
            strategy=CompressionStrategy.SLIDING_WINDOW,
        )
        history = _build_long_history(30)
        context, summary = cm.process(history)

        assert summary is None
        assert len(context) <= 12

    def test_preserves_recent_turns(self):
        cm = ContextManager(
            max_turns=4,
            strategy=CompressionStrategy.SLIDING_WINDOW,
        )
        history = _build_long_history(20)
        context, _ = cm.process(history)

        last_user_msg = None
        for msg in reversed(history):
            if msg["role"] == "user":
                last_user_msg = msg["content"][:50]
                break

        found = any(last_user_msg in c.get("content", "") for c in context)
        assert found, "压缩后应保留最近用户消息"

    def test_token_budget_respected(self):
        cm = ContextManager(
            max_turns=6,
            max_tokens=3000,
            strategy=CompressionStrategy.SLIDING_WINDOW,
        )
        history = _build_long_history(30, chars_per_turn=300)
        context, _ = cm.process(history)

        compressed_tokens = _estimate_compressed_tokens(context)
        assert compressed_tokens <= cm.max_tokens * 1.2


class TestSummaryCompression:
    """摘要压缩策略"""

    def test_generates_summary_for_long_history(self):
        cm = ContextManager(
            max_turns=6,
            max_tokens=6000,
            strategy=CompressionStrategy.SUMMARY,
        )
        history = _build_long_history(30)
        context, summary = cm.process(history)

        if len(history) > cm.SUMMARY_THRESHOLD:
            assert summary is not None, "超过阈值应生成摘要"

    def test_summary_in_context(self):
        cm = ContextManager(
            max_turns=6,
            max_tokens=6000,
            strategy=CompressionStrategy.SUMMARY,
        )
        history = _build_long_history(30)
        context, summary = cm.process(history)

        if summary:
            has_summary_msg = any(
                "历史对话摘要" in c.get("content", "")
                for c in context
            )
            assert has_summary_msg, "摘要应作为 system 消息插入上下文"

    def test_summary_max_length(self):
        cm = ContextManager(
            max_turns=6,
            max_tokens=6000,
            strategy=CompressionStrategy.SUMMARY,
        )
        history = _build_long_history(50, chars_per_turn=500)
        _, summary = cm.process(history)

        if summary:
            assert len(summary) <= cm.MAX_SUMMARY_CHARS + 1


class TestHybridCompression:
    """混合压缩策略（默认）"""

    def test_short_history_no_compression(self):
        cm = ContextManager(
            max_turns=6,
            max_tokens=6000,
            strategy=CompressionStrategy.HYBRID,
        )
        history = _build_long_history(5)
        context, summary = cm.process(history)

        assert summary is None
        assert len(context) == len(history)

    def test_long_history_triggers_compression(self):
        cm = ContextManager(
            max_turns=6,
            max_tokens=6000,
            strategy=CompressionStrategy.HYBRID,
        )
        history = _build_long_history(30, chars_per_turn=300)
        context, summary = cm.process(history)

        raw_tokens = _estimate_raw_tokens(history)
        compressed_tokens = _estimate_compressed_tokens(context)
        reduction = (1 - compressed_tokens / raw_tokens) * 100

        print(f"\n[Token压缩] 原始: {raw_tokens}, 压缩后: {compressed_tokens}, 降低: {reduction:.1f}%")
        assert compressed_tokens < raw_tokens, "压缩后 Token 应减少"

    def test_compression_ratio_benchmark(self):
        """量化基准：30条历史 vs 压缩后 Token 消耗对比"""
        cm = ContextManager(
            max_turns=6,
            max_tokens=6000,
            strategy=CompressionStrategy.HYBRID,
        )
        history = _build_long_history(30, chars_per_turn=200)
        context, summary = cm.process(history)

        raw_tokens = _estimate_raw_tokens(history)
        compressed_tokens = _estimate_compressed_tokens(context)
        if summary:
            cm_for_summary = ContextManager()
            compressed_tokens += cm_for_summary.estimate_tokens(summary)

        reduction = (1 - compressed_tokens / raw_tokens) * 100
        print(f"\n[Token压缩基准] 30条历史: 原始={raw_tokens} tokens, 压缩后={compressed_tokens} tokens, 降低={reduction:.1f}%")
        assert reduction > 30, f"Token消耗降低 {reduction:.1f}% 应超过 30%"


class TestContextManagerEdgeCases:
    """ContextManager 边界情况"""

    def test_empty_history(self):
        cm = ContextManager()
        context, summary = cm.process([])
        assert context == []
        assert summary is None

    def test_single_turn(self):
        cm = ContextManager()
        history = [{"role": "user", "content": "你好", "metadata": {}}]
        context, summary = cm.process(history)
        assert len(context) >= 1

    def test_meta_messages_filtered(self):
        cm = ContextManager()
        history = [
            {"role": "system", "content": "元信息", "metadata": {"is_meta": True}},
            {"role": "user", "content": "正常消息", "metadata": {}},
        ]
        context, _ = cm.process(history)
        assert not any("元信息" in c.get("content", "") for c in context)

    def test_fallback_messages_filtered(self):
        cm = ContextManager()
        history = [
            {"role": "assistant", "content": "降级回复", "metadata": {"is_fallback": True}},
            {"role": "user", "content": "正常消息", "metadata": {}},
        ]
        context, _ = cm.process(history)
        assert not any("降级回复" in c.get("content", "") for c in context)

    def test_single_message_char_limit(self):
        cm = ContextManager(max_single_message_chars=50)
        history = [{"role": "user", "content": "A" * 200, "metadata": {}}]
        context, _ = cm.process(history)
        for msg in context:
            if msg["role"] == "user":
                assert len(msg["content"]) <= 53

    def test_token_estimation(self):
        cm = ContextManager()
        chinese_tokens = cm.estimate_tokens("你好世界测试")
        english_tokens = cm.estimate_tokens("hello world test")
        assert chinese_tokens > 0
        assert english_tokens > 0
        assert chinese_tokens > english_tokens


class TestCompressionPerformance:
    """压缩操作性能测试"""

    def test_compression_under_10ms(self):
        cm = ContextManager(
            max_turns=6,
            max_tokens=6000,
            strategy=CompressionStrategy.HYBRID,
        )
        history = _build_long_history(30)

        start = time.perf_counter()
        for _ in range(100):
            cm.process(history)
        elapsed = (time.perf_counter() - start) * 1000

        avg_ms = elapsed / 100
        print(f"\n[压缩性能] 100次压缩平均耗时: {avg_ms:.3f}ms")
        assert avg_ms < 10, f"压缩平均耗时 {avg_ms:.3f}ms 超过 10ms 阈值"