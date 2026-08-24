# V1 架构

## 边界

Java 系统是订单、拼团、活动、资格、权限、状态转换、幂等和事务的唯一事实来源。Python 服务只编排自然语言任务，并且只能经未来的 Java 高层只读 Facade 获取实时业务事实。V1 的 `JavaMarketClient` 是本地 Stub，不会发 HTTP 请求。

Python Agent 不直连 MySQL 或 Redis，不执行 SQL、Shell、任意 URL 请求，也不根据模型输出改变订单、退款或判断金额/资格。这样可让业务写入与确定性规则继续处于 Java 的权限、事务与审计边界内。

## State、Context、Memory、RAG

- `AgentState` 是每个任务的总容器。它明确分为 `CapabilityState`（仅 `get_order_diagnosis` 白名单）、`ContextState`（下一步可见的订单槽位、ToolResult、evidence）和 `ControlState`（状态机、次数和时限）。
- Context 不是持久用户记忆；它只描述当前诊断任务。
- `SessionMemory` 是进程内、按 session 保存/加载 State 的最小实现，只用于第二轮补订单号恢复任务，不保存用户画像，也不接 Redis/数据库。
- `rag/retriever.py` 只是未来 FAQ、规则和错误码知识的接口；RAG 不得判断订单实时状态。

## ToolResult 和流程

每个 Tool 都返回带有 `success`、`error_code`、`message`、`data`、`evidence`、`retryable`、`source` 的 `ToolResult`。代码未抛异常不代表业务成功；业务不可见、参数错误和基础设施暂时失败是不同结果。ToolResult/evidence 被写回 Context，供下一受控步骤使用。

V1 流程为：确定性路由 → 提取订单号 → 缺失则 `WAITING_USER` → 注入可信身份调用白名单 Tool → 消费 Java `reasonCode` 模板回答 → `FINISHED`。未知 reasonCode、超限和可重试故障耗尽后进入 `HANDOFF`。永久 Tool 故障进入 `FAILED`。

不存在自由 ReAct 或 `while True`。唯一重试循环由 `max_retries`、`max_tool_calls` 和 `max_iterations` 共同限制。Trace 输出结构化 JSON，包含调用阶段、动作、结果、错误、耗时和计数，但不记录 token、密码、认证凭证或其他用户敏感信息。
