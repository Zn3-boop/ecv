# Next Step: Voice Loop, Conversation Memory, and Context Compression

## 本轮已落地

- `/chat/agent` 现在即使未显式传入 `conversation_id`，也会自动创建/复用默认会话，并持续写入 user / assistant 消息。
- `/voice/command` 现在会自动绑定默认语音会话，补充 `voice_turn` 原型消息，形成 `voice_turn -> user -> assistant` 的最小链路。
- `storage.py` 新增：
  - `ensure_conversation()`：确保桌面文本 / 语音入口始终有可用会话；
  - `create_voice_turn()`：把每轮语音转写以结构化 metadata 形式持久化。
- `context_builder.py` 的系统上下文摘要新增 `risk_level` 压缩字段，便于 Agent 在长提示中快速识别风险等级。

## 当前能力边界

### 1. Conversation 闭环
- 文本入口和语音入口都已经具备“无会话也能自动记忆”的基础能力。
- FastAPI 会在 prompt 中拼接最近 6 条历史消息，实现轻量记忆，而不依赖向量库。

### 2. Voice Turn 原型
- 当前 `voice_turn` 主要作为“语音原始轮次记录”，metadata 中保留：
  - `turn_id`
  - `session_id`
  - `source`
  - `locale`
  - `device`
  - `wake_word_enabled`
  - `interruption_enabled`
- 这为后续做“按 turn 回放”、“语音质检”、“多轮语音 session”打下基础。

### 3. 监控上下文压缩
- 目前采用规则压缩：CPU / 内存 / 磁盘 / Top 进程 / 告警 -> 单段摘要。
- `risk_level` 现在已经提前归一化为 `normal / warning / critical`，后续前后端都能直接复用。

## 建议下一步

### 前端
1. 将 `App.tsx` 拆分为：
   - `hooks/useVoiceAgent.ts`
   - `hooks/useDesktopMetrics.ts`
   - `components/ConversationPanel.tsx`
   - `components/ActionExecutorPanel.tsx`
2. 统一文本 / 语音提交函数，避免 chat 与 voice 两条入口的状态管理继续分叉。
3. 在会话消息列表中区分 `voice_turn` / `user` / `assistant`，展示语音轮次痕迹。

### 后端
1. 为 `/voice/command` 返回 `conversation_id`、`turn_id`，方便前端显式同步当前会话。
2. 为 automation 指令追加 `approval_policy` / `risk_level` / `require_confirm_reason` 字段，减少前端自行猜测。
3. 在 orchestrator 层引入更清晰的 agent stage 输出，如：`draft -> review -> final -> actions`。

### 面试/简历亮点表达
- “我没有走重 RAG + 向量数据库路线，而是用 Agentic RAG 思路做了生成者+审核者闭环，并结合桌面实时监控摘要做轻量记忆增强。”
- “语音入口不是演示级按钮，而是打通了 MediaRecorder -> STT -> Agent -> TTS -> conversation memory 的完整闭环。”
- “在桌面 Agent 中，我把系统监控、语音会话、自动执行审批三条链路统一进同一工作台，增强了产品化故事和工程完整性。”
