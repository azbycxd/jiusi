# 拼团客服与订单诊断 Agent（V1 骨架）

这是现有 Java 拼团系统的独立 Python Agent 服务。当前 Phase 2C-1.1 提供受控的动态 Agent Loop：模型只能提出严格的 `CALL_TOOL`、`ANSWER` 或 `HANDOFF` 决策，编排器验证并执行允许的工具。当前只有 `get_order_facts`，不生成“为什么未成团”的业务诊断。

## 职责边界

Java 继续负责订单/拼团/活动的真实状态、资格、权限、MySQL、Redis、业务规则、事务、幂等和任何写操作。Python 负责自然语言入口、路由、槽位、State、Tool 编排、错误恢复、Guardrail、Trace 与 Eval。

因此 Agent 不直连 DB 或 Redis：它不应绕过 Java 的权限校验、事务/幂等约束和业务事实边界。它不执行 SQL、Shell、任意 HTTP，也不能退款或修改订单。实时事实只能通过配置化的 Java 高层只读 `/api/v1/agent/order/facts` API 获取。

## 控制模型

`AgentState` 分开保存：Capability（显式白名单 Tool）、Context（当前任务槽位、ToolResult、OrderFacts、evidence 和去重调用历史）和 Control（状态、Tool/Model 独立重试与次数限制）。Session Memory 只是进程内任务恢复；不是长期记忆。RAG 当前只预留 FAQ/规则检索接口，绝不能判断订单实时状态。

Tool 统一返回 `ToolResult(success, error_code, message, data, evidence, retryable, source)`；不抛异常不等于业务成功。Agent Loop 为 `Decision → validation → Tool → observation → Decision`：模型可见内容仅包括用户问题、规范化 Facts/evidence 和安全 Tool Schema；可信身份、Header、Trace 和内部异常均不可见。`retry_count` 只计首次 Tool 调用失败后的额外重试次数，因此 `max_retries=1` 表示首次调用加最多一次重试；`model_retry_count` 独立计数。所有 `out_trade_no` 来源均须经过同一个确定性 Validator。`RUNNING`、`WAITING_USER`、`FINISHED`、`FAILED`、`HANDOFF` 是一等状态，且有最大迭代、Tool 调用、重试及超时配置，禁止无限循环。

## 目录

```
app/             FastAPI 最小 Chat API
agent/           State、Router、Orchestrator、Termination、Slot Validator
tools/           ToolResult、显式 Registry、Java HTTP Client、Facts Contract、Fake Client
memory/          进程内 Session State
rag/             未来支持知识检索接口
guardrails/      可信身份与 Tool 策略
observability/   安全结构化 Trace
eval/            8 个 V1 可运行评测样例
tests/           单元和流程测试
docs/            架构、Failure Ledger、评测计划
```

## 运行

必须使用项目指定的 Conda 环境：

```powershell
conda run -n group-buy-agent python -m pip install -r requirements.txt
conda run -n group-buy-agent python -m pytest
conda run -n group-buy-agent uvicorn app.main:app --reload
```

Chat API 不接受用户 ID JSON 参数。生产环境应由认证中间件将可信身份注入；V1 用 `X-Authenticated-User-Id` Header 模拟该边界。

## 尚未实现

没有真实 LLM、RAG/向量库、Redis、数据库、长期用户画像、多 Agent、真实认证，或订单/退款写操作。动态 Loop 目前只由 `FakeDecisionModel` 在测试中驱动；实际 HTTP 端点以显式 `compatibility_mode=True` 保留 Phase 2B 的 Facts-only 过渡路径。Java HTTP Client 已完成独立的真实联调验收；本阶段不重复发起 Java 请求。
