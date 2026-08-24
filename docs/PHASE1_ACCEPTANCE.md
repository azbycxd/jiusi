# Phase 1 工程骨架验收

验收日期：2026-08-24  
验收范围：仅当前 Python V1 控制骨架；没有接入真实 LLM、Java 服务、RAG、数据库、Redis 或任何 Agent 框架。

## A. 当前控制流程

```text
用户消息
  -> 确定性 Router / 槽位提取
  -> 缺失 outTradeNo: WAITING_USER 并保存 Session State
  -> get_order_diagnosis（显式白名单）
  -> ToolResult 写入 Context / evidence
  -> reasonCode 模板回答: FINISHED
     或失败恢复 / 次数上限 / 未知诊断: HANDOFF 或 FAILED
  -> 保存 State，并记录终态 Trace
```

`AgentState` 实际分为 Capability、Context、Control 三部分。`authenticated_user_id` 位于根 State，Tool 通过 State 构造 `AuthContext`；模型可影响的订单槽位只有 `out_trade_no`，不存在 `userId + outTradeNo` 的 Tool 调用形态。

## B. 实际执行场景

| 场景 | 实际结果 |
| --- | --- |
| `202608240001` / `GROUP_IN_PROGRESS` | `FINISHED`；1 次 Tool 调用；产生模板回答。 |
| 缺订单号，随后提交 `202608240001` | 首轮 `WAITING_USER` 且 `missing_fields=[out_trade_no]`；第二轮同 session 恢复，`iteration_count` 从 1 到 2，最终 `FINISHED`。 |
| 可重试失败 `202608240005` | 2 次 Tool 调用，`retry_count=1`，达到 `max_retries` 后 `HANDOFF`。 |
| 永久失败 `202608240006` | 1 次 Tool 调用，未重试，`FAILED`。 |
| 未知 reasonCode `202608240007` | Tool 成功但 `FUTURE_REASON_CODE` 进入 `HANDOFF`。 |
| 不存在或无权 `202608240004` | `FINISHED`；对外统一为“订单不存在，或当前账号无权查看”，未泄露订单归属。 |
| `max_iterations=1` | Tool 调用前进入 `HANDOFF`。 |
| `max_tool_calls=1` + 可重试失败 | 第 1 次失败后的下一循环进入 `HANDOFF`，未发生第 2 次 Tool 调用。 |

完整成功 Trace 包含同一个 `trace_id` 的 `ROUTED`、`TOOL_RESULT`、`FINISHED/persist_state` 三个事件。每个事件均带有 `trace_id`、`session_id`、`stage`、`action`、`tool_name`、`tool_success`、`error_code`、`duration_ms`、`iteration_count`、`tool_call_count`。

## C. 环境与 pytest

- Conda env：`group-buy-agent`
- Python：`3.11.15`
- 可执行文件：`D:\\soft\\anaconda3\\envs\\group-buy-agent\\python.exe`
- 命令：`conda run -n group-buy-agent python -m pytest -q`
- 结果：`13 passed in 0.17s`

## D. 控制骨架核验

| 项目 | 结论 | 证据 |
| --- | --- | --- |
| State | 通过 | `RUNNING`、`WAITING_USER`、`FINISHED`、`FAILED`、`HANDOFF` 均在流程中被实际赋值和断言。计数、缺失字段、ToolResult、diagnosis code 均参与分支控制。 |
| ToolResult | 通过 | 统一字段为 `success`、`error_code`、`message`、`data`、`evidence`、`retryable`、`source`。`success=False` 的业务失败、可重试基础设施失败和永久失败走不同控制路径；没有以“未抛异常”当作成功。 |
| Tool Registry | 通过 | 运行时 allowlist 只有 `get_order_diagnosis`；没有 shell、SQL、Redis、generic HTTP 或自动函数发现。 |
| 身份边界 | 通过（V1 模拟认证） | `GetOrderDiagnosisTool.run(state)` 不接收 user id；Facade 签名为 `(auth: AuthContext, out_trade_no: str)`。 |
| Termination | 通过 | 没有 `while True`；受限 retry 循环同时受 `max_retries`、`max_tool_calls`、`max_iterations` 强制终止。 |
| Trace | 通过 | 实际输出结构化 JSON，字段白名单中没有 token、密码或认证凭证。 |

## E. Session 恢复

通过。`SessionMemory.save_state` 保存首轮 `ORDER_DIAGNOSIS/WAITING_USER` State；第二轮以相同 session 和可信用户身份加载该 State，保留 intent，并在补齐订单号后完成诊断。第二轮不是独立新任务。

## F. 发现问题及修复

发现终态仅从返回 State 可见，Trace 原先只记录到 ToolResult。已修复：`_save` 在保存任何状态后记录 `persist_state` 终态事件，并补齐“订单不存在或无权”分支的 Trace 传递。新增验收测试覆盖完整成功 Trace 和两个次数上限。

## G. 仍为 Stub 的模块

- `JavaMarketClient`：本地 fixture，不发真实 HTTP 请求。
- FastAPI 的身份 Header：仅模拟可信身份注入，尚未对接真实认证中间件。
- `SessionMemory`：进程内内存，不持久化、不支持多实例共享。
- RAG、LLM、真实 Java Facade、数据库、Redis、长期记忆、多 Agent、订单写操作：均未实现。

## H. 第二阶段准入结论

控制骨架、工具边界、身份注入边界、终止协议、恢复路径、失败恢复与 Trace 均有实际执行证据，且全量测试通过。可进入第二阶段的接口契约设计/真实 Java 只读 Facade 接入准备；本次未开始第二阶段开发。

`PHASE1_ACCEPTANCE = PASS`
