"""
响应清洗与安全测试 - 验证内部标记不泄露、用户输入净化
"""
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.utils.response_cleaner import ResponseCleaner, LEAKAGE_FALLBACK_MESSAGE


class TestResponseCleaning:
    """响应清洗 - 移除内部调试信息"""

    def test_removes_review_notes(self):
        text = "系统运行正常。审核备注：内容合规"
        assert "审核备注" not in ResponseCleaner.clean(text)

    def test_removes_llm_config_marker(self):
        text = "结果如下。LLM provider not configured，回退到规则审核。"
        assert "LLM provider not configured" not in ResponseCleaner.clean(text)

    def test_removes_tts_marker(self):
        text = "TTS 文案：系统正常"
        assert "TTS 文案" not in ResponseCleaner.clean(text)

    def test_removes_rewritten_answer_marker(self):
        text = "[Rewritten Answer | mode=voice] 系统正常"
        assert "[Rewritten Answer" not in ResponseCleaner.clean(text)

    def test_removes_debug_marker(self):
        text = "[DEBUG] 调试信息\n系统正常"
        assert "[DEBUG" not in ResponseCleaner.clean(text)

    def test_removes_voice_mode_marker(self):
        text = "[mode=voice] 语音回复"
        assert "[mode=voice]" not in ResponseCleaner.clean(text)

    def test_removes_voice_broadcast_summary(self):
        text = "语音播报摘要：系统正常"
        assert "语音播报摘要" not in ResponseCleaner.clean(text)

    def test_removes_generator_draft_marker(self):
        text = "[Generator Draft] 草稿内容"
        assert "[Generator Draft" not in ResponseCleaner.clean(text)

    def test_removes_code_block_wrapper(self):
        text = "```markdown\n系统正常\n```"
        cleaned = ResponseCleaner.clean(text)
        assert not cleaned.startswith("```")
        assert not cleaned.endswith("```")

    def test_removes_code_block_with_language(self):
        text = "```json\n{\"key\": \"value\"}\n```"
        cleaned = ResponseCleaner.clean(text)
        assert not cleaned.startswith("```")

    def test_preserves_normal_content(self):
        text = "系统运行正常，CPU使用率45%，内存使用率60%。"
        assert ResponseCleaner.clean(text) == text

    def test_empty_string(self):
        assert ResponseCleaner.clean("") == ""

    def test_none_handling(self):
        assert ResponseCleaner.clean(None) is None


class TestLeakageDetection:
    """内部信息泄露检测"""

    def test_detects_role_setting_leakage(self):
        assert ResponseCleaner.contains_leakage("你是一个偏桌面效率的AI Agent")

    def test_detects_system_summary_leakage(self):
        assert ResponseCleaner.contains_leakage("系统监控摘要：CPU 90%")

    def test_detects_voice_context_leakage(self):
        assert ResponseCleaner.contains_leakage("语音上下文摘要：语音输入")

    def test_detects_review_note_leakage(self):
        assert ResponseCleaner.contains_leakage("审核意见：需要修改")

    def test_no_leakage_in_normal_text(self):
        assert not ResponseCleaner.contains_leakage("系统运行正常，CPU使用率45%")

    def test_no_leakage_in_empty_text(self):
        assert not ResponseCleaner.contains_leakage("")

    def test_leakage_triggers_fallback(self):
        text = "你是一个偏桌面效率的AI Agent，系统监控摘要：CPU 90%"
        cleaned = ResponseCleaner.clean(text)
        assert cleaned == LEAKAGE_FALLBACK_MESSAGE


class TestUserInputSanitization:
    """用户输入净化"""

    def test_strips_whitespace(self):
        assert ResponseCleaner.sanitize_user_input("  hello  ") == "hello"

    def test_empty_input(self):
        assert ResponseCleaner.sanitize_user_input("") == ""

    def test_cuts_at_leakage_pattern(self):
        text = "正常问题 系统监控摘要：CPU 90% 后续内容"
        sanitized = ResponseCleaner.sanitize_user_input(text)
        assert "系统监控摘要" not in sanitized

    def test_preserves_normal_input(self):
        text = "帮我查看CPU使用率"
        assert ResponseCleaner.sanitize_user_input(text) == text


class TestCleanJsonResponse:
    """JSON 响应清洗"""

    def test_cleans_string_fields(self):
        data = {
            "reply": "审核备注：合规\n系统正常",
            "meta": "LLM provider not configured",
        }
        cleaned = ResponseCleaner.clean_json_response(data)
        assert "审核备注" not in cleaned["reply"]
        assert "LLM provider not configured" not in cleaned["meta"]

    def test_handles_nested_dict(self):
        data = {
            "result": {
                "content": "[DEBUG] 调试\n正常内容",
            }
        }
        cleaned = ResponseCleaner.clean_json_response(data)
        assert "[DEBUG" not in cleaned["result"]["content"]

    def test_handles_list_values(self):
        data = {
            "messages": [
                {"role": "assistant", "content": "[mode=voice] 回复"},
            ]
        }
        cleaned = ResponseCleaner.clean_json_response(data)
        assert "[mode=voice]" not in cleaned["messages"][0]["content"]