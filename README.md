# 拼团客服与订单诊断 Agent（V1 骨架）

这是现有 Java 拼团系统的独立 Python Agent 服务。V1 只支持一个受控场景：用户询问拼团订单为何未成功，服务请求订单号、恢复同一会话中的补充订单号、调用订单诊断 Tool，并按 Java 返回的 `reasonCode` 输出简单解释。

## 职责边界

Java 继续负责订单/拼团/活动的真实状态、资格、权限、MySQL、Redis、业务规则、事务、幂等和任何写操作。Python 负责自然语言入口、路由、槽位、State、Tool 编排、错误恢复、Guardrail、Trace 与 Eval。

因此 Agent 不直连 DB 或 Redis：它不应绕过 Java 的权限校验、事务/幂等约束和业务事实边界。它不执行 SQL、Shell、任意 HTTP，也不能退款或修改订单。实时事实只能来自未来 Java 提供的高层只读 `getOrderDiagnosis` Facade。

## 控制模型

`AgentState` 分开保存：Capability（显式白名单 Tool）、Context（当前任务槽位、ToolResult 和 evidence）和 Control（状态、重试与次数限制）。Session Memory 只是进程内任务恢复；不是长期记忆。RAG 当前只预留 FAQ/规则检索接口，绝不能判断订单实时状态。

Tool 统一返回 `ToolResult(success, error_code, message, data, evidence, retryable, source)`；不抛异常不等于业务成功。`RUNNING`、`WAITING_USER`、`FINISHED`、`FAILED`、`HANDOFF` 是一等状态，且有最大迭代、Tool 调用、重试及超时配置，禁止无限循环。

## 目录

```
app/             FastAPI 最小 Chat API
agent/           State、Router、Orchestrator、Termination、模板回答
tools/           ToolResult、显式 Registry、Java Facade Stub
diagnosis/       Java reasonCode 定义
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

没有真实 LLM、真实 Java 调用、RAG/向量库、Redis、数据库、长期用户画像、多 Agent、真实认证，或订单/退款写操作。`tools/java_market_client.py` 的订单结果只是本地测试 fixture，不能代表真实业务判断。
