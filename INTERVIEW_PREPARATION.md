# AI Desktop Agent 项目 - 面试准备指南

## 📋 项目概述

这是一个 **AI Desktop Agent** 桌面智能助手项目，核心功能包括：
- 🎙️ 语音指令处理（STT/TTS）
- 🤖 AI Agent 工作流（支持工具调用）
- 💻 桌面控制与自动化
- 🌐 浏览器/应用自动化
- 📝 内容生成

---

## 🔥 核心技术亮点（面试必问）

### 0. **意图检测与本地快速路径**

**核心文件：**
- [intent_detector.py](apps/server/app/services/intent_detector.py) - 意图检测器
- [response_separator.py](apps/server/app/services/response_separator.py) - 响应分离器（TTS优化）

**面试问题：**

**Q0: 如何实现快速的本地意图检测？**
```python
# intent_detector.py
CONTENT_GENERATE_KEYWORDS = ['创建', '生成', '编写', '制作', '设计', '登录页面', '网页', 'html', '文档', '文章', '代码']
SEARCH_KEYWORDS = ['搜索', '搜一下', '查一下', '查询', '百度', 'google']

def _is_simple_single_action(text: str) -> str | None:
    """
    本地规则只处理3类最简单的情况：
    1. 纯系统监控（"电脑很卡"、"CPU多少"）→ 'system_monitor'
    2. 纯单应用启动，无其他动作（"打开微信"）→ 'desktop_control'
    3. 纯搜索，无其他动作（"搜索Python教程"）→ 'search_only'
    """
    has_optimize = any(k in normalized for k in ['清理', '优化', '加速', '提速'])
    has_monitor = any(k in normalized for k in ['cpu', '内存', 'disk', '监控', '状态', 'c盘', '进程'])
    
    if has_optimize and not has_monitor:
        return 'system_optimize'
    if has_monitor and not has_optimize:
        return 'system_monitor'
    
    has_open = any(k in normalized for k in ['打开', '启动', '运行'])
    has_content = any(k in text for k in CONTENT_GENERATE_KEYWORDS)
    has_search = any(k in text for k in SEARCH_KEYWORDS)
    
    if has_open and not has_content and not has_search:
        if _is_single_app_only(text):  # 确认是单应用启动
            return 'desktop_control'
    
    if has_search and not has_open and not has_content:
        return 'search_only'
    
    return None  # 需要 LLM 分解

def detect_intent(text: str) -> str:
    simple = _is_simple_single_action(text)
    if simple:
        return simple
    return 'llm_decompose'  # 复杂指令交给 LLM
```

**Q0b: 如何将响应分离为展示内容和TTS语音播报？**
```python
# response_separator.py
class ResponseSeparator:
    MAX_TTS_DURATION = 30  # 语音最长30秒
    CHARS_PER_SECOND = 4   # 约4字符/秒
    
    def separate(cls, full_response: str, user_intent: str) -> tuple[str, str]:
        """
        将完整响应拆分为：
        - tts_summary: 适合TTS语音播报（≤30秒）
        - display_content: 适合屏幕展示（保留格式）
        """
        # 1. 提取已有的摘要标记
        existing_summary = cls._extract_existing_summary(text)
        
        # 2. 生成TTS摘要（控制字数）
        tts_summary = cls._generate_tts_summary(
            full_response, 
            max_chars=cls.MAX_TTS_DURATION * cls.CHARS_PER_SECOND
        )
        
        # 3. 清理Markdown格式用于展示
        display_content = cls._prepare_display_content(full_response)
        
        return tts_summary, display_content
```

---

### 1. **Agent 架构与工具调用系统**

**核心文件：**
- [orchestrator.py](apps/server/app/services/llm/orchestrator.py) - Agent 工作流编排
- [executor.py](apps/server/app/services/tools/executor.py) - 工具执行器
- [generator.py](apps/server/app/services/llm/generator.py) - LLM 生成器
- [reviewer.py](apps/server/app/services/llm/reviewer.py) - 响应审核器

**面试问题：**

**Q1: 描述 Agent 的工作流程？**
```
用户输入 → 意图检测 → LLM决定是否需要工具 
→ 执行工具 → LLM基于结果总结 → 返回响应

关键点：
- 两轮 LLM 调用（决策 + 总结）
- 工具调用结果注入上下文
- 支持降级兜底机制
```

**Q2: 如何实现工具调用的 Function Calling？**
```python
# generator.py - LLM 生成器
async def generate_with_tools(message, mode, tools, history_messages):
    # 构建 messages 数组
    messages = history_messages + [{"role": "user", "content": user_prompt}]
    
    # 调用 LLM，传入工具定义
    response_msg = await provider.chat_with_tools(
        messages=messages,
        tools=tools,  # 工具定义
        temperature=0.2,
    )
    
    # 返回 tool_calls
    return {
        "content": response_msg.get("content", ""),
        "tool_calls": response_msg.get("tool_calls"),
    }

# orchestrator.py - Agent 工作流
async def run_agent_workflow(message, tools):
    # 第一轮：LLM 决定是否调工具
    first = await generate_with_tools(message, tools=tools)
    
    if first.get("tool_calls"):
        # 执行工具
        tool_results = await execute_tool_calls(first["tool_calls"])
        
        # 第二轮：LLM 基于结果总结
        second_history = history + [first] + tool_results
        second = await generate_with_tools(
            message="基于上述工具执行结果，给用户一个简洁的总结。",
            tools=None,  # 不再允许工具调用
            history_messages=second_history,
        )
        return {"reply": second.get("content")}
    
    # 无工具：走审核流程
    review_result = await review(message, first_content)
    if review_result["needs_revision"]:
        rewritten = await rewrite(message, first_content, feedback)
        return {"reply": rewritten.get("content")}
```

**Q3: 工具系统如何保证安全性？**
```python
# executor.py - 多层安全防护
async def execute_tool_calls(tool_calls):
    for call in tool_calls:
        name = call["function"]["name"]
        args = json.loads(call["function"]["arguments"])
        
        # 1. 危险命令拦截
        if name == "shell":
            cmd = args.get("command", "")
            blacklist = ["rm -rf /", "format", "del /f /s /q c:\\"]
            if any(b in cmd.lower() for b in blacklist):
                return {"error": "危险命令被拦截"}
        
        # 2. 需确认操作拦截
        if name == "systemControl" and args.get("action") in ("shutdown", "sleep"):
            return {"confirm_required": True, "message": "即将执行关机，请确认？"}
        
        # 3. 路径解析验证
        if name == "app:launch":
            args = _resolve_launch_path(args)  # 自动查找应用路径
            if not os.path.isabs(args.get("path")):
                return {"error": "无效路径"}
        
        # 4. 进程白名单保护（由 Electron 端处理）
```

---

### 2. **多 Provider 负载均衡与容错**

**核心文件：**
- [provider.py](apps/server/app/services/llm/provider.py) - LLM 提供者
- [rate_limiter.py](apps/server/app/services/llm/rate_limiter.py) - 限流器
- [provider_manager.py](apps/server/app/services/provider_manager.py) - Provider 管理

**面试问题：**

**Q4: 如何实现 LLM Provider 的自动切换与容错？**
```python
# provider_manager.py - Provider 管理器
class ProviderManager:
    def _load(self):
        # 从 providers.json 加载配置
        with open(PROVIDERS_CONFIG_FILE) as f:
            data = json.load(f)
            for p in data.get("providers", []):
                self.providers[p["id"]] = ProviderConfig(**p)
    
    async def chat_completion(self, provider_id, messages, **kwargs):
        provider = self.get_provider(provider_id)
        # 使用新的 URL 和 headers 处理
        headers = provider.get_headers()
        full_url = provider.get_full_url()
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(full_url, headers=headers, json=data)
            return resp.json()

# provider.py - LLM 调用封装
class LLMProvider:
    def __init__(self):
        # 优先从 ProviderManager 读取动态配置
        self._provider = self._load_active_provider()
        
        # 降级到 .env 配置
        if not self._provider:
            self.api_key = os.getenv("LLM_API_KEY")
            self.base_url = os.getenv("LLM_BASE_URL")
            self.model = os.getenv("LLM_MODEL")
    
    def _load_active_provider(self):
        for p in pm.providers.values():
            if p.enabled:
                if p.api_key or "localhost" in p.api_url:
                    return p  # 返回第一个启用的 Provider
```

**Q5: 错误分类与降级策略？**
```python
# provider.py
def _classify_provider_error(status_code, response_text):
    if status_code in {400, 413, 414} and any(
        token in response_text.lower() for token in {"context", "token", "too long"}
    ):
        return LLMContextTooLongError("上下文过长")
    
    if status_code == 429:
        return LLMRateLimitError("请求过于频繁")
    
    if status_code >= 500:
        return LLMUpstreamServerError("服务端异常")
    
    return LLMProviderError(f"请求失败: {status_code}")
```

**Q6: 限流器实现原理？**
```python
# rate_limiter.py
class LLMRateLimiter:
    def __init__(self):
        self.min_interval_seconds = 0.5  # 最小请求间隔
        self.cache_ttl_seconds = 120     # 缓存TTL
        self.max_cache_entries = 128      # 最大缓存条目
        self._cache: dict[str, CacheEntry] = {}
    
    async def wait_turn(self):
        # 确保请求间隔
        wait_seconds = self.min_interval_seconds - (now - self._last_request_ts)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        self._last_request_ts = time.time()
    
    def get_cached(self, **kwargs) -> str | None:
        key = self._make_cache_key(**kwargs)
        entry = self._cache.get(key)
        if entry and entry.expires_at > time.time():
            return entry.value
        return None
```

---

### 3. **上下文管理与历史对话**

**核心文件：**
- [context_manager.py](apps/server/app/services/context_manager.py) - 上下文管理器
- [storage.py](apps/server/app/services/storage.py) - SQLite 存储
- [response_cleaner.py](apps/server/app/utils/response_cleaner.py) - 响应清洗器

**面试问题：**

**Q7: 如何管理长对话的上下文？**
```python
# context_manager.py
class ContextManager:
    # 多种压缩策略
    NONE = "none"           # 不压缩
    SLIDING_WINDOW = "sliding"  # 滑动窗口
    SUMMARY = "summary"     # 摘要压缩
    HYBRID = "hybrid"       # 混合策略
    
    def process(self, history, current_message):
        # 1. 规范化历史消息
        turns = self._normalize_history(history)
        
        # 2. 选择压缩策略
        if len(turns) <= self.max_turns:
            return [turn_to_dict(turn) for turn in turns], None
        
        # 3. 摘要旧消息 + 保留最近
        return self._apply_summary_compression(turns, current_message)
    
    def _apply_summary_compression(self, turns, current_message):
        # 摘要旧消息
        summary = self._generate_history_summary(old_turns)
        recent = self._extract_recent_turns(turns, self.max_turns)
        
        context = [{"role": "system", "content": f"历史摘要：{summary}"}]
        context.extend([turn_to_dict(t) for t in recent])
        return context, summary
```

**Q8: Token 估算与预算管理？**
```python
def estimate_tokens(self, text: str) -> int:
    # 中文字符 = 1.5 tokens
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    # 英文单词 = 0.25 tokens
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    # 其他字符 = 0.25 tokens
    other_chars = len(text) - chinese_chars - english_words
    
    return int(chinese_chars * 1.5 + english_words / 4 + other_chars * 0.25)
```

**Q9: SQLite 数据库设计与备份？**
```python
# storage.py - 表结构
# conversations (id, title, role_prompt, created_at, updated_at)
# conversation_messages (id, conversation_id, role, content, metadata_json, created_at)
# shortcuts (id, name, content, category)
# favorites (id, kind, target_id, label, payload_json)

# 热备份机制
def backup_database():
    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(backup_path)
    source.backup(dest)  # 使用 SQLite backup API
    dest.close()
    source.close()
```

**Q10: 响应清洗如何防止信息泄露？**
```python
# response_cleaner.py
class ResponseCleaner:
    LEAKAGE_PATTERNS = [
        r"你是一个偏桌面效率.*?AI Agent",
        r"角色设定[：:]",
        r"系统监控摘要[：:]",
        r"语音上下文摘要[：:]",
        r"审核意见[：:]",
    ]
    
    def clean(self, text: str) -> str:
        # 移除代码块包装
        result = self._remove_code_block_wrappers(text)
        
        # 应用所有清洗规则
        for pattern, replacement in self.INTERNAL_PATTERNS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        # 检查泄露
        if self.contains_leakage(result):
            return LEAKAGE_FALLBACK_MESSAGE
        
        return result
```

---

### 4. **FastAPI 与异步架构**

**核心文件：**
- [main.py](apps/server/app/main.py) - FastAPI 应用入口
- [voice.py](apps/server/app/api/voice.py) - 语音指令 API (1220行)
- [agent.py](apps/server/app/api/agent.py) - Agent API

**面试问题：**

**Q11: FastAPI 异步编程模型？**
```python
# main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    init_storage()
    yield
    # 关闭时清理

app = FastAPI(lifespan=lifespan)

# 异步请求处理
@router.post("/command", response_model=AgentResponse)
async def handle_voice_command(payload: VoiceCommandRequest):
    # 异步 LLM 调用
    response = await provider.chat(
        system_prompt=GENERATOR_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    
    # 异步工具执行
    results = await execute_tool_calls(tool_calls)
    
    return response
```

**Q12: 中间件与异常处理？**
```python
# UTF-8 编码保证
@app.middleware("http")
async def ensure_utf8(request: Request, call_next):
    response = await call_next(request)
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

# 全局异常捕获
@app.middleware("http")
async def error_handler(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})
```

---

### 5. **语音处理架构 (STT/TTS - Faster-Whisper)**

**核心文件：**
- [voice_provider.py](apps/server/app/services/voice_provider.py) - 语音提供者
- [voice.py](apps/server/app/api/voice.py) - 语音 API
- [local-whisper-stt/server.py](local-whisper-stt/server.py) - 本地 Faster-Whisper STT 服务

**面试问题：**

**Q13: 语音链路完整流程？**
```
麦克风录音 → MediaRecorder → Base64编码
    ↓
本地 Faster-Whisper STT 服务 (端口 5051)
    ↓
normalize_voice_text() 文本规范化
    ↓
detect_intent() 意图检测
    ↓
LLM Agent 工作流
    ↓
Edge-TTS 语音合成
    ↓
音频播放 / 浏览器 speechSynthesis 回退
```

**Q14: Faster-Whisper 本地语音识别实现？**
```python
# local-whisper-stt/server.py - 本地 Whisper 服务
from faster_whisper import WhisperModel

# 模型本地缓存，支持多种精度
MODEL_NAME = os.getenv("WHISPER_MODEL", "base")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE", "float32")  # float32, int8

# 本地模型加载
model_path = os.path.join(local_model_path, MODEL_NAME)
model = WhisperModel(model_path, compute_type=COMPUTE_TYPE)

@app.post("/v1/audio/transcriptions")
async def transcribe(file: UploadFile, language: str = Form("zh")):
    # 1. 接收原始音频 (webm/ogg等格式)
    # 2. 使用 ffmpeg 转码为 16kHz WAV
    subprocess.run([
        'ffmpeg', '-i', input_path,
        '-ar', '16000',      # 采样率 16kHz
        '-ac', '1',          # 单声道
        '-c:a', 'pcm_s16le', # 16位 PCM
        output_path
    ], check=True)
    
    # 3. Faster-Whisper 转录
    segments, info = model.transcribe(wav_path, language=language)
    text = "".join([segment.text for segment in segments])
    
    return {"text": text.strip(), "language": info.language}
```

**Q15: 为什么选择 Faster-Whisper 而不是云端 Whisper？**
```
优势：
✅ 完全本地运行，无需网络，保护隐私
✅ 比 OpenAI Whisper 快 2-4 倍 (CTranslate2 优化)
✅ 支持 CPU 推理 (int8/float16)
✅ 零 API 成本，支持离线使用
✅ 兼容 OpenAI API 格式，便于切换

技术细节：
- 使用 CTranslate2 加速推理
- 支持模型：tiny, base, small, medium, large-v2/v3
- 可配置 compute_type: float32, float16, int8, int8_float16
```

（Q16 已整合到 Q15）

---

### 6. **Electron 桌面应用架构**

**核心文件：**
- [main.cjs](apps/desktop/electron/main.cjs) - Electron 主进程
- [preload.cjs](apps/desktop/electron/preload.cjs) - 预加载脚本
- [actionExecutor.cjs](apps/desktop/electron/actionExecutor.cjs) - 动作执行器
- [useVADVoice.ts](apps/desktop/src/hooks/useVADVoice.ts) - VAD 语音检测

**面试问题：**

**Q15: Electron 进程间通信？**
```javascript
// preload.cjs - 安全桥接
contextBridge.exposeInMainWorld('electronAPI', {
    executeTool: (tool, params) => 
        ipcRenderer.invoke('tool-execute', { tool, params }),
    
    getSystemMetrics: () => 
        ipcRenderer.invoke('system-metrics'),
});

// main.cjs - 主进程处理
ipcMain.handle('tool-execute', async (event, { tool, params }) => {
    // 执行工具操作
    if (tool === 'process:kill') {
        return await killProcess(params.name);
    }
    return { ok: true, result };
});
```

**Q16: VAD (Voice Activity Detection) 实现？**
```typescript
// useVADVoice.ts
export function useVADVoice() {
    // 使用 Silero VAD 模型进行语音活动检测
    // 支持 WebSocket 实时流式处理
    // 实现唤醒词检测与打断功能
}
```

---

## 📊 技术栈总结

| 层级 | 技术 | 关键点 |
|------|------|--------|
| 后端框架 | FastAPI | 异步、类型安全、中间件 |
| AI/ML | OpenAI/Claude API | Function Calling、多Provider |
| 数据库 | SQLite | 热备份、事务支持 |
| 语音 STT | Faster-Whisper | 本地推理、离线可用、CTranslate2加速 |
| 语音 TTS | Edge-TTS | 微软云端、高质量中文语音 |
| 桌面 | Electron | IPC、安全沙箱 |
| 前端 | React + TypeScript | Hooks、状态管理 |
| 构建 | Vite + pnpm workspace | monorepo |

---

## 🎯 高级面试问题

### Q17: 如何设计一个高可用的 Agent 系统？

**答案要点：**
1. **多级降级策略**
   - LLM → 本地规则 → 关键词匹配
   - 云端语音 → 浏览器原生 → 纯文本

2. **缓存与限流**
   - 请求缓存 (TTL 120s)
   - 最小请求间隔 (0.5s)
   - 最大缓存条目 (128)

3. **错误分类与恢复**
   - 限流 → 等待后重试
   - 服务端错误 → 切换 Provider
   - 上下文过长 → 自动压缩

### Q18: 如何优化 LLM 调用成本？

**答案要点：**
```python
# 1. 缓存重复请求
if cached := rate_limiter.get_cached(**kwargs):
    return cached

# 2. 上下文压缩
history = compress_history(history, max_tokens=6000)

# 3. 降级到轻量模型
try:
    result = await llm.chat(model="gpt-4o")
except RateLimitError:
    result = await llm.chat(model="gpt-4o-mini")

# 4. 避免不必要的长输出
temperature=0.2  # 低随机性
```

---

## 🔗 需要深入学习的完整文件清单

### 核心必须掌握：
1. ✅ [orchestrator.py](apps/server/app/services/llm/orchestrator.py) - Agent 工作流编排
2. ✅ [provider.py](apps/server/app/services/llm/provider.py) - LLM 调用封装
3. ✅ [generator.py](apps/server/app/services/llm/generator.py) - LLM 生成器
4. ✅ [reviewer.py](apps/server/app/services/llm/reviewer.py) - 响应审核器
5. ✅ [context_manager.py](apps/server/app/services/context_manager.py) - 上下文管理
6. ✅ [executor.py](apps/server/app/services/tools/executor.py) - 工具执行器
7. ✅ [intent_detector.py](apps/server/app/services/intent_detector.py) - 意图检测器
8. ✅ [response_separator.py](apps/server/app/services/response_separator.py) - 响应分离器

### 理解架构：
9. 📖 [main.py](apps/server/app/main.py) - FastAPI 应用结构
10. 📖 [storage.py](apps/server/app/services/storage.py) - SQLite 数据库设计
11. 📖 [rate_limiter.py](apps/server/app/services/llm/rate_limiter.py) - 限流与缓存
12. 📖 [provider_manager.py](apps/server/app/services/provider_manager.py) - Provider 管理
13. 📖 [response_cleaner.py](apps/server/app/utils/response_cleaner.py) - 响应清洗
14. 📖 [voice.py](apps/server/app/api/voice.py) - 语音指令 API (1220行)
15. 📖 [agent.py](apps/server/app/api/agent.py) - Agent API

### 扩展功能：
16. 📖 [voice_provider.py](apps/server/app/services/voice_provider.py) - 语音提供者
17. 📖 [local-whisper-stt/server.py](local-whisper-stt/server.py) - 本地 Faster-Whisper STT 服务
18. 📖 [desktop_controller.py](apps/server/app/services/desktop_controller.py) - 桌面控制
19. 📖 [browser_controller.py](apps/server/app/services/browser_controller.py) - 浏览器控制
20. 📖 [office_automation.py](apps/server/app/services/office_automation.py) - Office 自动化
21. 📖 [software_index.py](apps/server/app/services/software_index.py) - 软件索引

---

## 💡 面试话术建议

### 当被问到项目难点时：
> "项目最大的挑战是构建一个可靠的多级降级系统。当 LLM 服务不可用时，系统需要能够：
> 1. 从本地规则引擎快速响应简单请求（intent_detector.py）
> 2. 通过关键词匹配兜底复杂请求
> 3. 保证关键功能（如应用启动）始终可用
> 我实现了 ContextManager 来管理对话历史，确保长对话不会超出 LLM 的上下文限制。"

### 当被问到技术选型时：
> "选择 FastAPI 是因为它的异步特性非常适合 I/O 密集型的 Agent 工作流。
> SQLite 用于本地存储是因为它零配置、支持热备份，非常适合桌面应用的场景。
> Electron 则是为了统一桌面端的工具调用能力（进程管理、文件操作等）。"

---

**祝你面试顺利！🎉**
