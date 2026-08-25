# Phase 2B-2 Python Agent → Java → MySQL 真实联调

联调日期：2026-08-25。执行使用真实 `JavaMarketClient` HTTP；没有使用 `FakeMarketClient`、`httpx.MockTransport` 或 Stub Response。

## A. 实际 Python Agent 调用链

```text
AgentState
 -> OrderFactsOrchestrator
 -> ToolRegistry (get_order_facts)
 -> OrderFactsTool
 -> JavaMarketClient
 -> HTTP POST /api/v1/agent/order/facts
 -> Java Spring Boot / 已运行数据链路
 -> ToolResult
 -> ContextState.order_facts / evidence / Trace
```

正向、越权和错误地址测试均从 `OrderFactsOrchestrator.handle_message` 执行，而不是直接调用 Client。

## B. 配置

本次进程配置为 `JAVA_MARKET_BASE_URL=http://127.0.0.1:8091`、`JAVA_MARKET_ENABLE_DEV_AUTH_HEADER=true`。地址和测试身份均由进程环境/命令参数提供，未写入业务代码。Client 使用 `trust_env=False`，避免环境代理改变内部链路、认证边界或连接错误分类。

## C. 正向真实请求结果

使用本次提供的授权测试身份和订单号：

```text
status=FINISHED
final_answer=FACTS_RETRIEVED
tool_name=get_order_facts
ToolResult.success=true
ToolResult.source=java_market
tool_call_count=1
retry_count=0
```

## D. Java 返回的真实 Facts

```json
{
  "order": {"status": "CLOSE"},
  "team": {
    "status": "PROGRESS",
    "target_count": 3,
    "lock_count": 0,
    "complete_count": 0,
    "valid_end_time": "2026-07-30T03:45:37+08:00"
  },
  "activity": {"status": "EFFECTIVE"},
  "references": {"team_id": "18781389", "activity_id": 100123}
}
```

实际响应与给定预期核心事实一致。

## E. ToolResult

成功结果为 `success=true`、`error_code=null`、`source=java_market`，且 `data.facts` 是规范化 snake_case `OrderFacts`。没有产生 `reasonCode`。

## F. ContextState.order_facts

Facts 被写入 `ContextState.order_facts`，并同步 `team_id=18781389`、`activity_id=100123`。`diagnosis_code=null`；没有新增 CLOSE/PROGRESS 的 Python 业务判断。

## G. Evidence

- `order.status=CLOSE`
- `team.status=PROGRESS`
- `team.targetCount=3`
- `team.completeCount=0`
- `activity.status=EFFECTIVE`

只保存精简事实，未保存完整 HTTP Response。

## H. Trace

正向真实 Trace：

```text
ROUTED                 tool_call_count=0 retry_count=0
TOOL_RESULT get_order_facts success=true error_code=null duration_ms=14
FINISHED/persist_state tool_call_count=1 retry_count=0
```

Trace 包含 tool name、成功状态、error code、耗时、调用次数和 retry 次数；不包含开发认证 Header、认证身份或 Java Stack Trace。

## I. 越权结果

使用本次提供的非授权测试身份和同一订单号，真实 Java 返回结果映射为：

```text
success=false
error_code=ORDER_NOT_FOUND_OR_NOT_AUTHORIZED
retryable=false
source=java_market
ContextState.order_facts=null
evidence=[]
```

授权身份对应的订单 Facts 没有写入越权 AgentState。

## J. 无身份结果

空可信身份由 `OrderFactsTool` 在 HTTP 前拦截，未伪造 userId 参数或 Header：

```text
success=false
error_code=AUTH_REQUIRED
retryable=false
status=FAILED
```

拦截层是 `OrderFactsTool` 的可信身份边界。

## K. Connection failure 结果

使用 RFC 保留的 `.invalid` 测试 Base URL，经完整 Orchestrator → Tool → 真实 JavaMarketClient 路径得到：

```text
TOOL_CONNECTION_ERROR
retryable=true
tool_call_count=2
retry_count=1
terminal_status=HANDOFF
```

重试被有限策略终止，Java 服务未被停止或修改。

## L. pytest 结果

最终命令为 `conda run -n group-buy-agent python -m pytest -q`；结果为 `16 passed in 0.27s`。

## M. 是否修改业务代码

未增加 LLM、RAG、诊断规则或任何订单业务规则。为完成联调边界，仅修改 Python 基础设施：缺少可信身份时 Tool 在 HTTP 前稳定返回 `AUTH_REQUIRED`；内部 Java Client 禁用环境代理继承；并新增仅供联调的 Agent Runtime Harness。没有访问或修改 Java 项目。

## N. 尚未验证内容

未验证 Java 服务端日志/SQL 观测、生产认证中间件、生产网络拓扑、并发、Redis Session、LLM、RAG 或 Multi-Agent。MySQL 未被 Python 直接访问；`JAVA_TO_MYSQL_PATH` 依据真实 Java 服务返回的持久化事实做端到端验证，而不是直接数据库探测。

`PYTHON_TO_JAVA_INTEGRATION = PASS`

`JAVA_TO_MYSQL_PATH = PASS`

`AGENT_FACTS_STATE_INTEGRATION = PASS`

`AUTHORIZATION_END_TO_END = PASS`
