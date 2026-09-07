# Tool 超时、有限重试与 HANDOFF

## 用户输入

`查询订单 644398015396 的状态。`

## Task / RoutingResult / Skill

Intent=`ORDER_DIAGNOSIS`，Skill=`order_diagnosis`，参数来自用户；required dimension=`order`。

## 初始 AgentState

tool_call_count=0、tool_retry_count=0、observations=[]、order_state=PENDING。

## DecisionContext #1 / Decision #1

```json
{"action":"CALL_TOOL","tool_name":"get_order_facts","tool_arguments":{"outTradeNo":"644398015396"}}
```

## Harness Validation

能力、Schema、身份、Provenance、Repeat 与预算均通过，开始首次实际调用。

## ToolResult attempt=1

```json
{"tool_name":"get_order_facts","success":false,"data":null,"error_code":"TOOL_TIMEOUT","error_message":"暂时无法取得所需业务事实","retryable":true,"source":"java_market","attempt":1}
```

TimeoutPolicy 将异常稳定分类为 retryable；RetryPolicy 在 max_retries=1 时允许一次额外重试。此时 tool_call_count=1，tool_retry_count=0；第一次重试开始时 retry_count 才增加。

## ToolResult attempt=2

```json
{"tool_name":"get_order_facts","success":false,"data":null,"error_code":"TOOL_TIMEOUT","error_message":"暂时无法取得所需业务事实","retryable":true,"source":"java_market","attempt":2}
```

现在 tool_call_count=2、tool_retry_count=1，额外重试额度耗尽。RetryPolicy 返回 false，FailurePolicy 选择 HANDOFF。

## Observation / Evidence / Progress

- Observation：不创建。
- Evidence：不创建。
- Progress：order_state Obligation 仍为 PENDING。
- 禁止推断：不能说订单不存在、失败、属于别人或状态异常。

## 最终状态

```json
{"task_status":"HANDOFF","response_message":"当前事实查询失败，无法可靠给出业务结论。","tool_call_count":2,"tool_retry_count":1,"observations":[]}
```

## Trace 摘要

`MODEL_DECISION → TOOL_CALL(attempt1) → TOOL_RESULT(TOOL_TIMEOUT) → RETRY → TOOL_CALL(attempt2) → TOOL_RESULT(TOOL_TIMEOUT) → RETRY_EXHAUSTED → HANDOFF`

Trace 可以记录稳定错误码和 duration，不记录 Java stack、认证 Header 或原始异常。

## 为什么不是固定 Workflow

Retry 是同一个已验证动作的瞬时恢复策略，不是模型规划；若第二次成功，Loop 回到 Observation/Decision。它没有规定其它 Tool 顺序。

## 面试追问

1. retry_count 为什么不包含首次调用？
2. Retry 与 Repeat 的差别？
3. timeout 为什么是 INFRA/TOOL failure 而不是业务 Evidence？
4. 什么条件需要 circuit breaker？
5. 为什么不能无限增加 timeout？
