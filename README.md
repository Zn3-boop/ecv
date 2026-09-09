# AI Desktop Agent

当前已完成：
- pnpm workspace 根配置
- FastAPI 基础服务骨架
- `/health` 健康检查接口
- `/chat/agent` 多模型协作接口
- `/voice/command` 语音指令接口
- `/voice/runtime` 云端语音运行时能力接口
- `/voice/transcribe` 云端 ASR 预留接口
- `/voice/synthesize` 云端 TTS 预留接口
- Agent 工作流已支持注入系统监控上下文与语音上下文
- 已支持通过环境变量接入真实大模型（默认兼容 OpenRouter Chat Completions）
- 已新增 `VoiceProvider` 抽象，支持浏览器能力向云端语音 SDK 平滑迁移

## 启动后端

### 1. 安装 Python 依赖
```bash
pip install -r apps/server/requirements.txt
```

### 2. 启动 FastAPI
```bash
pnpm dev:server
```

### 3. 打开接口文档
访问：
- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/health

## 当前后端接口
- `GET /`
- `GET /health`
- `POST /chat/agent`
- `GET /storage/conversations`
- `POST /storage/conversations`
- `GET /storage/conversations/{conversation_id}`
- `PUT /storage/conversations/{conversation_id}`
- `DELETE /storage/conversations/{conversation_id}`
- `GET /storage/conversations/{conversation_id}/messages`
- `POST /storage/conversations/{conversation_id}/messages`
- `GET /storage/shortcuts`
- `POST /storage/shortcuts`
- `DELETE /storage/shortcuts/{shortcut_id}`
- `GET /storage/favorites`
- `POST /storage/favorites`
- `DELETE /storage/favorites/{favorite_id}`
- `GET /voice/runtime`
- `POST /voice/transcribe`
- `POST /voice/transcribe-upload`
- `POST /voice/synthesize`
- `POST /voice/command`
- `POST /automation/handle-alert`
- `POST /agent/command`
- `POST /agent/solve-problems`

### `/chat/agent` 请求示例
```json
{
  "message": "帮我规划桌面 AI Agent 的第一阶段开发步骤",
  "mode": "roadmap",
  "conversation_id": 1,
  "role_prompt": "你是一个偏运维诊断与桌面效率助手风格的 AI Agent",
  "system_context": {
    "cpu": { "usagePercent": 82.5, "cores": 8 },
    "memory": { "usagePercent": 76.2, "usedLabel": "12.1 GB", "totalLabel": "15.9 GB" },
    "network": { "defaultInterface": "Wi-Fi" },
    "processes": {
      "topProcesses": [
        { "name": "python", "cpu": 32.1, "memoryLabel": "1.2 GB" },
        { "name": "chrome", "cpu": 18.4, "memoryLabel": "2.8 GB" }
      ]
    },
    "alerts": [
      { "level": "warning", "type": "cpu", "message": "当前 CPU 使用率达到 82.5%" }
    ]
  },
  "voice_context": {
    "source": "manual-text",
    "locale": "zh-CN",
    "device": "desktop"
  }
}
```

### `/voice/command` 请求示例
```json
{
  "transcript": "帮我看看当前 CPU 状态，并给出处置建议",
  "mode": "voice",
  "system_context": {
    "cpu": { "usagePercent": 88.4, "cores": 8 },
    "memory": { "usagePercent": 73.2, "usedLabel": "11.6 GB", "totalLabel": "15.9 GB" },
    "network": { "defaultInterface": "Wi-Fi" },
    "processes": {
      "topProcesses": [
        { "name": "ollama", "cpu": 44.7, "memoryLabel": "2.4 GB" },
        { "name": "chrome", "cpu": 14.3, "memoryLabel": "1.8 GB" }
      ]
    },
    "alerts": [
      { "level": "critical", "type": "cpu", "message": "当前 CPU 使用率达到 88.4%" }
    ]
  },
  "voice_context": {
    "source": "microphone",
    "locale": "zh-CN",
    "device": "desktop",
    "session_id": "voice-session-001",
    "turn_id": "turn-001",
    "interruption_enabled": true
  }
}
```

### `/voice/transcribe` 请求示例
```json
{
  "audio_base64": "BASE64_AUDIO_BYTES",
  "filename": "voice.webm",
  "mime_type": "audio/webm",
  "locale": "zh-CN",
  "session_id": "voice-session-001",
  "turn_id": "turn-001",
  "wake_word_enabled": true,
  "interruption_enabled": true
}
```

### `/voice/synthesize` 请求示例
```json
{
  "text": "语音指令已处理。当前 CPU 使用率较高，建议先关闭高占用进程。",
  "format": "mp3",
  "session_id": "voice-session-001",
  "turn_id": "turn-001",
  "interruption_token": "tts-token-001"
}
```

## 真实大模型配置
1. 复制 `apps/server/.env.example` 为 `apps/server/.env`
2. 配置以下变量：
```bash
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openai/gpt-4o-mini
LLM_TIMEOUT_SECONDS=45
LLM_APP_NAME=AI Desktop Agent
LLM_HTTP_REFERER=http://localhost:3000
```
3. 重新启动 FastAPI 服务

## 云端语音配置
### 方案 A：免费优先，先把链路跑通（推荐新手先用这个）
```bash
VOICE_PROVIDER=mock
VOICE_API_KEY=
VOICE_BASE_URL=https://api.openai.com/v1
VOICE_STT_MODEL=gpt-4o-mini-transcribe
VOICE_TTS_MODEL=gpt-4o-mini-tts
VOICE_TTS_VOICE=alloy
VOICE_TIMEOUT_SECONDS=60
```

- `VOICE_PROVIDER=mock`：默认走占位模式
- 这时前端继续使用浏览器原生能力：
  - STT：浏览器 Web Speech / MediaRecorder + 本地回退
  - TTS：浏览器 `speechSynthesis`
- 优点：**零额外成本、最容易跑通、最适合先验证产品闭环**
- 建议：你现在先保持这个模式，把“录音 → 转写 → Agent → 播报”整条链路先打通

### 方案 B：切到 OpenAI 官方语音（后续更稳）
```bash
VOICE_PROVIDER=openai
VOICE_API_KEY=sk-...
VOICE_BASE_URL=https://api.openai.com/v1
VOICE_STT_MODEL=gpt-4o-mini-transcribe
VOICE_TTS_MODEL=gpt-4o-mini-tts
VOICE_TTS_VOICE=alloy
VOICE_TIMEOUT_SECONDS=60
```

- 当配置真实 `VOICE_API_KEY` 且 provider 不是 `mock` 时：
  - `/voice/transcribe` 可转发到云端 ASR
  - `/voice/synthesize` 可返回云端音频
  - `/voice/command` 会尝试附带 `tts_audio_base64`

### 为什么暂时不推荐你直接用 OpenRouter 语音
- 你当前已经验证：**同一把 key 可访问模型列表，但 `/audio/speech` 返回 401**
- 这说明 OpenRouter 文本链路可用，**不等于** OpenAI 风格语音端点也能直接用
- 所以对新手最省心的方式是：
  1. **文本模型继续走 OpenRouter**
  2. **语音先保持 `mock` 免费跑通**
  3. 后面真要上云端语音，再切 OpenAI 官方兼容配置

## `/voice/transcribe-upload` 请求示例
使用 `multipart/form-data`：
- `file`: 音频文件（如 `voice.webm`）
- `locale`: `zh-CN`
- `session_id`: `voice-session-001`
- `turn_id`: `turn-001`
- `wake_word_enabled`: `true`
- `interruption_enabled`: `true`

## 当前桌面语音链路
- 支持 `MediaRecorder -> /voice/transcribe-upload -> /voice/command` 直传链路
- 若后端尚未升级 multipart 接口，前端会自动回退到 `/voice/transcribe` 的 base64 JSON 上传
- 支持云端 TTS 音频优先播放，失败后回退浏览器 `speechSynthesis`
- 支持前端切换“优先云端语音链路 / 唤醒词 / 播报打断”
- 已展示 `voice runtime / session_id / turn_id / cloud audio status` 运行态信息

## 本轮新增能力
1. 新增 SQLite 本地存储层，默认保存在 `apps/server/data/agent.db`
2. 新增会话记录 CRUD、消息记录 CRUD、快捷指令 CRUD、收藏管理 CRUD API
3. `/chat/agent` 已支持 `conversation_id` + `role_prompt`，可把最近对话历史拼入 Agent 请求，实现轻量上下文记忆
4. 启动 FastAPI 时会自动初始化本地数据表

## 下一步计划
1. 在桌面端 UI 接入会话列表、快捷指令、收藏面板
2. 补 Electron 托盘、置顶、迷你模式、开机自启
3. 接入真实流式 ASR / 流式 TTS，降低长回复等待时间
4. 增加播报打断控制与更自然的语音交互状态机
5. 补桌面控制白名单动作（打开目录、执行诊断、清理缓存）
6. 增加 shadcn/ui 主题、Vercel 预览版、Stripe 付费授权与 Win/Mac 打包脚本

## 自动处置增强说明
- Electron 主进程在触发 `/automation/handle-alert` 时，已自动附带实时 `system_context`
- FastAPI 自动处置接口现在会走 Agent 工作流，而不再只是静态 action map
- 返回结果中会包含 `reply / review_notes / review_source / used_system_context`
- 这意味着自动处置建议已经能基于当前机器的实时监控快照动态生成
