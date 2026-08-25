# Phase 1.1 结构性修正

## 1. 修改内容与必要性

### 重试语义

`tool_call_count` 现在明确表示实际 Tool 调用总数；`retry_count` 仅表示首次调用失败之后发生的额外调用数。诊断循环使用 `range(max_retries + 1)`，因此 `max_retries=1` 明确等于首次调用加最多一次重试。此前虽然行为正确，但 `while retry_count <= max_retries` 容易在后续改动时产生边界误读。

### 终态 Context 保留

Orchestrator 不再因为 Session State 已处于 `FINISHED`、`FAILED` 或 `HANDOFF` 而重新构造空 `AgentState`。重新收到同一可信用户的同 session 消息时，复用既有 State，保留 intent、订单号、ToolResult、evidence 和 diagnosis code；只转换本轮必要的 Control State。此前新建 State 会使后续 LLM/Java Tool 无法审计前序观察结果。

### Slot Validator

新增 `agent/slots.py` 的 `validate_out_trade_no`。它统一执行空值、类型、trim、最大技术长度和宽字符集校验，不猜测 Java 的真实订单号业务格式。Router 输出和 Tool 防御性调用均使用该入口；非法 Router 槽位停在 `WAITING_USER`，不会执行 Tool。

### Tool 异常边界

新增 `tools/errors.py`，以稳定错误码区分 timeout、connection、authorization、invalid argument 和 unexpected error。预期错误映射为明确的 `retryable`；未知异常在最外层被安全映射为 `TOOL_UNEXPECTED_ERROR`，不把异常消息或栈返回用户。保留 Orchestrator 最外层兜底，以防未来不符合 Tool 协议的实现抛异常。

### State 更新责任

Router 现在是纯函数，返回不可变 `RoutingResult`；Orchestrator 是唯一应用路由结果并变更 State 的模块。Tool 只读 State、构造可信 `AuthContext` 并返回 `ToolResult`。关键状态转换仍集中于 Orchestrator 与 `TerminationPolicy`。

## 2. 新增测试

- `max_retries=1` 实际为 2 次 Tool 调用、1 次 retry。
- 终态 Session 再次处理时关键 Context 与历史 ToolResult/evidence 不丢失。
- 非法订单号不进入 Tool 调用。
- timeout 为可重试；invalid argument 不可重试。
- unexpected exception 不暴露原始内容，也不重复重试。
- Router 与 Tool 均不会产生不可追踪的 AgentState 原地副作用。

## 3. 明确延期

Redis Session、TTL、多实例一致性、分布式锁、Session version、deep-copy 优化、evidence 压缩、全生命周期 Trace 指标、LLM、RAG、真实 Java HTTP、Multi-Agent 均未实现，已记录在 Failure Ledger 或保持 V1 Stub 边界。

## 4. 验证结果

在 `group-buy-agent` Conda 环境中执行 `conda run -n group-buy-agent python -m pytest -q`，结果为 `19 passed in 0.24s`。

## 5. Phase 2 准入

本次仅改变接口与控制骨架，不改变 V1 业务场景或接入外部服务。完成全量测试后，可进入 Phase 2 的 Java 只读 Facade 契约设计；本次不会开始该阶段。

`PHASE1_1_REFACTOR = PASS`
