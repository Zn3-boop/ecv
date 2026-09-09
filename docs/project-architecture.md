# AI Desktop Agent 项目架构文档

## 📁 项目结构

```
d:\ecv\
├── apps/
│   ├── desktop/          # Electron 桌面前端
│   │   ├── electron/    # Electron 主进程代码
│   │   │   ├── main.cjs           # 主进程入口
│   │   │   ├── preload.cjs       # 预加载脚本 (安全桥接)
│   │   │   ├── actionExecutor.cjs # 动作执行器
│   │   │   ├── desktop-executor.cjs # 桌面工具执行器
│   │   │   └── main/             # VAD 语音检测模块
│   │   └── src/         # React 前端
│   │       ├── components/       # React 组件
│   │       ├── hooks/            # 自定义 Hooks
│   │       ├── types/            # TypeScript 类型定义
│   │       └── App.tsx           # 主应用组件
│   │
│   └── server/         # Python FastAPI 后端
│       └── app/
│           ├── api/              # API 路由
│           │   ├── voice.py      # 语音指令处理
│           │   ├── agent.py      # Agent 核心
│           │   ├── content_generator.py # 内容生成
│           │   ├── automation.py # 自动化任务
│           │   └── browser.py    # 浏览器控制
│           │
│           ├── services/         # 业务服务
│           │   ├── llm/         # LLM 相关
│           │   │   ├── provider.py     # LLM 提供者
│           │   │   ├── generator.py   # 生成器
│           │   │   ├── orchestrator.py # 编排器
│           │   │   └── context_builder.py # 上下文构建
│           │   │
│           │   ├── tools/       # 工具系统
│           │   │   ├── schema.py      # 工具定义
│           │   │   └── executor.py    # 工具执行
│           │   │
│           │   ├── desktop_controller.py # 桌面控制
│           │   ├── browser_controller.py # 浏览器控制
│           │   └── office_automation.py  # Office 自动化
│           │
│           └── data/
│               └── providers.json # LLM Provider 配置
│
├── packages/           # 共享包
├── edge-tts-api/       # Edge TTS 语音合成服务
├── local-whisper-stt/  # 本地 Whisper 语音识别
└── docs/              # 文档
```

---

## 🔄 系统数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户交互层                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │  麦克风输入  │    │  文本输入   │    │  语音识别 (Whisper)  │  │
│  └──────┬──────┘    └──────┬──────┘    └──────────┬──────────┘  │
└─────────┼───────────────────┼──────────────────────┼─────────────┘
          │                   │                      │
          ▼                   ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      React 前端 (Electron)                       │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ VoiceControl │    │TasksPanel   │    │ ConversationPanel   │  │
│  └──────┬──────┘    └──────┬──────┘    └──────────┬──────────┘  │
│         │                   │                      │              │
│         └───────────────────┼──────────────────────┘              │
│                             │                                     │
│                    ┌────────▼────────┐                           │
│                    │  useApp Hook   │                           │
│                    │  (状态管理)    │                           │
│                    └────────┬────────┘                           │
└─────────────────────────────┼───────────────────────────────────┘
                              │ HTTP
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI 后端 (Python)                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    /voice/command API                      │  │
│  │  1. 文本规范化 (normalize)                               │  │
│  │  2. 意图检测 (intent detection)                           │  │
│  │  3. 命令解析/分解 (parse/decompose)                       │  │
│  │  4. 安全过滤 (validate)                                   │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                   │
│         ┌───────────────────┼───────────────────┐               │
│         ▼                   ▼                   ▼               │
│  ┌────────────┐    ┌────────────┐    ┌────────────────────┐  │
│  │   LLM      │    │  本地规则   │    │   本地降级分解      │  │
│  │  Orchestrator│   │  (快速路径) │    │  (LLM不可用时)     │  │
│  └─────┬──────┘    └────────────┘    └────────────────────┘  │
│        │                                                        │
│        ▼                                                        │
│  ┌────────────────────────────────────────────────────────┐   │
│  │                    Command 执行                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │app:launch│ │process:  │ │content:  │ │browser:  │  │   │
│  │  │          │ │kill     │ │generate │ │search   │  │   │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │   │
│  └───────┼────────────┼─────────────┼─────────────┼────────┘   │
│          │            │             │             │           │
│          ▼            ▼             ▼             ▼           │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ │
│  │  Desktop  │ │  Process   │ │  LLM API   │ │  Browser   │ │
│  │Controller │ │ Controller │ │  (Word等)  │ │Controller  │ │
│  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ │
└────────┼──────────────┼─────────────┼─────────────┼────────┘
         │              │             │             │
         ▼              ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      系统执行层                                    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │
│  │  打开应用   │ │  结束进程  │ │  生成文档  │ │  浏览器操作 │    │
│  │  ms-settings│ │  taskkill │ │  python-  │ │  selenium │    │
│  │  WINWORD   │ │           │ │  docx     │ │           │    │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 核心模块说明

### 1. 语音指令处理 (`voice.py`)

```
输入: "打开设置" 或 "打开word写一篇关于智能的文章"
  ↓
normalize_voice_text() - 规范化文本
  ↓
detect_intent() - 检测意图类型
  ↓
handle_app_launch_intent() - 处理应用启动
  ↓
parse_user_command() - 解析命令
  ↓
_validate_and_filter_commands() - 安全过滤
  ↓
返回: Command[] + 回复文本
```

### 2. 工具系统 (`tools/`)

**支持的工具类型：**

| 工具名 | 功能 | 示例 |
|--------|------|------|
| `app:launch` | 启动应用 | `app:launch {path: "WINWORD.EXE"}` |
| `process:kill` | 结束进程 | `process:kill {name: "chrome.exe"}` |
| `content:generate` | 生成内容 | `content:generate {task: "文章", type: "word"}` |
| `browser:search` | 浏览器搜索 | `browser:search {query: "AI"}` |
| `system:info` | 获取系统信息 | `system:info {}` |
| `disk:cleanup` | 磁盘清理 | `disk:cleanup {}` |

### 3. LLM Provider (`llm/provider.py`)

支持多 Provider 自动切换：

```json
{
  "providers": [
    {"id": "zhipu", "name": "智谱 AI", "enabled": true},
    {"id": "openrouter", "name": "OpenRouter", "enabled": true},
    {"id": "ollama", "name": "Ollama (本地)", "enabled": false}
  ]
}
```

### 4. 上下文管理 (`context_builder.py`)

- **策略**: auto / compact / expand / manual
- **功能**: 历史记录压缩、token 优化、摘要生成

---

## 🔒 安全机制

### 1. 进程白名单 (`PROCESS_WHITELIST`)

```javascript
// 绝对保护 - 系统核心进程
system: ['explorer.exe', 'svchost.exe', ...]

// 工作区保护 - 常用办公应用
work: ['Code.exe', 'chrome.exe', 'WINWORD.EXE', ...]
```

### 2. 路径白名单 (`FILE_ACTION_ROOTS`)

```javascript
const FILE_ACTION_ROOTS = [
  app.getPath('desktop'),
  app.getPath('documents'),
  app.getPath('downloads'),
  // ...
]
```

### 3. 工具白名单

只有白名单内的工具才能执行，防止恶意命令。

---

## 🛠️ 常用命令

### 启动服务

```bash
# 后端
cd d:\ecv\apps\server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 前端
cd d:\ecv\apps\desktop
pnpm dev

# 同时启动
d:\ecv\start_all.bat
```

### 测试 API

```bash
# 语音指令
curl -X POST http://127.0.0.1:8000/voice/command \
  -H "Content-Type: application/json" \
  -d '{"transcript": "打开设置"}'

# 内容生成
curl -X POST http://127.0.0.1:8000/content/generate \
  -H "Content-Type: application/json" \
  -d '{"task": "一篇关于AI的文章", "content_type": "word"}'
```

---

## 📝 关键配置文件

| 文件 | 用途 |
|------|------|
| `apps/server/app/data/providers.json` | LLM API 配置 |
| `apps/server/.env` | 环境变量 (API密钥等) |
| `apps/desktop/vite.config.ts` | Vite 构建配置 |

---

## 🔧 扩展指南

### 添加新工具

1. 在 `tools/schema.py` 定义工具结构
2. 在 `actionExecutor.cjs` 实现执行逻辑
3. 在 `preload.cjs` 的 `ALLOWED_TOOLS` 添加工具名

### 添加新 Provider

1. 在 `providers.json` 添加配置
2. 在 `llm/provider.py` 实现调用逻辑

### 添加新 Intent

1. 在 `intent_detector.py` 添加检测逻辑
2. 在 `voice.py` 添加处理函数

---

*文档更新时间: 2026-06-18*
