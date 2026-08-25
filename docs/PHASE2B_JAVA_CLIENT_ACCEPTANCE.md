# Phase 2B-1 Java Order Facts Client 验收

## A. Python 调用链

```text
AgentState (trusted authenticated_user_id, out_trade_no)
  -> OrderFactsOrchestrator
  -> ToolRegistry allowlist: get_order_facts
  -> OrderFactsTool
  -> JavaMarketClient / FakeMarketClient
  -> POST {JAVA_MARKET_BASE_URL}/api/v1/agent/order/facts
  -> ToolResult
  -> ContextState.order_facts + tool_results + evidence + Trace
```

当前成功后的状态为 `FINISHED`，`final_answer=FACTS_RETRIEVED`。这仅代表事实已取得，不代表生成了客服诊断。

## B. 修改文件

- `tools/java_market_client.py`：配置化真实同步 HTTP Client、Envelope 检查、错误映射和 `OrderFactsTool`。
- `tools/facts.py`：`OrderFact`、`TeamFacts`、`ActivityFacts`、`OrderReferences`、`OrderFacts` 的规范化 Python Contract。
- `tools/fake_market_client.py`、`tools/base.py`：可注入的 MarketClient 测试边界。
- `agent/orchestrator.py`、`agent/state.py`、`agent/router.py`：Facts 意图、`get_order_facts` 调用、Context Facts 保存。
- `observability/trace.py`：增加 `retry_count` 字段。
- `.env.example`、README、架构/Eval 文档、测试：更新配置、命名和验证。

## C. `get_order_diagnosis` 迁移

活动路径已经迁移为 `get_order_facts`：Capability allowlist、Registry、Orchestrator、Trace action、测试和当前架构文档均使用新名称。旧 Diagnosis Tool 不存在于当前 Registry，也不在生产调用链中。历史 Phase 1 验收记录保留原名，仅作为历史证据。

## D. Java Contract 建模

HTTP Client 按顺序验证 transport、HTTP 状态、JSON 合法性、Envelope `code` 和成功 `data` Schema。`code=0000` 时，Pydantic 将 Java camelCase 数据转换为明确的 `OrderFacts` 合同；内部 Context 数据使用 snake_case，而不是透传任意原始 dict。

## E. 可信身份注入

Tool 输入只有 State 中的订单号。`OrderFactsTool` 从 `AgentState.authenticated_user_id` 构造 `AuthContext`；`JavaMarketClient` 在 `JAVA_MARKET_ENABLE_DEV_AUTH_HEADER=true` 时才注入开发专用 `X-Dev-Authenticated-User-Id` Header。该 Header 不属于 Router/LLM Tool 参数，也不写入 Trace。

## F. Java code → ToolResult

| Java/Transport 结果 | Python `error_code` | retryable |
| --- | --- | --- |
| `0000` + 合法 Schema | `success=true`, `source=java_market` | false |
| `AUTH_REQUIRED` | `AUTH_REQUIRED` | false |
| `INVALID_ARGUMENT` | `INVALID_ARGUMENT` | false |
| `ORDER_NOT_FOUND_OR_NOT_AUTHORIZED` | 同名 | false |
| `INTERNAL_SERVICE_ERROR` | 同名 | true（受既有次数上限约束） |
| HTTP timeout | `TOOL_TIMEOUT` | true |
| connection failure | `TOOL_CONNECTION_ERROR` | true |
| 非 2xx HTTP | `HTTP_UNEXPECTED_STATUS` | 5xx 为 true |
| 非法 JSON | `TOOL_MALFORMED_JSON` | false |
| Envelope/Data Schema 不匹配 | `TOOL_CONTRACT_MISMATCH` | false |
| 未知 Java code | `TOOL_UNKNOWN_RESPONSE_CODE` | false |

异常消息或 Java 堆栈不会进入用户答案或 Trace。

## G. Timeout、连接与契约错误

Client 不将这些错误抛给 Orchestrator：它们都会在 Client 层变成稳定 `ToolResult`。可重试的纯只读错误仍通过 `max_retries`、`max_tool_calls` 和 `max_iterations` 有限终止；不会无限重试。

## H. Facts 进入 AgentState

成功结果写入：

- `ContextState.order_facts`：规范化 Facts。
- `ContextState.tool_results`：完整统一 ToolResult。
- `ContextState.evidence`：精简的 order/team/activity 状态事实。
- `ContextState.team_id`、`activity_id`：从 references 复制。

`diagnosis_code` 保持为空；本阶段不会创建 reasonCode 或判断“为什么未成团”。Trace 记录 `get_order_facts`、成功与否、error code、局部调用耗时、调用总数和 retry 次数。

## I. 测试结果

命令：`conda run -n group-buy-agent python -m pytest -q`  
结果：`15 passed in 0.54s`

覆盖 Java `0000` 解析、开发身份 Header、无 userId Tool 输入、四个已知 Java code、timeout、connection、非 2xx、非法 JSON、Schema mismatch、Facts Context 写入、Session 恢复、非法 slot、有限重试、Trace retry 字段以及 Router/Tool 无 State 副作用。

## J. 真实 Java HTTP 联调

本阶段没有向 Java 服务发出真实 HTTP 请求。测试仅使用 `httpx.MockTransport` 与 `FakeMarketClient`。

`LIVE_JAVA_INTEGRATION = NOT_TESTED`

## K. 尚未验证内容

未验证真实 Java 服务启动、真实认证中间件、Python→Java→MySQL 链路、网络/代理部署行为、生产 Header 模式或真实订单数据。LLM、RAG、多 Agent、Redis、数据库写入仍不在本阶段范围内。

`PHASE2B_CLIENT_IMPLEMENTATION = PASS`
