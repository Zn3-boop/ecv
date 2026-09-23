# Desktop Agent 上线部署 Checklist

> 版本：v1.0 | 更新日期：2026-09-18
> 覆盖范围：LangGraph 状态图编排 + 安全护栏 + 可观测 + HITL 审批 + 记忆体系

---

## 一、环境与配置

### 1.1 环境变量

| 变量 | 必填 | 生产值 | 说明 |
|------|------|--------|------|
| `GRAPH_ENV` | ✅ | `prod` | 禁止 `dev`，`dev` 使用 MemorySaver 重启丢会话 |
| `GRAPH_POSTGRES_CONN` | ✅ | `postgresql://user:pass@host:5432/db` | 生产 PostgresSaver 连接串 |
| `GRAPH_CHECKPOINT_DB` | test | `./graph_checkpoint.db` | 仅 test 环境使用 |
| `GRAPH_MEMORY_STORE_DIR` | ✅ | `/data/memory_store` | 长期记忆 Store 目录 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | ✅ | `http://otel-collector:4318` | OTel Collector 地址 |
| `OTEL_SERVICE_NAME` | ✅ | `ecv-desktop-agent` | 服务名，用于 trace/span |
| `LANGFUSE_PUBLIC_KEY` | 可选 | — | LangFuse 可观测平台 |
| `LANGFUSE_SECRET_KEY` | 可选 | — | LangFuse 密钥 |
| `LANGFUSE_HOST` | 可选 | `https://cloud.langfuse.com` | LangFuse 地址 |
| `POSTGRES_DB` | ✅ | `ecv_graph` | 数据库名 |
| `POSTGRES_USER` | ✅ | — | 数据库用户 |
| `POSTGRES_PASSWORD` | ✅ | — | 数据库密码（强密码） |
| `REDIS_PASSWORD` | ✅ | — | Redis 密码 |
| `MAX_CONCURRENT_PER_USER` | ✅ | `5` | 单用户并发任务上限 |

### 1.2 依赖版本锁定

```
langgraph>=0.2.35,<0.3.0
langgraph-checkpoint>=2.0
pydantic>=2.10
```

- [ ] `requirements.txt` 版本范围已锁定，禁止模糊 `*` 版本
- [ ] `pip install -r requirements.txt` 在干净虚拟环境可成功安装
- [ ] `langgraph` 版本 >= 0.2.35，`MemorySaver` 从 `langgraph.checkpoint.memory` 导入

---

## 二、基础设施

### 2.1 PostgreSQL

- [ ] PostgreSQL 16+ 实例已部署
- [ ] `init_postgres.sql` 已执行：checkpoints / checkpoint_writes / checkpoint_blobs / memory_store 表已创建
- [ ] 连接池配置合理（建议 `pool_size=10, max_overflow=20`）
- [ ] 定期备份策略已配置
- [ ] `GRAPH_POSTGRES_CONN` 连接串可连通

### 2.2 Redis

- [ ] Redis 7+ 实例已部署
- [ ] 密码认证已开启（`requirepass`）
- [ ] 最大内存限制已设置（`maxmemory` + `allkeys-lru`）
- [ ] `REDIS_PASSWORD` 与配置一致

### 2.3 OTel Collector

- [ ] `otel-collector-config.yaml` 已部署
- [ ] 三路采集 pipeline 已配置：traces / metrics / logs
- [ ] 4317 (gRPC) + 4318 (HTTP) 端口可达
- [ ] 后端 exporter 已对接（Jaeger / Tempo / Prometheus / Loki 等）

---

## 三、安全检查

### 3.1 命令注入防护

- [ ] `_guard_pre_check` 拦截 shell 元字符：`; & | $ \` > <`
- [ ] Pydantic `AppLaunchInput` 校验 path 格式，拒绝非法路径
- [ ] Guard 拦截设置 `error_type=security`，禁止重试
- [ ] 测试用例 `test_shell_injection_*` 全部通过

### 3.2 风险分级

- [ ] 高风险路径（`.bat` `.ps1` `.cmd` `system32`）标记 `approval_required=True`
- [ ] `interrupt_before=["approval_node"]` 编译配置生效
- [ ] HITL 审批流程完整：interrupt → update_state → ainvoke(None, config)
- [ ] 拒绝操作走 `error_fallback_node`，不执行工具

### 3.3 Validation Gate

- [ ] 工具执行后独立校验进程存活状态
- [ ] 不以工具返回 `ok` 判定任务完成
- [ ] 假 PID / 僵尸进程检测逻辑生效

### 3.4 State 安全

- [ ] 所有节点函数返回新字典，**禁止原地修改 state**
- [ ] checkpoint 快照正确记录每次状态变更
- [ ] `trace_id` 全链路唯一，节点内部禁止重新生成

---

## 四、LangGraph 配置

### 4.1 Checkpointer

- [ ] 生产环境 `GRAPH_ENV=prod`，使用 PostgresSaver
- [ ] **禁止生产使用 MemorySaver**（重启丢全部会话）
- [ ] `get_checkpointer()` 工厂函数按环境正确切换
- [ ] 降级链路：PostgresSaver → SqliteSaver → MemorySaver（ImportError 时）

### 4.2 Recursion 保护

- [ ] `DEFAULT_RECURSION_LIMIT=15` 已配置
- [ ] `build_invoke_config()` 自动注入 `recursion_limit`
- [ ] 全局 `GraphRecursionError` 异常处理器已注册（HTTP 508）
- [ ] 异常返回友好业务错误，不暴露堆栈

### 4.3 Thread ID

- [ ] `thread_id` 格式：`{user_id}_{session_id}`（复合键）
- [ ] 不同用户的 thread_id 不会碰撞
- [ ] 同一用户不同会话的 thread_id 不会碰撞

### 4.4 RetryPolicy

- [ ] `error_type=transient`（超时、连接异常）→ 允许重试，最多 2 次
- [ ] `error_type=security`（命令注入）→ 禁止重试，直接 fallback
- [ ] `error_type=business`（参数非法、校验失败）→ 禁止重试，直接 fallback
- [ ] `_is_transient_error()` 关键词列表完整（含 etimedout 小写匹配）

---

## 五、HITL 人工审批

- [ ] `interrupt_before=["approval_node"]` 编译参数已设置
- [ ] 高风险操作触发 interrupt，返回 `approval_status="pending"`
- [ ] `/desktop/graph/approval` 和 `/agent/graph/approval` 接口可用
- [ ] `approve` → `update_state(approval_status=ok)` → `ainvoke(None, config)` 恢复
- [ ] `reject` → `update_state(approval_status=reject)` → 走 error_fallback
- [ ] `ainvoke(None, config)` 不传新 input，复用已有 checkpoint
- [ ] 审批 metrics 计数器正常：`graph_approval_approve_total` / `graph_approval_reject_total`

---

## 六、可观测

### 6.1 OTel GenAI Trace

- [ ] span 属性使用 `gen_ai.*` 标准前缀，不自定义随意 key
- [ ] span 只存参数 hash 摘要，**禁止存储完整 path / url**
- [ ] 原始参数 opt-in 独立事件存储，需显式开启
- [ ] `gen_ai.usage` / `gen_ai.tool.call.id` / `finish_reasons` 标签正确

### 6.2 Metrics

- [ ] `/metrics` 端点可访问，返回 counters + histograms 摘要
- [ ] 关键指标已埋点：
  - `graph_node_duration_seconds` — 节点耗时直方图
  - `graph_node_error_total` — 节点错误计数（按 type 分类）
  - `graph_security_blocked_total` — 安全拦截计数（injection / high_risk）
  - `graph_clarification_trigger_total` — 澄清触发计数
  - `graph_recursion_error_total` — 递归超限计数
  - `graph_approval_interrupt_total` — HITL 中断计数

### 6.3 Logs

- [ ] 结构化日志包含 `trace_id` 字段
- [ ] 敏感信息（完整路径、API Key）不写入日志
- [ ] 日志级别合理：生产 `INFO`，调试 `DEBUG`

### 6.4 trace_id 透传

- [ ] `init_state()` 生成全局唯一 trace_id
- [ ] 所有日志、OTel span、metrics 全部挂载 `state["trace_id"]`
- [ ] 节点内部禁止重新生成 trace_id

---

## 七、记忆体系

### 7.1 短期记忆（Checkpointer）

- [ ] 单次会话状态快照正确保存
- [ ] Time-Travel 可用：`get_state()` / `get_state_history()` 接口正常
- [ ] Checkpoint 包含完整状态字段，无遗漏

### 7.2 长期记忆（Store）

- [ ] `memory_store.py` 已接入
- [ ] namespace 按 `("user", user_id)` 隔离
- [ ] 证据分级正确：
  - **A级**（用户原始输入）→ 写入长期事实
  - **B级**（工具执行结果）→ 写入素材日志
  - **D级**（LLM 推论）→ **禁止固化**，仅临时使用
- [ ] D 级推论 `put()` 调用时自动跳过，不写入 Store

---

## 八、接口与路由

### 8.1 Graph 接口

| 接口 | 方法 | 状态 |
|------|------|------|
| `/desktop/graph/invoke` | POST | [ ] 可用 |
| `/desktop/graph/approval` | POST | [ ] 可用 |
| `/desktop/graph/state` | GET | [ ] 可用 |
| `/desktop/graph/history` | GET | [ ] 可用 |
| `/agent/graph/invoke` | POST | [ ] 可用 |
| `/agent/graph/approval` | POST | [ ] 可用 |
| `/agent/graph/state` | GET | [ ] 可用 |
| `/agent/graph/history` | GET | [ ] 可用 |

### 8.2 兼容接口

| 接口 | 方法 | 状态 |
|------|------|------|
| `/agent/command` | POST | [ ] 可用（原有快路径） |
| `/agent/solve-problems` | POST | [ ] 可用 |
| `/desktop/open` | POST | [ ] 可用 |
| `/desktop/find` | POST | [ ] 可用 |
| `/desktop/close` | POST | [ ] 可用 |
| `/desktop/running` | GET | [ ] 可用 |

### 8.3 系统接口

| 接口 | 方法 | 状态 |
|------|------|------|
| `/health` | GET | [ ] 返回 `{"status":"ok"}` |
| `/metrics` | GET | [ ] 返回 counters + histograms |

---

## 九、测试

### 9.1 单元测试

- [ ] `pytest app/services/graph/tests/test_graph.py -v` — **35 passed, 0 failed**
- [ ] 测试覆盖：
  - Pydantic 参数校验（合法路径 / shell 注入）
  - Guard 前置检查（拦截 / 放行）
  - 风险分级（高 / 中 / 低）
  - Validation Gate（假 PID 检测 / 进程未存活）
  - 意图置信度（高 / 低 → 澄清）
  - Trace Hash（不含原始路径 / 确定性）
  - State 初始化（trace_id / session_id）
  - 错误类型区分（transient / security / business）
  - build_invoke_config（复合 thread_id / 自定义 recursion_limit）
  - Checkpointer 工厂（dev / test 降级）
  - Memory Store（A/B/D 级证据）
  - Metrics（counter / histogram）

### 9.2 集成测试

- [ ] `api_test.http` 脚本全部接口可执行
- [ ] 正常流程端到端验证
- [ ] HITL 审批完整流程验证
- [ ] 命令注入拦截验证

---

## 十、部署

### 10.1 Docker

- [ ] `Dockerfile` 构建成功：`docker build -t ecv-server .`
- [ ] `docker-compose.yml` 全部服务启动：`docker compose up -d`
- [ ] 服务依赖顺序正确：postgres → redis → otel-collector → server
- [ ] 健康检查通过：`curl http://localhost:8000/health`

### 10.2 数据初始化

- [ ] `scripts/init_postgres.sql` 自动执行（docker-entrypoint-initdb.d）
- [ ] checkpoints / memory_store 表已创建
- [ ] 索引已建立：`idx_checkpoints_thread` / `idx_memory_store_user` / `idx_memory_store_level`

### 10.3 资源限制

- [ ] 单用户并发任务限制（`MAX_CONCURRENT_PER_USER`）
- [ ] 防止短时间大量 subprocess 拉起耗尽系统资源
- [ ] Redis `maxmemory` 限制已设置

---

## 十一、上线后验证

### 11.1 冒烟测试

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. Metrics 端点
curl http://localhost:8000/metrics

# 3. 正常流程
curl -X POST http://localhost:8000/desktop/graph/invoke \
  -H "Content-Type: application/json" \
  -d '{"user_id":"smoke_test","session_id":"smoke_001","query":"打开微信"}'

# 4. 安全拦截
curl -X POST http://localhost:8000/desktop/graph/invoke \
  -H "Content-Type: application/json" \
  -d '{"user_id":"smoke_test","session_id":"smoke_002","query":"打开 C:\\Windows\\System32\\cmd.exe; rm -rf /"}'

# 5. HITL 审批
curl -X POST http://localhost:8000/desktop/graph/invoke \
  -H "Content-Type: application/json" \
  -d '{"user_id":"smoke_test","session_id":"smoke_003","query":"运行 cleanup.bat"}'
```

### 11.2 监控确认

- [ ] OTel Collector 收到 traces / metrics / logs
- [ ] Prometheus 抓取到 `graph_node_duration_seconds` 等指标
- [ ] LangFuse 面板可查看 trace 详情
- [ ] 无 `GraphRecursionError` 异常
- [ ] 无 security 拦截误报（合法路径被拦截）

---

## 十二、回滚预案

| 场景 | 操作 |
|------|------|
| Graph 执行异常 | 前端降级调用 `/agent/command` 快路径 |
| PostgresSaver 连接失败 | `get_checkpointer()` 自动降级 SqliteSaver → MemorySaver |
| OTel Collector 不可用 | tracing 初始化失败 non-fatal，服务正常启动 |
| HITL 审批超时 | 前端展示超时提示，用户可重新发起请求 |

---

## 十三、后续迭代（架构预留，暂不开发）

1. **快慢脑架构**：快脑前置节点过滤无效输入，减少昂贵 LLM 调用
2. **Governor 治理循环**：定期扫描记忆仓库，清理过期/冲突证据
3. **Supervisor 诊断 Agent**：自动诊断意图识别/路由失败，生成纠错信号
4. **Tool Search 延迟加载**：工具数量膨胀后按需加载 schema
5. **限流断路器**：上层网关控制单用户并发，防止 subprocess 资源耗尽