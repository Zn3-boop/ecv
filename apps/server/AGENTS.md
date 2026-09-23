# AGENTS.md — Agent 约束边界文档

> 本文件是 Agent 的"岗位手册+红线清单"。所有判断以本文件为准，不在口头约定里。
> Agent 不允许自行修改本文件，修改必须由人类显式指令。

---

## 1. 仓库总览

本项目是一个桌面 Agent 系统，基于 LangGraph StateGraph 编排 28+ 节点，通过 Hook 插件架构增强能力。

核心链路：`用户提问 → 快脑过滤 → 意图识别(Hook) → 实体抽取 → 路由 → [RAG+Web并行检索(Hook) / 子Agent执行] → 工具执行(Hook安全拦截) → 验证门 → 记忆持久化 → 检查点(Hook)`

## 2. 可改 / 禁改范围

| 可改 | 禁改 |
|------|------|
| `app/services/hooks/plugins/` 下所有插件实现 | `app/services/graph/state.py` 中 `raw_query` 字段 |
| `config/hooks_plugins.yaml` 插件配置 | `AGENTS.md` 本文件 |
| `app/services/hooks/builtin/` 内置Hook实现 | `app/services/graph/graph.py` 节点拓扑（需人工审批） |
| 新增 Hook / Plugin | 证据分级 A/B 级 append-only 约束 |

## 3. Hook 插件架构（核心增强层）

### 四层生命周期

| 层 | 事件 | 用途 |
|---|---|---|
| Session | `session_start/end/compact/fork` | 会话级全局逻辑 |
| Agent | `before_agent_start`, `turn_start/end`, `context_assemble`, `query_rewrite`, `retrieval_start/end`, `fusion_complete` | Agent循环拦截 |
| Tool | `tool_call`, `before/after_tool_exec`, `validation_gate` | 工具安全拦截 |
| Provider | `before/after_provider_request` | LLM请求拦截 |

### 5 个内置 Hook

| Hook | 事件 | 知识点 | 作用 |
|---|---|---|---|
| `rag_web_parallel` | `before_agent_start` | RAG+Web并行检索 | 查询改写→并行检索→去重→融合→验证→Prompt |
| `tool_call_guard` | `tool_call` | H12/A7 | 4级风险评估，高风险阻断 |
| `context_manage` | `context_assemble` | A9 | 消息压缩，近期保留+远期占位符 |
| `execution_protocol` | `before_agent_start` | H3 | 标准执行协议(feature/bugfix/refactor/investigation) |
| `checkpoint` | `turn_end` | H4 | 检查点保存(目标/计划/产出物/剩余步骤) |

### 3 种配置方式（优先级低→高）

1. **YAML**: `config/hooks_plugins.yaml`
2. **环境变量**: `HOOKS_ENABLED`, `HOOK_REWRITER`, `HOOK_FUSION_STRATEGY`, `HOOK_RAG_WEIGHT`, `HOOK_WEB_WEIGHT`
3. **代码注册**: `registry.register_xxx("name", instance)`

### 8 类可插拔组件

| 类别 | 内置实现 | 配置键 |
|---|---|---|
| 查询改写 | `rule`, `llm` | `rewriter.type` |
| 意图识别 | `rule`, `llm` | `intent_recognizer.type` |
| 意图澄清 | `rule`, `llm` | `clarifier.type` |
| 检索器 | `rag`, `duckduckgo`, `tavily`, `serpapi`, `code_search` | `retrievers[].type` |
| 融合策略 | `simple_concat`, `weighted`, `rerank`, `source_priority` | `fusion.type` |
| 去重过滤 | `simhash`, `rule_filter`, `recency` | `dedup_filters[].type` |
| Prompt构造 | `default`, `concise`, `structured` | `prompt_builder.type` |
| 验证器 | `min_result`, `score_threshold` | `validators[].type` |

## 4. 节点清单

| 节点 | 职责 | Hook增强 |
|------|------|----------|
| `fast_brain` | 快脑过滤：空输入/垃圾字符/注入检测 | — |
| `detect_intent` | 意图识别+参数抽取+澄清判断 | ✅ Hook版 |
| `extract_entities` | 实体抽取+Query改写 | — |
| `route_llm` | 路由决策 | — |
| `clarification_node` | 低置信度澄清 | ✅ Hook版 |
| `rag_retrieve_node` | RAG+Web并行检索 | ✅ Hook版 |
| `tool_execute_node` | 工具执行 | ✅ Hook版(安全拦截) |
| `post_validate_gate` | 执行后校验 | — |
| `memory_persist_node` | 记忆持久化 | — |
| `turn_end_hook` | 检查点保存 | ✅ Hook版 |

## 5. 编码约束

1. **禁止原地修改 state**：所有节点必须 `return {key: value}` 返回全新字典
2. **RetryPolicy 仅瞬态错误重试**：security/business 错误直接进入 `error_fallback_node`
3. **D级推论禁止写入长期记忆**：仅会话 state 临时保存
4. **raw_query 永不覆盖**：改写产出 `standalone_query` / `retrieval_queries`
5. **高危动作 HITL 拦截**：`interrupt_before=["approval_node"]`
6. **OTel GenAI Trace**：只存参数 hash，原始参数 opt-in 独立存储
7. **Hook是增强层不是替代层**：Hook失败自动降级到原有节点逻辑

## 6. 高危操作清单

| 操作 | 风险级 | 处理 |
|------|--------|------|
| `shell_exec` 含 `rm -rf` / `DROP` | 不可逆 | 默认阻断 |
| `db_execute` 含 DDL/DROP | 高 | 需人工审批 |
| `shell_exec` 任意命令 | 高 | 需人工审批 |
| `file_write` | 中 | 记录审计日志 |
| `file_read` | 低 | 直接执行 |

## 7. 交付验收标准（Validation Gate）

Agent 不能口头宣称"完成"。交付必须附带以下证据：
- 代码变更文件列表
- Lint / 类型检查结果
- 新增/修改测试用例，测试执行日志
- 文档更新记录（如有）
- Hook执行日志（检索结果数/融合策略/验证通过/耗时）

Evaluator 将独立核验上述证据，作为完成判定依据。

## 8. 验证与自测规范

```bash
# 必须通过的检查
python -m pytest app/services/graph/tests/ -v
python -m pytest app/services/hooks/ -v
ruff check app/services/
```

## 9. 资料索引

| 文档 | 路径 |
|------|------|
| 插件配置 | `config/hooks_plugins.yaml` |
| Graph技术文档 | `app/services/graph/TECHNICAL_DOC.md` |
| RAG工程 | `app/services/rag/` |
| Hook插件 | `app/services/hooks/plugins/` |
| 安全配置 | `config/security.yaml` |

## 10. LLM 调用模式

| 环境变量 | 值 | 行为 |
|----------|-----|------|
| `LLM_MODE` | `mock`（默认） | 本地规则 mock，无需 API Key |
| `LLM_MODE` | `real` | 调用真实 LLM（需 `LLM_API_KEY`），失败自动降级 mock |
| `HOOKS_ENABLED` | `true`（默认） | Hook增强节点生效 |
| `HOOKS_ENABLED` | `false` | 所有Hook降级为原有节点 |

## 11. 证据分级

| 级别 | 含义 | 写入策略 |
|------|------|----------|
| A | 事实证据（用户原始输入、执行结果） | append-only |
| B | 素材（工具中间结果） | append-only |
| C | 辅助数据（治理扫描等） | 可读写 |
| D | 模型推论（intent/route） | **禁止写入长期 Fact** |

## 12. 信号状态机

```
open → processing → resolved
```