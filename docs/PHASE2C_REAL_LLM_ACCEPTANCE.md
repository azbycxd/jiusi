# Phase 2C-2 Real LLM Dynamic Agent Loop 验收

## A. Real Model Adapter 设计

保留 `DecisionModel` Protocol，新增 `RealLLMDecisionModel`。它是同步、可注入 `httpx.Client` 的 OpenAI-compatible `/chat/completions` HTTP Adapter；Orchestrator 只依赖 `DecisionModel`，不导入任何厂商 SDK。

```text
DecisionStage → DecisionModel → FakeDecisionModel（仅测试）| RealLLMDecisionModel（配置化 HTTP Provider）
```

Provider 返回内容先解析为 JSON object，再由既有 `AgentDecision` Pydantic Contract 校验。Provider 的 JSON 能力不替代 Harness 校验。

## B. Prompt 输入结构

系统 Prompt 限定模型只选择 `CALL_TOOL`、`ANSWER` 或 `HANDOFF`，不得输出 Chain-of-Thought、不得操作系统或编造业务事实。用户消息是脱敏 JSON，只有 `user_query`、`available_tools`（含 `get_order_facts` 的 `outTradeNo` schema）、`facts` 和 `evidence`。

可信身份值、认证 Header、Token、SQL、Redis Key、数据库配置、完整 Trace、Java 异常、Provider API Key 和响应 Header 都不进入可见 Context 或 Provider JSON body。

## C. AgentDecision 输出结构

未创建第二套 Schema，继续使用 `action`、`tool_name`、`tool_arguments`、`final_answer`、`used_evidence`、`missing_information`。`action` 仅为 `CALL_TOOL | ANSWER | HANDOFF`。

`CALL_TOOL` 仍经过 Capability、Registry、严格参数、去重和终止验证。`ANSWER.used_evidence` 仍必须引用当前 Facts 中的真实 leaf path；普通能力说明可使用空 evidence。能力不足（例如退款规则/退款状态）应 `HANDOFF`。

## D. Model error mapping

| 条件 | 稳定错误码 | 可重试 |
| --- | --- | --- |
| HTTP timeout | `MODEL_TIMEOUT` | 是 |
| 连接失败 | `MODEL_CONNECTION_ERROR` | 是 |
| HTTP 429 | `MODEL_RATE_LIMITED` | 是 |
| HTTP/API 5xx | `MODEL_HTTP_ERROR` | 是 |
| 非法/空 JSON 响应 | `MODEL_INVALID_RESPONSE` | 否 |
| 输出不符合 AgentDecision | `MODEL_CONTRACT_MISMATCH` | 是（有限） |
| 未分类调用异常 | `MODEL_INVOCATION_ERROR` | 否 |

Provider 异常不会映射为 Tool 异常，原始异常、响应、Header 或 stack trace 不会进入用户答案、Context 或 Trace。

## E. Model retry / termination

`model_call_count`、`model_retry_count`、`max_model_retries` 与 Tool 的 `tool_call_count` / `retry_count` 完全分离。重试型模型故障至多为首次调用加 `max_model_retries` 次额外调用；达到限制后 Orchestrator 转 `HANDOFF`，没有无限模型调用。

## F. 隐私与脱敏

测试捕获真实 Adapter 的 HTTP payload，验证它只有 `user_query`、`available_tools`、`facts`、`evidence`；可信身份值和 API Key 不会进入 JSON body。结构化 Trace 仅记录稳定错误分类、模型名、耗时和安全 telemetry，不记录 Prompt、响应正文、认证 Header 或密钥。

## G. Token / latency telemetry

若 Provider envelope 包含可靠 `usage.prompt_tokens`、`usage.completion_tokens` 和 `usage.total_tokens`，Adapter 将它们连同 Provider 返回的模型名记录到 `MODEL_DECISION` / `MODEL_VALIDATION_ERROR` Trace 事件。事件 `duration_ms` 使用本次模型调用的单调计时。Provider 未返回 usage 时字段为 `null`，不会伪造 token 或成本。

## H. FastAPI 如何选择真实动态 Loop

`.env.example` 新增 `LLM_MODEL`、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_TIMEOUT` 示例值，未含真实密钥。

- 三项必需配置均存在且合法：FastAPI 构造 `RealLLMDecisionModel`，进入 `dynamic-agent-loop`。
- 三项均未配置：FastAPI 明确使用 `compatibility_mode=True` 的 Phase 2B Facts-only 过渡路径，health 标识为 `phase2b-facts-compatibility`。
- 任意部分配置或非法 timeout：启动时明确抛出配置错误；不会静默降级为 FakeDecisionModel 或 Facts-only 路径。

## I. 单元测试结果

执行：`conda run -n group-buy-agent python -m pytest -q`

结果：`49 passed in 0.32s`。

覆盖 Adapter 合法 `CALL_TOOL` / `ANSWER` / `HANDOFF`、evidence 校验、非法 JSON、空响应、AgentDecision Contract mismatch、timeout、连接失败、429、HTTP 5xx、usage telemetry、payload/Trace 脱敏、有限模型重试、FakeDecisionModel 和既有动态 Tool Loop 回归。

## J. 是否真实调用模型

否。验收时只读取环境变量的“是否存在”状态：`LLM_MODEL`、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_TIMEOUT` 均未配置。未读取、输出或尝试任何密钥值，所有 Adapter 测试均使用 `httpx.MockTransport`。

## K. 三个真实场景结果

未执行：没有合法 Provider 配置，不能将 Mock/Fake 结果冒充真实模型调用。

- “你能帮我做什么？”：NOT_TESTED
- 订单事实 → Java → MySQL → 模型回答：NOT_TESTED
- “我的退款什么时候到账？”安全 HANDOFF：NOT_TESTED

## L. LLM → Tool → Java → MySQL → LLM

NOT_TESTED。Dynamic Agent Loop 和 Java Tool 已各有独立 Mock/既有验收，但本阶段没有有效 LLM 配置，未访问或修改 Java 项目，也未伪造该完整链路成功。

## M. 尚未实现内容

没有 RAG、向量库、长期 Memory、Multi-Agent、新业务 Tool、退款/写操作、动态 SQL、Python 诊断规则、复杂成本系统、Prompt 工程扩展或 Fine-tuning。真实 Provider 协议差异、真实限流、token usage 可靠性和端到端安全行为留待具备合法配置后的单独 live 验收。

`REAL_LLM_ADAPTER = PASS`

`REAL_LLM_LIVE_TEST = NOT_TESTED`

`REAL_LLM_DYNAMIC_AGENT_LOOP = NOT_TESTED`
