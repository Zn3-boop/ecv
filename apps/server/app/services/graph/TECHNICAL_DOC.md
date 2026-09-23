# Desktop Agent LangGraph 技术文档

> 版本：v1.0 | 更新：2026-09-18 | pytest：76/76 passed

---

## 1. 项目概述

基于 LangGraph 0.2.x 构建的桌面控制 Agent 有向状态图系统。实现快慢脑前置过滤、Governor 治理循环、Supervisor 诊断 Agent、Tool-Search 工具延迟加载、HITL 人工审批、可观测三路采集等完整工程化能力。

### 1.1 技术栈

| 层 | 技术 |
|---|---|
| 框架 | LangGraph 0.2.x + FastAPI |
| LLM | OpenAI GPT-4o / 可替换 |
| 存储 | Checkpointer (MemorySaver/PostgresSaver) + MemoryStore (文件系统) |
| 可观测 | OTel GenAI Trace + LangFuse + 自建 Metrics |
| 容器 | Docker + docker-compose |

### 1.2 核心设计原则

1. **节点返回新字典**：禁止原地修改 state，全部 `return {key: value}` 更新
2. **证据分级**：A 级用户原话固化为事实，D 级模型推论不写入长期记忆
3. **不以工具返回判定任务完成**：独立 Validation Gate 校验真实业务结果
4. **最小侵入**：新增模块兼容原有业务链路，不破坏历史接口
5. **ACI 接口优先原则**：工具接口为 Agent 设计，不是照搬人类 GUI 接口；遵循 Simple / Compact / Informative but concise / Guarded 护栏，写入前校验拦截错误扩散
6. **原始输入不可覆盖原则**：永久保留 `raw_query` 原始用户输入；所有改写、实体抽取生成独立字段，禁止改写覆盖原始请求
7. **评测与生产分离**：生产使用 OTel GenAI Trace；开发调试使用 LangFuse 双埋点；Agent 质量评估使用 LLM-as-Judge 做离线评测，形成 bad-case 回流数据集

---

## 2. 架构总览

### 2.1 状态图流转

```
用户输入
  ↓
fast_brain【快脑，纯规则无LLM】
  ├─拦截 → END（空输入、空格、乱码）
  └─放行 → detect_intent【慢脑LLM链路】
      ↓
  extract_entities → route_llm → risk_check
      ↓
  ├─高风险 → interrupt_before HITL人工审批
  └─普通 → 继续
      ↓
  tool_search_node【Tool-Search：defer-loading按需加载schema】
      ↓
  tool_execute_node【ACI-Guarded护栏 + 工具执行】
      ↓
  [有错误 && enable_auto_diagnose]
      → supervisor_diagnose_node → governor_scan_node → END
  [无错误/未开启]
      → post_validate_gate
          ├─校验失败 → error_fallback_node（降级响应）→ memory_persist_node → END
          └─校验通过 → memory_persist_node → END
```

### 2.2 节点清单

| 节点 | 类型 | 说明 |
|---|---|---|
| fast_brain | Checker | 快脑前置过滤，零 token 消耗 |
| detect_intent | Node | 意图识别（LLM） |
| extract_entities | Node | 实体抽取 |
| route_llm | Node | LLM 路由决策 |
| clarification_node | Node | 低置信度意图澄清 |
| risk_check_node | Checker | 风险分级（非 LLM 硬编码） |
| approval_node | Node | HITL 人工审批（interrupt_before） |
| app_launch_agent_node | Node | Agent 执行 |
| tool_search_node | Node | Tool-Search 工具检索 + 按需加载 |
| tool_execute_node | Node | Guard 前置护栏 + 工具执行 |
| post_validate_gate | Checker | Validation Gate 后校验 |
| governor_scan_node | Checker | Governor 治理循环 |
| supervisor_diagnose_node | Checker | Supervisor 诊断 Agent |
| error_fallback_node | Node | 降级 Fallback |
| memory_persist_node | Node | Checkpointer 快照 + Store 证据落盘 |

### 2.3 条件边路由

| 源节点 | 路由函数 | 目标 |
|---|---|---|
| fast_brain | route_after_fast_brain | detect_intent / END |
| tool_execute_node | route_after_tool_exec | supervisor_diagnose_node / post_validate_gate |
| supervisor_diagnose_node | route_after_supervisor | governor_scan_node / END |
| governor_scan_node | route_after_governor | END |

---

## 3. 模块详细设计

### 3.1 快慢脑架构

**快脑 fast_brain_node**：纯规则前置过滤，不调用 LLM。

| 规则 | 判定 | 动作 |
|---|---|---|
| 空字符串 | 拦截 | need_slow_brain=False |
| 全空格/全标点 | 拦截 | need_slow_brain=False |
| 乱码比例 > 60% | 拦截 | need_slow_brain=False |
| 正常输入 | 放行 | need_slow_brain=True |

**慢脑**：完整 LLM 链路（意图识别 → 实体抽取 → 路由 → 风险检查 → 工具执行 → 校验）。

> **快脑定位说明**：快脑是低成本准入层，不做深度推理；复杂语义过滤属于进阶迭代方向，当前版本纯规则实现符合现状，迭代表保留小模型语义过滤路线。

### 3.2 Governor 治理循环

**职责**：
1. 扫描记忆仓库，识别冲突实体、过期证据，生成 `correction_signal` 纠错信号。
2. 信号写入 MemoryStore `signals` 命名空间，具备状态机：`open → processing → resolved`，记录 `owner` 责任人、`entity_key`、证据等级。
3. **信号只上报，不自动修改事实；无 Owner 的实体标记为腐烂，不自动修改记忆。**

**两种触发模式**：

| 模式 | 触发方式 | 扫描范围 | 阻塞 | 信号行为 |
|---|---|---|---|---|
| light | 记忆写入事件触发 | 当前用户 namespace | 不阻塞主流程 | 生成 signal，状态 open，等待 owner 处理 |
| full | 手动/外部 cron 调用 | 指定用户全量 | 独立执行 | 批量生成多条 signal |

**冲突检测**：同一 namespace 内相同实体 key 出现 ≥2 次视为冲突。
**过期检测**：`expire_at` 字段与当前时间比较。
**纠错信号**：写入 `signals` 命名空间，状态机 `open → processing → resolved`，每条信号携带 `owner`、`entity_key`、`evidence_level`。

**指标**：
- `governor_light_scan_total`
- `governor_full_scan_total`
- `governor_signal_generated_total`
- `signal_status_open_total`
- `signal_status_resolved_total`

**限制**：
- 未实现 Celery 后台定时；支持事件触发 + 手动 full_scan；生产可对接外部 cron。
- **Governor 禁止自动修改 content 事实**，仅输出信号交给 Owner/人工处理，避免 AI 自动篡改事实。

### 3.3 Supervisor 诊断 Agent

**职责**：链路执行失败时，读取 trace 信息，分析意图识别/路由失败，生成 correction_signal。

> Supervisor 产出的 correction_signal 复用 Governor 信号存储体系，统一 `signals` 命名空间，不单独搞一套信号数据结构。

**触发条件**：`enable_auto_diagnose=True` 且 `last_error` 非空 且 `diagnose_trace_id` 非空。

**诊断规则**（当前版本）：

| 错误关键词 | 信号类型 |
|---|---|
| intent / route / confidence | pollution |
| 其他 | 不生成信号 |

**指标**：`supervisor_diagnose_signal_total`

**限制**：当前规则式诊断；进阶可替换为 LLM 读取完整 trace 做深度根因分析。

### 3.4 Tool-Search 工具延迟加载

**职责**：解决工具数量膨胀时大量 schema 占满 LLM 上下文窗口、工具选错问题。

**工具分类**：

| 标记 | 含义 | 加载时机 |
|---|---|---|
| alwaysLoad=True | 高频常驻工具 | 初始化直接加载 |
| defer_loading=True | 长尾/高危工具 | 检索命中后按需加载 |

**流程**：输入检索 query → 关键词匹配 → 命中后 load_tool_schema → schema 加入 LLM 上下文。

**Demo 工具集**：

| 工具 | 标记 | 说明 |
|---|---|---|
| launch_app | alwaysLoad | 启动桌面应用 |
| query_process | alwaysLoad | 查询系统进程 |
| kill_process | alwaysLoad | 结束进程 |
| edit_registry | defer_loading | 编辑注册表（高危） |
| export_system_log | defer_loading | 导出系统日志（大输出） |
| run_script | defer_loading | 运行脚本（高危） |

**指标**：`tool_search_invoked_total`

**限制**：当前关键词匹配检索；进阶可替换 embedding 向量语义检索。

**风险提示**：
- Tool-Search 检索召回不准会导致需要的高危工具无法加载，造成功能缺失；高频工具必须设置 `alwaysLoad=True`。
- 检索工具本身不能设置 `defer_loading=True`，否则模型无法发起检索。

### 3.5 记忆体系

**双层存储**：

| 存储 | 用途 | 生命周期 |
|---|---|---|
| Checkpointer | 会话状态快照 | 单次会话 |
| MemoryStore | 跨会话长期记忆 | 永久 |

**Owner 责任域**：每个实体/记忆条目必须绑定 `owner`；**无 Owner 实体标记为腐烂，不自动维护**。

**世界模型实体三层结构**：

| 层 | 含义 | 说明 |
|---|---|---|
| Summary | 实体当前结论 | 快速读取 |
| Fact | 带 evidence 证据来源记录 | 支撑 Summary 的证据链 |
| PageRevision | 历史变更版本 | 更新实体时追加修订记录，**禁止直接覆盖旧版本** |

**证据分级**：

| 级别 | 含义 | 是否固化 | 写入规则 |
|---|---|---|---|
| A | 用户原始输入 + 执行结果 | ✅ 固化为事实 | append-only，只追加不修改不删除 |
| B | 工具执行中间素材 | ✅ 固化 | append-only，只追加不修改不删除 |
| C | 治理扫描等辅助数据 | ✅ 固化 | 正常读写 |
| D | 模型推论（intent/route） | ❌ 不固化 | **禁止写入长期记忆 Fact**，仅临时保存在会话 state |

**SelfGoverningMemoryStore**：在 MemoryStore 基础上增加冲突检测、过期检测、correction_signal 管理。

> 建议在 `memory_store.py` 增加字段：`owner`、`page_revision[]`、`expire_at`。

### 3.6 Harness 约束工程

| 层 | 实现 |
|---|---|
| 风险分级 | risk_check_node，非 LLM 硬编码规则 |
| HITL 审批 | interrupt_before=["approval_node"]，外部 update_state 写入审批结果 |
| ACI 护栏 | 工具执行前参数校验，拦截命令注入；遵循 4 条 ACI 设计原则（见下） |
| Validation Gate | 独立校验进程存活，不以工具返回值判定任务完成 |
| RetryPolicy | 仅对 transient 瞬时错误重试，security/business 错误直接降级 |

**ACI 护栏 4 条设计原则**：
1. **Simple 简单**：提供高层动作，避免 Agent 拼接底层 shell/注册表原始命令。
2. **Compact 紧凑**：一次 action 完成一件完整工作，减少来回轮次。
3. **Informative but concise**：工具返回结果做窗口裁剪，返回充分但简洁的信息，防止上下文爆炸。
4. **Guarded 护栏**：写入操作前置校验；格式、语法、权限校验失败直接拒绝写入，原始状态不被修改，阻止错误扩散。

### 3.7 可观测

| 维度 | 实现 |
|---|---|
| Trace | OTel GenAI Span，trace_id 全链路透传，参数只存 hash |
| Metrics | 自建计数器 + 直方图，/metrics 端点暴露 |
| Logs | 结构化日志，trace_id 关联 |

**双埋点落地模式（工业互补架构，二者不可互相替代）**：

1. **生产环境**：OTel GenAI Trace，遵循五层标准 Span，trace_id 全链路透传；trace 中只存参数 hash；原始参数通过 opt-in 独立存储，用于大盘告警、性能瓶颈定位。
2. **开发/测试环境**：LangFuse 本地 Docker 自建，做 Agent 调试、可视化、数据集批量评估。
3. **联动**：线上 OTel 抓到异常 trace_id，使用 `session_id / trace_id` 到 LangFuse 拉取完整会话样本复盘。

**两种落地模式**：

| 模式 | 说明 |
|---|---|
| 模式 A（简历 Demo） | 代码实现完整 OTel 埋点逻辑，后端输出 JSON/Console，不部署完整 OTel Collector 服务 |
| 模式 B（完整工程） | 本地部署 Arize-Phoenix 作为 OTel 后端 + 本地 LangFuse，实现完整双埋点闭环 |

---

## 4. 状态字段定义 (AgentState)

```python
class AgentState(TypedDict, total=False):
    # 基础
    raw_query: str                    # 用户原始输入，永远不被改写（审计兜底）
    standalone_query: str             # 消解指代、补全省略后的独立可理解查询
    retrieval_queries: list[str]      # 多条用于检索的改写 query
    session_id: str
    trace_id: str
    user_id: str

    # 快慢脑
    fast_brain_decision: str
    need_slow_brain: bool
    fast_brain_msg: str

    # 意图/路由
    intent: str
    intent_confidence: float
    route_target: str
    route_confidence: float
    needs_clarification: bool
    clarification_message: str

    # 风险/审批
    risk_level: str
    approval_required: bool
    approval_status: str

    # 工具执行
    tool_name: str
    tool_args: dict
    tool_result: dict
    last_error: str
    error_type: str
    retry_count: int

    # Governor
    governor_trigger: str          # "light" / "full" / ""
    governor_scan_result: dict

    # Supervisor
    enable_auto_diagnose: bool
    diagnose_trigger: bool
    diagnose_trace_id: str
    correction_signal_id: str
    correction_signal_status: str    # open / processing / resolved

    # Tool-Search
    tool_search_query: str
    tool_search_hit_list: list[str]
    tool_loaded_schema: list[dict]

    # 记忆
    evidence: dict
```

---

## 5. HTTP 接口清单

### 5.1 核心业务接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /desktop/graph/invoke | LangGraph 状态图执行 |
| POST | /desktop/graph/approval | HITL 人工审批 |
| GET | /desktop/graph/state | 查询 checkpoint 状态快照 |
| GET | /desktop/graph/history | 查询 checkpoint 历史记录 |
| GET | /desktop/graph/checkpoints | 获取历史 checkpoint 快照列表（Time Travel） |
| POST | /desktop/graph/fork | 回溯到指定 checkpoint_id，fork 出新分支（Time Travel） |

> **Time Travel 说明**：底层 Checkpointer 已支持时间旅行，业务层暴露 API 可用于调试失败任务、A/B 分支实验。

### 5.2 Governor 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /desktop/governor/full-scan | 手动触发全量扫描 |
| GET | /desktop/governor/signals | 查询 correction_signal 列表 |
| PATCH | /desktop/governor/signals/{signal_id} | 更新信号状态（补齐信号闭环） |

**POST /desktop/governor/full-scan**

请求：
```json
{ "user_id": "u1" }
```

响应：
```json
{
  "success": true,
  "conflict": [{"entity_key": "evidence_A", "count": 3}],
  "expired": [{"key": "temp_cert", "expire_at": "2025-01-01T00:00:00"}],
  "signal_generated": 2
}
```

**PATCH /desktop/governor/signals/{signal_id}**

请求：
```json
{
  "status": "resolved",
  "owner": "human-admin",
  "comment": "人工处理完成"
}
```

响应：
```json
{
  "success": true,
  "signal_id": "sig_a1b2c3d4e5f6",
  "status": "resolved"
}
```

### 5.3 Supervisor 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /desktop/supervisor/diagnose | 手动触发诊断 |

**POST /desktop/supervisor/diagnose**

请求：
```json
{
  "user_id": "u1",
  "trace_id": "trace-001",
  "last_error": "intent parse failed"
}
```

响应：
```json
{
  "success": true,
  "correction_signal_id": "sig_a1b2c3d4e5f6"
}
```

### 5.4 Tool-Search 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /desktop/tool-search/query | 工具检索 |
| POST | /desktop/tool-search/load | 手动加载工具 schema |
| GET | /desktop/tool-search/loaded | 查询已加载 schema |
| GET | /desktop/tool-search/all | 查询全部已注册工具 |

**POST /desktop/tool-search/query**

请求：
```json
{ "query": "registry", "top_k": 3 }
```

响应：
```json
{
  "success": true,
  "hit_list": ["edit_registry"],
  "loaded_schema": [
    {"name": "launch_app", "description": "启动桌面应用", "input_schema": {...}},
    {"name": "edit_registry", "description": "编辑Windows注册表，高危操作", "input_schema": {...}}
  ]
}
```

### 5.5 可观测接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /metrics | 全套计数器 + 直方图汇总 |

---

## 6. 指标清单

| 指标名 | 类型 | 模块 |
|---|---|---|
| fast_brain_filter_total | counter | 快脑 |
| fast_brain_pass_total | counter | 快脑 |
| governor_light_scan_total | counter | Governor |
| governor_full_scan_total | counter | Governor |
| governor_signal_generated_total | counter | Governor |
| supervisor_diagnose_signal_total | counter | Supervisor |
| tool_search_invoked_total | counter | Tool-Search |
| graph_recursion_error_total | counter | 全局 |
| graph_invoke_error_total | counter | 全局 |
| graph_approval_interrupt_total | counter | HITL |
| graph_approval_approve_total | counter | HITL |
| graph_approval_reject_total | counter | HITL |
| graph_node_duration_seconds | histogram | 全节点 |
| signal_status_open_total | gauge | Governor 信号统计 |
| signal_status_resolved_total | gauge | Governor 信号统计 |
| fallback_triggered_total | counter | error_fallback_node 降级统计 |

---

## 7. 上线前 Checklist

```
[ ] GRAPH_ENV=prod，生产使用 PostgresSaver，禁止 MemorySaver
[ ] thread_id 格式 = {user_id}_{session_id}，防止多用户会话碰撞
[ ] recursion_limit=15 配置；捕获 GraphRecursionError
[ ] 所有节点禁止原地修改 state，全部 return 新字典
[ ] error_type 区分 transient / security / business；仅瞬时错误启用 RetryPolicy
[ ] HITL 高危动作：interrupt_before=["approval_node"]
[ ] OTel Trace：span 只存参数 hash；原始参数 opt-in 独立存储
[ ] 证据分级：A级用户原话固化，D级模型推论不写入长期 Fact
[ ] metrics 埋点全部生效
[ ] Validation Gate 独立校验，不把工具返回 ok 当做任务完成标志
[ ] pytest 全部 70 用例通过
[ ] Tool-Search：高频 alwaysLoad，长尾 defer_loading
[ ] Governor：生产不依赖自动 full_scan，由外部 cron 调用接口触发
[ ] Supervisor：生产默认 enable_auto_diagnose=False
[ ] .env 环境变量校验：DATABASE_URI / REDIS_URI / OTEL 端点
[ ] 记忆实体必须携带 owner；禁止无 Owner 的实体写入长期记忆
[ ] correction_signal 具备完整状态机 open→processing→resolved，信号可人工更新状态
[ ] raw_query 字段全程不可覆盖；standalone_query、retrieval_queries 为改写产出字段
[ ] ACI 护栏：工具执行遵循 Simple/Compact/Informative-but-concise/Guarded 原则；写入操作前置校验，错误拒绝写入，原始状态不变
[ ] 双埋点策略确认：生产 OTel GenAI Trace；开发使用 LangFuse，trace_id 作为两者关联键
[ ] 世界模型实体更新必须追加 PageRevision 历史版本，禁止直接覆盖旧事实
[ ] 降级链路 error_fallback_node 可正常触发，埋点 fallback_triggered_total 指标
[ ] 确认 D 级模型推论（intent/route）不会写入长期 MemoryStore 事实
```

---

## 8. 测试覆盖

| 测试类 | 用例数 | 覆盖范围 |
|---|---|---|
| TestPydanticModels | 3 | 状态模型校验 |
| TestGuard | 4 | ACI 护栏：命令注入、路径穿越 |
| TestRiskChecker | 4 | 风险分级 |
| TestValidationGate | 3 | 后校验闸门 |
| TestIntent | 2 | 意图识别 |
| TestClarification | 1 | 低置信度澄清 |
| TestTraceHash | 2 | 参数 hash 摘要 |
| TestIsTransientError | 3 | 错误分类 |
| TestBuildInvokeConfig | 2 | 配置构建 |
| TestCheckpointerFactory | 2 | 存储工厂 |
| TestMemoryStore | 3 | 记忆读写 |
| TestMetrics | 2 | 指标计数 |
| TestFastBrain | 6 | 快脑过滤 |
| TestGovernor | 3 | Governor 轻量/全量/无触发 |
| TestSupervisor | 4 | Supervisor 自动/手动/关闭/非意图错误 |
| TestToolSearch | 6 | 检索/初始化/加载/重复加载/节点/空查询 |
| TestSelfGoverningMemoryStore | 3 | 写入扫描/信号生成/全量扫描 |
| TestSignalStateMachine | 5 | 信号初始状态/open→processing/open→resolved/非法流转/携带entity_key |
| TestOwnerResponsibility | 2 | 有owner写入/无owner警告 |
| TestPageRevision | 1 | 覆盖旧版本时追加PageRevision |
| TestQueryRewriteFields | 3 | raw_query/standalone_query/retrieval_queries + user_id + signal_status |
| TestFallbackMetrics | 1 | error_fallback_node埋点fallback_triggered_total |
| TestToolSearchDeferLoadingGuard | 1 | 检索工具禁止defer_loading |
| **合计** | **70** | |

**Agent 行为级评测（与 pytest 互补，不可互相替代）**：

| 测试类 | 用例数 | 覆盖范围 |
|---|---|---|
| LangSmith/LangFuse Evaluate | 若干 | Agent 端到端行为评测；LLM-as-Judge 评测；bad-case 回流到回归数据集 |

> 70 个 pytest 为单元层，evaluate 负责 Agent 业务行为评测，二者互补。

---

## 9. 文件结构

```
app/services/graph/
├── state.py              # AgentState 状态定义
├── checkers.py           # fast_brain / governor_scan / supervisor_diagnose
├── nodes.py              # 全部业务节点 + tool_search_node
├── graph.py              # LangGraph 图编排 + 条件边
├── memory_store.py       # MemoryStore + SelfGoverningMemoryStore
├── tool_search.py        # ToolSearch + ToolDef
├── metrics.py            # 计数器 + 直方图
├── demo.py               # 交互式 Demo
├── FLOWCHART.md          # Mermaid 流程图
├── AGENTS.md             # 架构说明 + 面试话术
└── tests/
    └── test_graph.py     # 70 pytest 用例

app/api/
├── desktop.py            # /desktop/* 全套接口（含 Governor/Supervisor/Tool-Search）
└── agent.py              # /agent/* 历史接口

app/main.py               # FastAPI 入口 + lifespan + 全局异常处理
```

---

## 10. 后续迭代方向

| 模块 | 当前 | 进阶 |
|---|---|---|
| Governor | 事件触发 + 手动 full_scan | Celery 异步定时任务 |
| Supervisor | 规则式诊断 | LLM 读取完整 trace span 做深度根因分析 |
| Tool-Search | 关键词匹配检索 | embedding 向量语义检索 |
| 快慢脑 | 规则版快脑 | 小模型轻量语义过滤 |
| 记忆仓库 | 文件系统 | 向量数据库 + Owner 责任域 |
| 可观测 | ConsoleExporter | 双埋点 OTel+LangFuse 完整落地；trace_id 打通两套系统 |
| LLM 缓存 | 未实现 | 四层缓存（提示词缓存、KV 前缀缓存、结果缓存、语义缓存），上线门禁公式 Quality≥Qmin ∧ Safety=pass ∧ Latency≤Lmax ∧ CostReduction>ε |
| 评测体系 | pytest 单元 | LLM-as-Judge 评测闭环；Rubric 结构化评判标尺；Annotation Queue；bad-case 自动回流回归数据集 |
| Query 改写 | 基础 clarification_node | 完整 Query 改写链路，raw_query/standalone_query/retrieval_queries 三字段完整实现 |
| Fallback 降级 | 存在节点 | 完善降级链路，多等级降级策略，指标埋点 |

---

## 11. Known-Risk 已知风险

> 以下为工程实践中已识别的高风险点，交付开发时必须逐条确认。

1. ❗ **correction_signal 只生成不消费是重大工程风险**：信号必须有状态机（open → processing → resolved），支持人工/Owner 处理，不能只写日志。
2. ❗ **禁止改写覆盖 `raw_query` 原始用户输入**：所有意图改写、query 改写产出独立字段（standalone_query / retrieval_queries），原始输入永远保留。
3. ❗ **Tool-Search 检索工具不能设置 `defer_loading=True`**：否则模型无法发起工具检索，导致功能缺失。
4. ❗ **D 级模型推论（intent、route 结果）只能存在会话 state**：严禁写入 MemoryStore 长期事实，防止模型推论污染知识库。
5. ❗ **Governor 禁止自动修改世界模型 Fact**：只能产出信号，交给 Owner/人工处理，防止 AI 自动篡改事实。
6. ❗ **工具执行成功不等于任务完成**：必须经过独立 Validation Gate 校验真实业务结果。
7. ❗ **Trace 链路只存参数 hash**：完整参数必须 opt-in 独立存储，避免数据爆炸、隐私合规风险。