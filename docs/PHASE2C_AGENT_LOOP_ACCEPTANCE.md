# Phase 2C-1.1 Dynamic Agent Loop 验收

## A. 重构前后的控制流

旧的 Facts-only 过渡路径是确定性的 `Router → get_order_facts → FACTS_RETRIEVED`。它没有动态 Tool 选择能力。

当前 Agent Loop 的活动控制流为：

```text
User Query
  → Router（仅提取规范化槽位）
  → DecisionModel
  → AgentDecision
  → CALL_TOOL validation
  → ToolRegistry / get_order_facts
  → ToolResult / Facts / evidence observation
  → DecisionModel（下一轮）
  → ANSWER / HANDOFF
```

未注入 `DecisionModel` 时，构造 `OrderFactsOrchestrator` 必须显式传入 `compatibility_mode=True`，才可保留临时 Phase 2B Facts-only 行为。这不是动态 Loop 的隐式回退。

## B. AgentDecision Contract

`AgentDecision` 是严格 Pydantic Schema（`extra=forbid`），只允许：

```text
action: CALL_TOOL | ANSWER | HANDOFF
tool_name: string | null
tool_arguments: object | null
final_answer: string | null
used_evidence: string[]
missing_information: string[]
```

`CALL_TOOL` 必须带 Tool 名称和参数且不能夹带答案；`ANSWER` 必须带答案且不能请求 Tool；`HANDOFF` 不能请求 Tool 或声称已有最终答案。Schema 不包含 reasoning steps、thoughts 或 chain-of-thought。

## C. Tool 调用验证链

模型提出 `CALL_TOOL` 后，Orchestrator 依次执行：Capability allowlist → Registry allowlist → 参数 Schema/Slot Validator → 重复调用检查 → TerminationPolicy → Tool 执行。当前唯一注册且允许的 Tool 是 `get_order_facts`。

工具参数严格只允许：

```json
{"outTradeNo": "..."}
```

`userId`、`authenticated_user_id`、`header`、`base_url`、`teamId`、`activityId`、`sql` 和任何额外字段都会被拒绝，不会触发 Tool 调用。

## D. 可信身份边界

模型 Context 没有 `authenticated_user_id`、认证 Header、Token、SQL、Java 异常或 Trace。可信身份仅保存在 `AgentState`，并由 `OrderFactsTool` / `JavaMarketClient` 在执行阶段按既有 Contract 注入。模型永远不能构造身份参数。

## E. Observation 与状态写回

每次成功 Tool 调用都会将 `ToolResult`、精简 evidence、规范化 `OrderFacts` 写入 `ContextState`，随后才请求下一轮 `DecisionModel`。同一 `tool_name + normalized arguments` 会记录到 `tool_call_history`；重复调用会安全转人工而不重复执行。

`ANSWER.used_evidence` 的每一条均须是当前真实 Facts 中存在的 leaf path。泛化回答可使用空 evidence；伪造的 `payment.failed` 等路径会产生 `MODEL_EVIDENCE_NOT_AVAILABLE` 并转人工。

## F. 终止、重试与失败隔离

- Tool 调用由 `max_tool_calls`、`max_retries` 与 `max_iterations` 限制；`retry_count` 只统计首次 Tool 失败后的额外重试。
- 模型调用使用独立的 `model_call_count`、`model_retry_count`、`max_model_retries`；Schema 或调用错误最多初始调用加一次修复重试。
- 不允许的 Tool、非法参数、伪造 evidence、重复调用或模型重试耗尽均不会无限循环，进入 `HANDOFF`。
- Tool timeout 的重试不会消耗模型重试计数，反之亦然。

## G. ContextState 与责任边界

`ContextState` 现在保存 `order_facts`、`evidence`、`tool_results`、`model_decision` 和 `tool_call_history`。Router 只产出 `RoutingResult`；DecisionStage 只建模/校验模型输入输出；Tool 只返回 `ToolResult`；只有 Orchestrator 与 TerminationPolicy 变更控制 State。

## H. Trace

每条结构化 Trace 均有 `trace_id`、`session_id`、`stage`、`action`、`duration_ms`、Tool 成功/错误信息以及 Tool/Model 的独立计数。动态 Loop 可观察到至少：

```text
ROUTED → MODEL_DECISION(CALL_TOOL) → TOOL_CALL(get_order_facts)
→ TOOL_RESULT → MODEL_DECISION(ANSWER) → FINISHED
```

Trace 不记录完整认证 Header、Token、身份凭证或 Java stack trace。

## I. 实际测试场景

- 多轮 `CALL_TOOL(get_order_facts)` → observation → `ANSWER`，确认第二轮模型可见真实 Facts/evidence。
- 首轮 `ANSWER`，无需 Tool 或 Facts。
- 不允许的 `refund_order`、全部额外/敏感参数、重复 Tool 调用均不执行 Tool。
- `HANDOFF` 不执行 Tool；伪造 evidence 被拒绝。
- Tool timeout 的有限 Tool 重试与模型重试计数隔离。
- 非法模型 Schema 的有限修复重试及耗尽后 HANDOFF。
- 未注入模型必须显式选择 Facts-only compatibility path。
- 原 Phase 1 / 1.1 / 2B Client Harness 测试继续通过。

## J. 测试结果

执行环境：Conda `group-buy-agent`，Python 3.11。

```powershell
conda run -n group-buy-agent python -m pytest -q
```

结果：`36 passed`。

## K. 兼容性变化

`OrderFactsOrchestrator()` 不再静默启动 Facts-only 流程。没有 `DecisionModel` 的历史调用方必须明确传入 `compatibility_mode=True`；已更新 FastAPI 临时入口、既有 Harness、Eval 和 Phase 2B live script。注入 `DecisionModel` 的调用进入动态 Loop。

## L. 明确未做的内容

没有真实 LLM/Prompt/API Key/网络调用，没有 RAG、Multi-Agent、新 Java Tool、Java 项目访问、Python 诊断规则或基于 Facts 的 `if/else` 诊断。真实 LLM 的稳定输出、超时、成本、Prompt 注入对抗、长期上下文与生产观测仍待后续 Phase 验证。

## M. 结论

`PHASE2C_AGENT_LOOP = PASS`

`DYNAMIC_TOOL_SELECTION_ARCHITECTURE = PASS`

`REAL_LLM_INTEGRATION = NOT_TESTED`
