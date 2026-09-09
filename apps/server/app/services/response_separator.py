from __future__ import annotations

import re
from typing import Any

from app.utils.response_cleaner import cleaner


class ResponseSeparator:
    """将完整响应拆分为展示内容与适合 TTS 播报的摘要。"""

    MAX_TTS_DURATION = 30
    CHARS_PER_SECOND = 4
    MAX_TTS_CHARS = MAX_TTS_DURATION * CHARS_PER_SECOND

    @classmethod
    def separate(cls, full_response: str, user_intent: str | None = None) -> tuple[str, str]:
        clean_response = cleaner.clean(full_response)
        display_content = cls._prepare_display_content(clean_response)

        existing_summary = cls._extract_existing_summary(clean_response)

        if existing_summary:
          tts_summary = existing_summary
        else:
            estimated_tts_time = len(clean_response) / cls.CHARS_PER_SECOND if clean_response else 0
            if estimated_tts_time <= cls.MAX_TTS_DURATION:
                tts_summary = cls._generate_tts_summary(clean_response, user_intent)
            else:
                tts_summary = cls._generate_tts_summary(clean_response, user_intent)

        tts_summary = cls._final_cleanup_for_tts(tts_summary)
        return tts_summary, display_content

    @classmethod
    def _extract_existing_summary(cls, text: str) -> str | None:
        patterns = [
            r'##\s*摘要[：:]?\s*\n(.*?)(?=\n##|\Z)',
            r'\*\*摘要[：:]?\*\*\s*(.*?)(?=\n|$)',
            r'【摘要[：:]?\s*】(.*?)【/摘要】',
            r'\[摘要[：:]?\s*\](.*?)\[/摘要\]',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                summary = cleaner.clean(match.group(1).strip())
                if summary:
                    return summary
        return None

    @classmethod
    def _prepare_display_content(cls, text: str) -> str:
        result = cleaner.clean(text)
        result = re.sub(r'^#{1,6}\s+(.+)$', r'\1', result, flags=re.MULTILINE)
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

    @classmethod
    def _generate_tts_summary(cls, full_response: str, intent: str | None = None) -> str:
        plain_text = cls._markdown_to_plain(full_response)
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if not plain_text:
            return ''

        sentences = re.split(r'(?<=[。！？!?])\s*', plain_text)
        collected: list[str] = []

        if intent:
            intent_prefix = f'关于{intent}：'
            if not plain_text.startswith(intent_prefix):
                collected.append(intent_prefix)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            next_text = ''.join(collected) + sentence
            if len(next_text) > cls.MAX_TTS_CHARS:
                break
            collected.append(sentence)
            if len(''.join(collected)) >= min(80, cls.MAX_TTS_CHARS):
                break

        summary = ''.join(collected).strip()
        if not summary:
            summary = plain_text[:cls.MAX_TTS_CHARS].strip()

        if len(plain_text) > len(summary) and len(summary) < len(plain_text):
            summary = summary.rstrip('，、；： ')
            if not summary.endswith(('。', '！', '？', '!', '?', '…')):
                summary += '。'
        return summary

    @classmethod
    def _markdown_to_plain(cls, text: str) -> str:
        result = cleaner.clean(text)
        result = re.sub(r'```(?:\w+)?\n([\s\S]*?)```', r'\1', result)
        result = re.sub(r'`[^`]+`', ' ', result)

        result = re.sub(
            r'(\|.+\|\n\|[-:| ]+\|\n(?:\|.*\|\n?)*)',
            lambda match: cls._simplify_table(match.group(1)),
            result,
            flags=re.MULTILINE,
        )

        result = re.sub(r'!\[.*?\]\(.*?\)', ' ', result)
        result = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', result)
        result = re.sub(r'^#{1,6}\s+(.+)$', r'\1：', result, flags=re.MULTILINE)
        result = re.sub(r'^\s*[-*+]\s+', '', result, flags=re.MULTILINE)
        result = re.sub(r'^\s*\d+\.\s+', '', result, flags=re.MULTILINE)
        result = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', result)
        result = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', result)
        result = re.sub(r'\n{2,}', '\n', result)
        result = re.sub(r'[ \t]+', ' ', result)
        return result.strip()

    @classmethod
    def _simplify_table(cls, table_text: str) -> str:
        lines = [line.strip() for line in table_text.strip().splitlines() if line.strip()]
        if len(lines) < 2:
            return ' '
        header = '，'.join(cell.strip() for cell in lines[0].strip('|').split('|') if cell.strip())
        data_lines = [line for line in lines[2:] if line.startswith('|')]
        if data_lines:
            first_row = '，'.join(cell.strip() for cell in data_lines[0].strip('|').split('|') if cell.strip())
            return f'表格信息：{header}；首行数据：{first_row}。'
        return f'表格信息：{header}。'

    @classmethod
    def _final_cleanup_for_tts(cls, text: str) -> str:
        result = cleaner.clean(text)
        result = result.replace('#', '').replace('*', '').replace('_', '')
        result = re.sub(r'\.{3,}', '…', result)
        result = re.sub(r'\s+', ' ', result).strip()
        if len(result) > 150:
            result = result[:147].rstrip() + '...'
        return result


separator = ResponseSeparator()