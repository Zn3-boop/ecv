# Desktop-Agent LangGraph 流9程图

## 主执行流程

```mermaid
flowchart TD
    START([START]) --> FB[fast_brain<br/>快脑过滤]
    FB -->|reject| EF[error_fallback_node<br/>错误降级]
    FB -->|pass| ID[detect_intent<br/>意图识别]
    ID --> EE[extract_entities<br/>实体抽取+Query改写]
    EE --> RT[route_llm<br/>路由决策]
    RT -->|confidence >= threshold| RC[risk_check_node<br/>风险评级]
    RT -->|confidence < threshold| CL[clarification_node<br/>澄清]
    RC -->|approval_required| AP[approval_node<br/>HITL审批]
    RC -->|pass| TS[tool_search_node<br/>工具检索]
    AP -->|approved| TS
    AP -->|rejected| EF
    TS --> AG[app_launch_agent_node<br/>执行]
    AG --> TE[tool_execute_node<br/>工具执行+Guard预检]
    TE --> VG[post_validate_gate<br/>执行后校验]
    VG -->|transient_error+retry<max| TE
    VG -->|business/security_error| EF
    VG -->|pass| MP[memory_persist_node<br/>记忆落盘]
    MP --> END([END])
    CL --> MP
    EF --> MP
```

## Tool-Search 延迟加载

```mermaid
flowchart LR
    Q[tool_search_query] --> TS[ToolSearch.search_tool]
    TS -->|命中| LD[load_tool_schema]
    TS -->|0命中| MET[metrics: tool_search_zero_hit_total]
    LD --> SCHEMA[tool_loaded_schema<br/>注入LLM上下文]
```

## Governor 治理流程

```mermaid
flowchart TD
    WRITE[put_memory 写入] --> LS[governor_light_scan<br/>轻量扫描]
    LS -->|冲突/过期| SIG[generate_correction_signal<br/>产出纠错信号]
    SIG --> PERSIST[_dump_signals<br/>磁盘持久化]
    
    API[/desktop/graph/governor/full-scan/] --> FS[full_scan<br/>全量扫描]
    FS -->|conflict+expired| SIG2[generate_correction_signal]
    SIG2 --> PERSIST
```

## 信号状态机

```mermaid
stateDiagram-v2
    [*] --> open
    open --> processing : Owner认领
    open --> resolved : 直接关闭
    processing --> resolved : 处理完成
    resolved --> [*]
```

## HITL 人工审批流程

```mermaid
sequenceDiagram
    participant User
    participant API as FastAPI /desktop/graph/invoke
    participant Graph as LangGraph
    participant Approval as approval_node
    
    User->>API: POST /invoke {raw_query}
    API->>Graph: ainvoke(input_state)
    Graph->>Approval: interrupt_before
    Approval-->>Graph: 等待审批
    Graph-->>API: is_interrupted=true
    
    User->>API: POST /approval {thread_id, approval_status=ok}
    API->>Graph: aupdate_state({approval_status: ok})
    Graph->>Graph: 继续执行
    Graph-->>API: result
    API-->>User: {success, result}
```

## LLM 调用 + 重试 + 降级

```mermaid
flowchart TD
    CALL[llm_parse_with_retry] --> TRY[LLM API调用]
    TRY -->|成功+parse成功| OK[返回 parsed模型]
    TRY -->|成功+parse失败| FALL[返回 None + raw<br/>⚠️ 禁止重试]
    TRY -->|异常| CHECK{is_transient?}
    CHECK -->|是: 429/5xx/Timeout| RETRY[重试 max_retry次]
    RETRY --> TRY
    CHECK -->|否: 400/401/403| FALL
    RETRY -->|达到上限| FALL
    
    FALL --> DEGRADE[业务函数降级兜底]
    DEGRADE -->|detect_intent| D1["unknown", 0.0]
    DEGRADE -->|route| D2["clarification_node", {}, 0.0]
    DEGRADE -->|rewrite| D3["raw_query, [raw_query]"]
```

## 可观测性架构

```mermaid
flowchart LR
    APP[FastAPI App] -->|OTEL_TRACE_ENABLE=true| OTEL[OTel SDK]
    OTEL -->|OTLP HTTP| JAEGER[Jaeger :4318]
    JAEGER --> UI[Jaeger UI :16686]
    
    APP -->|GRAPH_ENV=prod| PROM[Prometheus Client]
    PROM -->|/metrics text/plain| PROMUI[Prometheus :9090]
    
    APP -->|GRAPH_ENV=dev| MEM[内存 dict]
    MEM -->|/metrics JSON| DEVUI[开发调试]
```

## Docker 部署架构

```mermaid
flowchart TB
    subgraph Docker Compose
        APP[fastapi-app :8000]
        PG[postgres :5432]
        JAE[jaeger :16686/:4318]
        PROM[prometheus :9090]
    end
    
    APP --> PG
    APP -->|OTLP| JAE
    PROM -->|scrape /metrics| APP
    
    USER[用户浏览器] -->|:8000/docs| APP
    USER -->|:16686| JAE
    USER -->|:9090| PROM
```