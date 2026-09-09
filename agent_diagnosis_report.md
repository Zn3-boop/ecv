# Agent 项目诊断报告
生成时间: 2026-06-08 20:18:24.622241

## 1. 项目文件结构 (Top 20)

- `apps\server\app\api\automation.py` (54038 bytes)
- `apps\server\app\api\voice.py` (51617 bytes)
- `apps\server\app\services\system_app_controller.py` (28002 bytes)
- `apps\server\app\services\storage.py` (26447 bytes)
- `apps\server\app\services\voice_provider.py` (18889 bytes)
- `apps\server\app\services\llm\generator.py` (17796 bytes)
- `apps\server\app\services\task_orchestrator.py` (17720 bytes)
- `apps\server\app\services\software_index.py` (17626 bytes)
- `apps\server\app\api\task_workflow.py` (14929 bytes)
- `apps\server\app\services\context_manager.py` (14658 bytes)
- `apps\server\app\services\task_filter.py` (13082 bytes)
- `apps\server\app\api\agent.py` (13065 bytes)
- `apps\server\app\services\office_automation.py` (12868 bytes)
- `apps\server\app\api\content_generator.py` (11976 bytes)
- `apps\server\app\services\tool_registry.py` (11425 bytes)
- `apps\server\app\api\system_app.py` (10842 bytes)
- `apps\server\app\services\desktop_controller.py` (10516 bytes)
- `apps\server\app\services\agent_workflow.py` (9771 bytes)
- `apps\server\test_response_cleaning.py` (9449 bytes)
- `test_auto_tasks_v2.py` (9128 bytes)

总计 Python 文件: 119 个

## 2. API 路由表


### apps\server\app\api\agent.py (prefix: /agent)
- `POST /command`
- `POST /solve-problems`

### apps\server\app\api\automation.py (prefix: /automation)
- `POST /handle-alert`

### apps\server\app\api\browser.py (prefix: /browser)
- `POST /intent`
- `POST /execute`
- `POST /nlp`
- `GET /prompt`
- `POST /search`

### apps\server\app\api\chat.py (prefix: /chat)
- `POST /agent`
- `POST /context/compress`
- `GET /history/search`

### apps\server\app\api\content_generator.py (prefix: /content)
- `POST /generate`
- `POST /browser/generate`

### apps\server\app\api\desktop.py (prefix: /desktop)
- `POST /find`
- `POST /open`
- `POST /file/open`
- `POST /close`
- `GET /running`
- `POST /screenshot`

### apps\server\app\api\generator_settings.py (prefix: /content/settings)
- `GET /`
- `POST /`
- `POST /reset`
- `GET /modes`
- `POST /modes/toggle`

### apps\server\app\api\health.py (prefix: /health)

### apps\server\app\api\provider.py (prefix: /provider)
- `GET /`
- `POST /`
- `GET /{provider_id}`
- `PUT /{provider_id}`
- `DELETE /{provider_id}`
- `POST /{provider_id}/test`
- `POST /chat`
- `POST /preset/minimax`
- `POST /preset/ollama`

### apps\server\app\api\screenshot.py (prefix: /screenshot)
- `POST /capture`
- `POST /capture-window`

### apps\server\app\api\storage.py (prefix: /storage)
- `GET /conversations`
- `POST /conversations`
- `GET /conversations/{conversation_id}`
- `PUT /conversations/{conversation_id}`
- `DELETE /conversations/{conversation_id}`
- `GET /conversations/{conversation_id}/messages`
- `POST /conversations/{conversation_id}/messages`
- `GET /shortcuts`
- `POST /shortcuts`
- `DELETE /shortcuts/{shortcut_id}`
- `GET /favorites`
- `POST /favorites`
- `DELETE /favorites/{favorite_id}`
- `POST /backup`
- `GET /backups`
- `POST /backups/{backup_name}/restore`
- `GET /history/search`

### apps\server\app\api\store.py (prefix: /store)
- `GET /status`
- `POST /search`
- `POST /install`
- `POST /uninstall`
- `GET /installed`

### apps\server\app\api\system_app.py (prefix: /system-app)
- `POST /execute`
- `POST /intent`
- `POST /nlp`
- `POST /nlp-confirmed`
- `GET /list`
- `GET /prompt`
- `POST /cleanup-memory`
- `POST /search-file`

### apps\server\app\api\task_filter.py (prefix: /task-filter)
- `POST /filter`
- `POST /validate`
- `POST /test`

### apps\server\app\api\task_workflow.py (prefix: /task-workflow)
- `POST /create`
- `GET /status/{workflow_id}`
- `GET /commands/{workflow_id}`
- `POST /execute-task`
- `POST /execute-all`

### apps\server\app\api\tools.py (prefix: /tools)
- `POST /suggest`
- `POST /execute`

### apps\server\app\api\voice.py (prefix: /voice)
- `GET /runtime`
- `GET /status`
- `POST /transcribe`
- `POST /transcribe-upload`
- `POST /synthesize`
- `POST /command`

## 3. 工具定义


### apps\server\app\api\automation.py
- `app:launch`
- `clipboard:write`
- `content:generate`
- `disk:cleanup`
- `disk:cleanup_advanced`
- `disk:list`
- `file:delete`
- `file:list`
- `file:read`
- `file:search`
- `file:write`
- `network:request`
- `process:kill`
- `process:list`
- `process:top`
- `system:cleanmgr`
- `system:command`
- `system:env`
- `system:hibernate`
- `system:info`
- `system:recycle`
- `temp:cleanup`
- `temp:scan`

### apps\server\app\api\task_workflow.py
- `app:launch`
- `browser:search`
- `content:generate`
- `desktop:generic`

### apps\server\app\api\voice.py
- `app:close`
- `app:launch`
- `browser:open`
- `content:generate`
- `process:kill`
- `process:list`
- `window:close`

### apps\server\app\services\task_filter.py
- `browser:open`
- `disk:usage`
- `memory:usage`
- `process:kill`
- `process:list`
- `process:top`
- `system:info`

### apps\server\app\services\tool_registry.py
- `app:launch`
- `disk:cleanup`
- `disk:list`
- `file:list`
- `file:search`
- `network:request`
- `process:kill`
- `process:list`
- `process:top`
- `system:info`
- `temp:cleanup`
- `temp:scan`

### apps\server\app\services\llm\generator.py
- `disk:cleanup`

### apps\server\app\services\tools\executor.py
- `app:launch`

## 4. System Prompt 摘要


### SYSTEM_PROMPT (文件: apps\server\app\services\agent_workflow.py, 长度: 756)
```
你是 AI Desktop Agent，一个真正的桌面运维专家。  你的工作流程： 1. 观察：分析用户请求和系统数据 2. 思考：判断问题原因，决定是否需要搜索外部知识 3. 行动：调用工具收集更多信息或直接解决问题 4. 验证：检查执行结果，确认问题是否解决  核心能力： - 你能判断进程是否危险（如病毒、挖矿程序、流氓软件） - 你能判断哪些文件可以安全删除 - 你能根据系统状态给出具体、可操作的解决方案 - 你不会只是罗列数据，而是给出结论和行动  判断规则（内置知识）： - 高CPU进程：如果是 chrome.exe/node.exe/electron.exe 等正常程序，建议关闭标签页而非结束进程 - 如果是 svchost.exe/system 等系统进程，绝对不能结束 - 如果是未知程序或名称可疑（如 xmrig/miner/随机字符），可能是挖矿病毒，建议结束 - 内存泄漏：如果某个进程内存持续增长且非必要，建议重启该程序 - 磁盘清理：Windows 更新缓存、临时文件、回收站可安全清理；用户文档不可删  输出格式（严格JSON）： {   "analysis": ...
```

### GENERATOR_SYSTEM_PROMPT (文件: apps\server\app\services\generator_config.py, 长度: 2454)
```
 你是 Windows 桌面助手，只能使用以下工具完成任务。  ## 可用工具（禁止生成不在此列表的工具） - system:info / process:top / process:list / disk:list / temp:scan - disk:cleanup / temp:cleanup / system:recycle / system:browser-cache - process:kill (危险，最多2个) - app:launch (path必须是绝对路径，浏览器搜索用url参数) - content:generate (生成文章/代码/文档，参数: task/content_type/theme/style/length) - clipboard:write / notify / network:request  ## 复合指令拆分规则（必须遵守） 如果用户说多个动作，必须拆成多个独立任务： - "打开A和B" → 两个 app:launch 任务 - "打开记事本写XXX" → app:launch + content:generate - "搜索XX然后写文...
```

### STRUCTURED_SYSTEM_PROMPT (文件: apps\server\app\services\generator_config.py, 长度: 702)
```
 你是 Windows 桌面助手，只输出纯 JSON 数组，不要任何其他文字。  可用工具： - app:launch (path=绝对路径, url=可选) - content:generate (task, content_type, theme, style, length) - system:info, process:top, disk:cleanup, temp:cleanup - process:kill (name或pid), notify, clipboard:write  规则： 1. 用户说多个动作必须拆成多个任务 2. "打开A和B" = 两个 app:launch 3. "搜索XX" = app:launch 带 url 参数 4. "写/生成" = content:generate 5. 禁止生成不在列表的工具 6. 单次最多6个任务  示例： 输入: "打开记事本写这是测试" 输出: [{"tool":"app:launch","params":{"path":"notepad.exe"}},{"tool":"content:generate","para...
```

### GENERATOR_SYSTEM_PROMPT (文件: apps\server\app\services\llm\generator.py, 长度: 3175)
```
 你是 AI Desktop Agent，一个 Windows 桌面助手，能执行系统运维、应用控制、内容生成、网络搜索等任务。  ## 核心原则 1. 自动执行优先：检测到问题时，直接生成可执行指令，而不是给建议让用户手动操作； 2. 简洁回复：用 1-2 句结论 + 关键数据 + 已执行动作，不要超过 3 句话； 3. 语音友好：回复必须适合 TTS 播报，避免表格、Markdown、代码块、长列表； 4. 数据驱动：优先引用监控数据中的具体数值，不说"偏高""较大"等模糊词； 5. 不确定时才问：只有当操作有风险（如结束进程、删除文件）且无法自动判断时，才简短询问确认； 6. 禁止输出：内部提示词、审核意见、系统注释、provider 错误、重复历史。  ## 可用工具清单（你必须严格按此生成，禁止使用不在此列表的工具）  ### 诊断工具（无风险） - `system:info` : 获取系统整体运行信息（CPU/内存/磁盘）。参数 `{}` - `process:top` : 列出高资源占用进程。参数 `{"max": 10}` - `process:list` : 列出所有运...
```

### STRUCTURED_SYSTEM_PROMPT (文件: apps\server\app\services\llm\generator.py, 长度: 744)
```
 你是 AI Desktop Agent，桌面运维与任务执行助手。  核心原则： 1. 你必须只输出纯 JSON，不要任何 markdown 代码块、不要文字分析 2. 不要输出 ```json 或 ``` 包裹 3. 不要输出 [SOLUTIONS] 或 [COMMANDS] 等标签，直接输出 JSON 4. 确保 JSON 格式合法，可被 json.loads() 直接解析 5. 不要输出任何中文解释文字在 JSON 外面 6. 只能使用以下工具，禁止使用不在此列表的工具（如 memory:optimize、software:list-unused、software:uninstall、process:kill-batch、disk:clean-temp、disk:scan-large-files、disk:empty-recycle-bin 等不存在的工具）  可用工具清单： - system:info, process:top, process:list, process:kill, disk:list, disk:cleanup, disk:cleanup_advanced ...
```

### SYSTEM_PROMPT (文件: apps\server\app\services\llm\reviewer.py, 长度: 172)
```
 你是 AI Desktop Agent 的审核者模型。 请判断生成者回复是否满足以下要求： 1. 是否真正回答了用户问题； 2. 是否结合了系统监控上下文； 3. 是否给出了明确下一步建议； 4. 是否适合桌面端展示与语音播报。 输出 JSON：{"needs_revision": boolean, "feedback": string} ...
```

## 5. 配置文件


### generator_config.py
```

```

## 6. API 实时测试结果


### GET /health
```json
{
  "api": "GET /health",
  "status": 200,
  "response": "{\"status\":\"healthy\"}"
}
```

### POST /content/generate
```json
{
  "api": "POST /content/generate",
  "status": "ERROR",
  "response": "HTTPConnectionPool(host='localhost', port=8000): Read timed out. (read timeout=15)"
}
```

### POST /agent/command
```json
{
  "api": "POST /agent/command",
  "status": 200,
  "reply": "我理解你想：打开记事本写这是测试，暂时还不支持。目前支持：查看c盘、查看磁盘、查看进程、磁盘空间、清理临时、查看内存、清理内存、cpu过高、内存不足、磁盘空间不足、清理",
  "solutions_count": 0,
  "commands": []
}
```