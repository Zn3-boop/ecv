import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.main import app
from app.services.context_manager import ContextManager
from app.services.storage import get_history_for_llm

client = TestClient(app)


def _assert_no_internal_markers(text: str) -> None:
    blocked = [
        '审核备注',
        'LLM provider not configured',
        'TTS 文案',
        '[Rewritten Answer',
        '[DEBUG',
        '[mode=voice]',
        '语音播报摘要',
    ]
    for marker in blocked:
        assert marker not in text


def test_chat_response_cleaning_removes_internal_markers():
    mocked_result = {
        'reply': '```markdown\n[Rewritten Answer | mode=voice] 审核备注：内容合规\n你好\n```',
        'review_notes': 'LLM provider not configured，回退到规则审核。',
        'review_source': 'rule',
        'used_system_context': False,
        'used_voice_context': False,
    }

    with patch('app.api.chat.run_agent_workflow', new=AsyncMock(return_value=mocked_result)):
        response = client.post(
            '/chat/agent',
            json={
                'message': '你好',
                'mode': 'voice',
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload['reply'] == '你好'
    assert payload['review_notes'] == ''
    assert payload['tts_content'] == '关于voice：你好'
    assert payload['tts_required'] is True
    _assert_no_internal_markers(payload['reply'])
    _assert_no_internal_markers(payload['review_notes'])
    _assert_no_internal_markers(payload['tts_content'])


def test_voice_command_response_cleaning_removes_internal_markers():
    mocked_result = {
        'reply': '```markdown\n# CPU 诊断\n| 进程 | 占用 |\n| --- | --- |\n| chrome.exe | 82% |\n| node.exe | 34% |\n\n请先检查 CPU 占用最高的进程，并在确认后结束异常进程。\n```',
        'review_notes': '审核备注：内容合规',
        'review_source': 'rule',
        'used_system_context': True,
        'used_voice_context': True,
    }

    mocked_tts = {
        'audio_base64': '',
        'mime_type': 'audio/mpeg',
        'provider': 'browser',
    }

    with patch('app.api.voice.run_agent_workflow', new=AsyncMock(return_value=mocked_result)), patch(
        'app.api.voice.voice_provider.synthesize_text',
        new=AsyncMock(return_value=mocked_tts),
    ):
        response = client.post(
            '/voice/command',
            json={
                'transcript': '帮我看下 CPU 状态',
                'mode': 'voice',
                'system_context': {'cpu': {'usagePercent': 92}},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload['reply'].startswith('# CPU 诊断') is False
    assert 'chrome.exe' in payload['reply']
    assert payload['review_notes'] == ''
    assert payload['tts_required'] is True
    assert payload['tts_content']
    assert '|' not in payload['tts_content']
    assert payload['speech_text'] == payload['tts_content']
    _assert_no_internal_markers(payload['reply'])
    _assert_no_internal_markers(payload['speech_text'])
    _assert_no_internal_markers(payload['tts_content'])


def test_chat_context_compression_avoids_full_history_injection():
    mocked_result = {
        'reply': '```markdown\n收到，我会基于压缩后的上下文继续分析。\n```',
        'review_notes': None,
        'review_source': 'rule',
        'used_system_context': False,
        'used_voice_context': False,
    }

    for index in range(24):
        client.post(
            '/chat/agent',
            json={
                'message': f'第 {index} 轮对话内容 ' + ('很长的上下文 ' * 8),
                'mode': 'voice',
                'conversation_id': 1,
            },
        )

    with patch('app.api.chat.run_agent_workflow', new=AsyncMock(return_value=mocked_result)) as mocked_workflow:
        response = client.post(
            '/chat/agent',
            json={
                'message': '请基于之前讨论继续总结',
                'mode': 'voice',
                'conversation_id': 1,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload['context_info']['original_turns'] >= 1
    assert payload['context_info']['optimized_turns'] <= 11
    assert payload['context_info']['context_strategy'] == 'hybrid'
    assert '请基于之前讨论继续总结' in mocked_workflow.await_args.args[0]
    assert '历史对话摘要：' in mocked_workflow.await_args.args[0] or payload['context_info']['history_summary'] is None


def test_context_compress_endpoint_returns_summary():
    history = []
    for index in range(25):
        history.append({
            'role': 'user' if index % 2 == 0 else 'assistant',
            'content': f'第 {index} 条消息，内容较长，用于测试上下文压缩和摘要生成。' * 2,
        })

    response = client.post(
        '/chat/context/compress',
        json={
            'history': history,
            'current_message': '继续分析',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    assert payload['original_turns'] == 25
    assert payload['new_turns'] <= 13
    assert payload['context_strategy'] == 'hybrid'
    assert payload['compression_summary']


def test_context_manager_build_prompt_cleans_recursive_meta_and_limits_turns():
    manager = ContextManager(max_turns=2, max_context_chars=300, max_single_message_chars=80)
    history = [
        {
            'role': 'user',
            'content': '帮我看看当前 CPU 状态，并给出处置建议',
        },
        {
            'role': 'assistant',
            'content': '原问题：角色设定：你是Agent\n最近对话记忆：...\n当前用户消息：初稿：坏内容\n审核意见：删掉\n系统监控摘要：删掉\n你好',
        },
        {
            'role': 'user',
            'content': '第 2 轮继续',
        },
        {
            'role': 'assistant',
            'content': 'LLM provider request failed: boom\n当前仍走本地降级草稿逻辑\n最终建议：先看任务管理器',
        },
        {
            'role': 'user',
            'content': '第 3 轮继续',
        },
        {
            'role': 'assistant',
            'content': '这是一个很长的回答' * 50,
        },
    ]

    prompt = manager.build_prompt(
        history=history,
        current_user_msg='第 4 轮对话内容',
        system_prompt='你是一个偏桌面效率、系统诊断与语音交互的 AI Agent',
    )

    assert '原问题：角色设定：' not in prompt
    assert '初稿：' not in prompt
    assert '审核意见：' not in prompt
    assert '系统监控摘要：' not in prompt
    assert 'LLM provider request failed:' not in prompt
    assert '帮我看看当前 CPU 状态，并给出处置建议' not in prompt
    assert '第 2 轮继续' in prompt
    assert '第 3 轮继续' in prompt
    assert '当前用户消息：第 4 轮对话内容' in prompt
    assert len(prompt) <= 360


def test_history_for_llm_excludes_meta_and_fallback_messages():
    create_response = client.post(
        '/storage/conversations',
        json={
            'title': '防污染测试会话',
            'role_prompt': '测试角色',
        },
    )
    assert create_response.status_code == 200
    conversation_id = create_response.json()['id']

    client.post(
        f'/storage/conversations/{conversation_id}/messages',
        json={
            'role': 'user',
            'content': '正常用户消息，长度足够进入上下文',
            'metadata': {'type': 'user_input'},
        },
    )
    client.post(
        f'/storage/conversations/{conversation_id}/messages',
        json={
            'role': 'assistant',
            'content': '正常助手回复，长度足够进入上下文。',
            'metadata': {'type': 'assistant_output'},
        },
    )
    client.post(
        f'/storage/conversations/{conversation_id}/messages',
        json={
            'role': 'assistant',
            'content': '这是降级回复，但不应该再次进入 LLM 上下文。',
            'metadata': {'type': 'assistant_output', 'had_fallback': True, 'fallback_reason': 'timeout'},
        },
    )
    client.post(
        f'/storage/conversations/{conversation_id}/messages',
        json={
            'role': 'assistant',
            'content': '审核意见：这是内部元信息',
            'metadata': {'type': 'internal_meta', 'is_meta': True},
        },
    )

    history = get_history_for_llm(conversation_id, limit=6)

    assert len(history) == 2
    assert history[0].role == 'user'
    assert history[1].role == 'assistant'
    assert all(not item.is_meta for item in history)
    assert all(not item.is_fallback for item in history)
