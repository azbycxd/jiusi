# Phase 2C-1 历史 Decision Schema 记录（已由 Phase 2C-1.1 取代）

> 本文件记录早期固定 Facts → Decision 方案的历史验收，不描述当前活动实现。当前应以 `PHASE2C_AGENT_LOOP_ACCEPTANCE.md` 为准；活动架构使用 `AgentDecision(CALL_TOOL | ANSWER | HANDOFF)` 动态循环，不保留本文件所述的旧 `ENOUGH_EVIDENCE` / `NEED_MORE_EVIDENCE` Schema。

## A. 新增调用链

```text
AgentState
 -> OrderFactsOrchestrator
 -> get_order_facts / Java Facts Tool
 -> ContextState.order_facts
 -> DecisionStage (optional, injected)
 -> DecisionModel / FakeDecisionModel
 -> Decision Schema + Evidence/Tool 权限 Validation
 -> terminal decision / HANDOFF
```

未注入 `DecisionModel` 时，既有 Facts 流程不变：成功后为 `FINISHED / FACTS_RETRIEVED`。注入模型时，Facts 成功后才进入决策阶段。

## B. ModelAdapter 设计

`DecisionModel` 是 vendor-neutral Protocol，仅定义 `decide(context) -> object`。`DecisionStage` 负责：构造脱敏 `DecisionContext`、调用 Adapter、解析严格 Schema、验证 evidence 与 Tool 权限；它不修改 `AgentState`。Orchestrator 负责调用计数、重试、Trace、State 更新和终止。

本阶段唯一实现为 `FakeDecisionModel`：脚本化返回结果、记录 Model Context、无网络调用。没有任何真实 OpenAI、Claude、Qwen、DeepSeek SDK、API Key 或网络调用。

## C. Decision Schema

严格 Pydantic `Decision` 只有以下可审计字段：

```text
decision: ENOUGH_EVIDENCE | NEED_MORE_EVIDENCE | HANDOFF
diagnosis: str | null
used_evidence: list[str]
missing_information: list[str]
next_tool: str | null
```

不包含 reasoning steps、thoughts 或 chain-of-thought。`ENOUGH_EVIDENCE` 必须有诊断与至少一项 evidence；`NEED_MORE_EVIDENCE` 必须有 missing information 且不得给最终诊断；`HANDOFF` 不得请求 Tool。

## D. Evidence validation

`DecisionStage` 仅接受能在实际规范化 Facts 中找到的 leaf path，例如 `order.status`、`team.status`、`team.target_count`、`team.complete_count`、`team.lock_count`、`team.valid_end_time`、`activity.status`。引用不存在的 `payment.failed` 会产生 `MODEL_EVIDENCE_NOT_AVAILABLE`，决策不会被接受或执行。

## E. Tool allowlist validation

`next_tool` 同时必须属于 `CapabilityState.allowed_tools` 和 `ToolRegistry.allowed_names`。例如 `refund_order` 会产生 `MODEL_TOOL_NOT_ALLOWED`，不会执行。当前只有 `get_order_facts`；即使模型合法请求它来补证据，决策会进入下一控制判断后安全 `HANDOFF`，不会重复执行同一 Facts Tool 或编造补充结果。

## F. Model retry / termination

`ControlState` 新增且独立于 Tool 的字段：

```text
model_call_count
model_retry_count
max_model_retries = 1
```

Schema/invocation failure 最多为首次调用加一次模型修复重试。达到上限后 `HANDOFF`；Tool 的 `tool_call_count`/`retry_count` 不会被用作模型计数。Evidence 或 Tool 权限不合法时立即安全终止，不执行新 Tool。

## G. Trace

TraceEvent 新增 `model_call_count` 和 `model_retry_count`。实际阶段可区分：

- `TOOL_RESULT`
- `MODEL_DECISION`
- `MODEL_VALIDATION_ERROR`

模型 Context 不含 `authenticated_user_id`、认证 Header、完整 Trace、Java 异常、SQL、Redis 或其它内部状态。Trace 同样不记录这些值。

## H. FakeDecisionModel 的作用

Fake 模型用于确定性覆盖合法充分证据、需更多证据、人工转接、非法 Schema、虚构 evidence、未授权 Tool 和重试耗尽。它是测试替身，既不被默认生产 Orchestrator 使用，也不假装为真实智能模型。

## I. 测试结果

命令：

```powershell
conda run -n group-buy-agent python -m pytest -q
```

结果：`25 passed in 0.29s`

测试覆盖 Decision 接受、Evidence 拒绝、allowlist、`refund_order` 拒绝、HANDOFF、Schema 有限重试、模型计数与 Tool 计数分离、脱敏 Context、Trace 阶段，以及既有 Phase 1/1.1/2B 流程。

## J. 尚未接入的真实 LLM

尚未实现真实模型 Adapter、Prompt、API Key、模型网络调用、RAG、Multi-Agent 或新 Java Tool。没有把 Facts 状态翻译为 Python `if/else` 诊断规则。

`PHASE2C_DECISION_SCHEMA = PASS`

`REAL_LLM_INTEGRATION = NOT_TESTED`
