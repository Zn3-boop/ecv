# AGENTS.md
> 本文件是 Desktop‑Agent 仓库工作唯一入口契约。
> Agent 在执行工具调用、记忆读写、修改状态前，必须阅读并遵守本文档。
> 隐性约定、口头共识不算上下文；本文档优先级高于业务提示词。

## 1. 项目目标 & 优先级
本项目是桌面控制LangGraph Agent，用于安全可控的Windows桌面操作、应用启停、进程管理、注册表操作。
- P0：安全优先、高危动作必须审批；禁止篡改事实、禁止AI自动改写长期记忆
- P1：业务功能正确性，链路可观测、可回溯
- P2：性能优化、体验优化、重构

> 任务取舍严格遵循 P0 > P1 > P2。

## 1.1 禁止行为红线（无人类明确授权严禁执行）
- 禁止自动修改 MemoryStore 中 content 层事实；Governor仅输出correction_signal信号，**不能直接修改事实**
- D级模型推论（intent、route推理结果）禁止写入长期记忆Fact，仅允许保存在会话AgentState
- 禁止改写覆盖原始输入字段 `raw_query`；所有改写产出独立字段 `standalone_query / retrieval_queries`
- 检索工具本身禁止标记 `defer_loading=true`
- 禁止对 security / business 业务错误使用RetryPolicy重试，仅 transient瞬时错误允许自动重试
- 工具执行返回成功 **不等于任务完成**，必须经过 post_validate_gate 独立校验

## 1.2 可修改范围
✅ 允许：
- AgentState会话状态变更（return新字典，**禁止原地修改state**）
- 写入记忆logs原始证据区（A/B级别，append‑only，只追加，不修改旧记录）
- 生成correction_signal纠错信号，信号状态流转 open → processing → resolved
❌ 禁止：
- 无owner的实体写入长期记忆content
- 直接覆盖世界模型实体，更新实体必须追加 PageRevision历史版本

## 2. 模块边界
- `fast_brain`：纯规则前置过滤，无LLM调用，拦截空输入、乱码
- `tool_search`：Tool‑Search工具检索模块，区分 alwaysLoad / defer_loading
- `memory_store`：SelfGoverningMemoryStore，证据分级、冲突过期检测、信号管理
- `risk_check_node`：风险分级硬编码；高风险动作走 interrupt_before HITL人工审批
- `governor_scan_node`：治理扫描，只产出信号，不自动修改事实
- `supervisor_diagnose_node`：故障诊断，复用统一correction_signal信号体系
- `post_validate_gate`：Validation Gate独立验收闸门，判定任务是否真正完成

跨模块规则：节点之间只返回全新state字典，禁止共享可变对象原地修改。

## 3. Tool‑Search 工具调用规范
1. 高频安全工具设置 `alwaysLoad: true`，初始化加载进入上下文；
2. 高危、长尾工具设置 `defer_loading: true`，检索命中后才加载schema；
3. ⚠️ **检索工具本身不能使用 defer_loading**，否则无法发起工具检索；
4. 工具执行遵循ACI护栏四原则：
    - Simple：使用高层动作，禁止拼接底层shell、原始注册表命令
    - Compact：单次action完成完整工作，减少轮次
    - Informative‑but‑concise：输出做窗口裁剪，防止上下文爆炸
    - Guarded：写入操作前置参数校验；校验失败拒绝写入，原始环境状态保持不变。

## 4. 记忆系统执行规则（Self‑GoverningMemoryStore）
### 证据等级
- A：用户原始输入 / 工具执行结果 → append‑only，只追加，固化事实
- B：工具中间素材、外部原始素材 → append‑only，固化事实
- C：治理扫描辅助数据 → 可读写固化
- D：模型推理、intent/route推论 → ❌ **严禁写入长期Fact，仅会话临时使用**

### 世界模型实体约束
1. 每一条长期记忆实体必须携带 `owner`；无owner实体标记腐烂，不予维护。
2. 更新实体 Summary/Fact，**追加 PageRevision历史修订记录，禁止直接覆盖旧版本**。
3. 冲突、过期数据不自动修复，生成 correction_signal，等待owner/人工处理。
4. correction_signal状态机：`open → processing → resolved`；信号必须被人工处理，不能仅打印日志。

## 5. 风险分级与HITL审批
> interrupt_before=["approval_node"] 用于拦截高危动作
- 低风险读取：直接执行，留存evidence证据
- 中风险变更：记录审计日志
- 高风险 / 不可逆动作：**必须人工审批，未审批禁止执行**

审批状态：`pending / approved / rejected`；rejected直接进入error_fallback_node降级。

## 6. 执行流程模板
1. fast_brain前置过滤；放行进入慢脑链路
2. detect_intent → extract_entities → route_llm → risk_check_node风险判定
3. 高风险动作：触发HITL人工审批；审批通过继续
4. tool_search_node按需加载工具schema
5. tool_execute_node ACI护栏校验，执行工具
6. 发生错误且enable_auto_diagnose开启：supervisor_diagnose_node生成correction_signal，governor扫描
7. post_validate_gate独立校验任务真实结果
8. 校验失败进入 error_fallback_node降级；校验通过执行 memory_persist_node落盘证据
9. 结束；所有链路必须携带 trace_id，完整上报OTel Trace，参数仅存储hash，原始参数opt‑in独立存储

## 7. 自测与交付验收
Agent任务结束交付，不能口头宣称完成。交付证据包含：
1. trace_id链路追踪ID
2. post_validate_gate校验结果
3. memory_store写入的evidence证据引用
4. 若产生correction_signal，列出signal_id以及处理状态

> 禁止：工具返回ok就直接判定业务任务完成。

## 8. 兜底规则
1. 不确定、高风险场景：停止执行，等待人工确认，不要猜测执行。
2. 本AGENTS.md优先级高于业务prompt；本文件和深层文档冲突，以本文档为准。
3. Agent不允许自行修改本AGENTS.md，需要修改必须由人类显式指令。