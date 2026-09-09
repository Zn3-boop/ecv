from __future__ import annotations

import re

CONTENT_GENERATE_KEYWORDS = [
    '创建', '生成', '编写', '制作', '设计', '撰写',
    '登录页面', '网页', 'html', '网站', '页面',
    '文档', '文章', '报告', '论文', '毕业论文',
    '代码', '程序', '脚本',
    'word', 'wps', 'office',
    '保存到', '存到', '放在',
]

SEARCH_KEYWORDS = [
    '搜索', '搜一下', '查一下', '查询', '百度', 'google',
    '查资料', '找资料',
]

def _is_simple_single_action(text: str) -> str | None:
    """
    判断是否为简单单动作指令（本地规则可快速处理）。
    返回意图类型，或 None 表示需要 LLM 分解。

    本地规则只处理以下简单情况：
    1. 纯系统监控（"电脑很卡"、"CPU多少"）
    2. 纯单应用启动，无其他动作（"打开微信"）
    3. 纯搜索，无其他动作（"搜索Python教程"）
    4. 应用商店操作（"删除XX应用"、"卸载XX"、"安装XX"、"搜索应用XX"）
    """
    normalized = text.lower()

    has_optimize = any(k in normalized for k in ['全面清理', '深度优化', '电脑加速', '系统清理', '清理垃圾', '清理缓存', '优化', '加速', '提速'])
    has_monitor = any(k in normalized for k in ['cpu', '内存', 'memory', 'disk', '监控', '状态', 'c盘', '进程', '检查', '诊断', '占用', '使用率'])
    has_open = any(k in normalized for k in ['打开', '启动', '运行'])
    has_content = any(k in text for k in CONTENT_GENERATE_KEYWORDS)
    has_search = any(k in text for k in SEARCH_KEYWORDS)
    has_kill = any(k in normalized for k in ['结束', '杀', '关闭进程', '关闭', '关掉', '退出', '关了'])

    if has_kill and not has_open and not has_content:
        return 'desktop_control'

    if has_optimize and not has_monitor and not has_kill:
        return 'system_optimize'
    if has_monitor and not has_optimize and not has_kill:
        return 'system_monitor'
    if any(k in normalized for k in ['卡', '慢']) and not has_optimize and not has_kill:
        return 'system_monitor'
    if any(k in normalized for k in ['磁盘']) and not has_optimize and not has_kill:
        return 'system_monitor'

    has_uninstall = any(k in normalized for k in ['删除应用', '删除软件', '删除程序', '删除app', '卸载', '移除'])
    has_install = any(k in normalized for k in ['安装'])
    has_store_search = any(k in normalized for k in ['搜索应用', '查找应用', '应用商店'])
    has_app_keyword = any(k in normalized for k in ['应用', '软件', '程序', 'app'])

    if (has_uninstall or has_install or has_store_search) and has_app_keyword:
        return 'store_action'
    if has_uninstall and not any(k in normalized for k in ['打开', '启动', '运行', '生成', '创建', '写', '搜索', '文件', '文件夹', '目录']):
        return 'store_action'
    if has_install and not any(k in normalized for k in ['打开', '启动', '运行', '生成', '创建', '写']):
        return 'store_action'

    if has_open and not has_content and not has_search:
        if _is_single_app_only(text):
            return 'desktop_control'

    if has_search and not has_open and not has_content:
        return 'search_only'

    return None

def _is_single_app_only(text: str) -> bool:
    """判断'打开XX'是否只是单纯启动一个应用，没有其他动作"""
    compound_connectors = ['然后', '再', '并', '而且', '接着', '之后', '同时', '并且']
    if any(w in text for w in compound_connectors):
        return False
    after_open = re.sub(r'^.*?(?:打开|启动|运行)', '', text).strip()
    action_words = ['写', '生成', '创建', '制作', '编写', '搜索', '查找', '编辑',
                    '预览', '查看', '关闭', '删除', '安装', '卸载', '下载', '上传',
                    '结束', '杀', '清理', '优化', '加速', '移动', '复制', '重命名']
    return not any(w in after_open for w in action_words)

def detect_intent(text: str) -> str:
    simple = _is_simple_single_action(text)
    if simple:
        return simple
    return 'llm_decompose'