# V2-4：RepeatPolicy 与 Loop Guard

## 1. V1 duplicate 机制与问题

审计确认，V1 在 `agent/orchestrator.py` 的动态 Agent Loop 中，在 Registry 完成参数校验后，把 `tool_name + JSON arguments` 写入 `ContextState.tool_call_history`。只要历史中已存在相同字符串，第二次模型主动请求即以 `DUPLICATE_TOOL_CALL` 转为 `HANDOFF`，且不执行 Tool。

这种绝对禁止虽然能防止死循环，却无法支持只读实时 Facts 的合理重新观察；模型在一次已完成的推理后即使有正当理由刷新同一订单事实，也会被第一次重复调用拦截。

## 2. RepeatPolicy Contract

`tools/base.py` 新增 Tool 自描述契约：

```python
class RepeatPolicy(BaseModel):
    repeatable: bool = False
    max_same_call: int = Field(default=1, ge=1)
```

- `repeatable=False`：每个相同 signature 最多允许一次模型主动 Action，忽略 `max_same_call` 的较大值。
- `repeatable=True`：最多允许 `max_same_call` 次模型主动 Action。
- `AgentTool` Protocol 现在要求每个 Tool 声明 `repeat_policy`；`ToolRegistry.repeat_policy()` 只读取 Tool 元数据，没有任何业务 Tool 名分支。
- `OrderFactsTool` 声明 `RepeatPolicy(repeatable=True, max_same_call=2)`。

RepeatPolicy 没有暴露给 `available_tools`，它是 Runtime/Harness 的确定性安全策略，而不是模型可协商的能力参数。

## 3. Canonical ToolCallSignature 与执行位置

`OrderFactsOrchestrator._tool_call_signature()` 仅使用：

```python
tool_name + json.dumps(
    validated_arguments.model_dump(by_alias=True, mode="json"),
    sort_keys=True,
    separators=(",", ":"),
)
```

它位于 Registry validation 之后、Tool 执行之前；不包含可信身份、Header、Token 或其它认证数据。Loop Guard 的顺序为：

1. 验证 capability、Registry 与参数；
2. 生成 canonical signature；
3. 读取 Tool 自身的 RepeatPolicy；
4. 统计 `tool_call_history` 中该 signature 的模型主动 Action 次数；
5. 超限则不执行 Tool，记录 Trace 并进入受控 `HANDOFF`；未超限才追加 history 并执行。

因此 `tool_call_history` 继续仅保存紧凑的运行控制 signature，不复制 ToolResult 或业务 Facts。

## 4. Retry 与 Repeated Tool Call 的分离

- `tool_call_count`：实际 Tool 执行尝试总次数；每一次 Runtime 调用前递增。
- `retry_count`：首次调用以后，实际发生的额外 Tool 重试次数。
- `tool_call_history`：模型主动的、已获准的 Tool Action signature；一次 Action 在 Runtime retry 前仅追加一次。
- `model_call_count` / `model_retry_count`：模型调用及模型契约重试，与 Tool 计数独立。

因此 timeout 后 Runtime 重试成功会得到 `tool_call_count=2`、`retry_count=1`，但同一 signature history 仍只有一项，未被误判为第二次模型主动重复调用。

## 5. Observation / Evidence

每次成功 Tool 调用都继续追加一个 `Observation`，重复 `get_order_facts` 不会覆盖先前 Observation。`DecisionContext.evidence` 仍从所有 Observation 派生并保留每一条 Evidence。

本阶段将旧 evidence path 兼容转换的候选改为集合去重：多个同名 Tool Observation 产生同一合法 canonical path 时仍是一个无歧义路径；虚构 path 仍被 `validate_evidence()` 拒绝。验证逻辑不会把第二个 Observation 的数据静默写回第一个 Observation。

当前 Evidence Contract 的 path 不带 Observation 版本或时间戳；若未来需要让回答精确引用两次观察中互相冲突的同一路径值，应在独立阶段设计 Observation identity/provenance，而不是在本阶段引入覆盖规则。

## 6. Trace 与终止边界

超过 RepeatPolicy 时新增安全 Trace：

- `stage=TOOL_REPEAT_BLOCKED`
- `tool_name`
- `same_call_count`
- `allowed_same_call_count`
- `error_code=TOOL_REPEAT_LIMIT`

Trace 不记录认证身份、认证 Header、Token、Secret 或 Tool 参数。当前没有单独 `TOOL_RETRY` 事件；重试可通过连续的 `TOOL_CALL` / `TOOL_RESULT`、`tool_call_count` 与 `retry_count` 区分。未为此扩大 Trace 生命周期。

RepeatPolicy 是每个 signature 的局部边界，不替代 `TerminationPolicy` 的全局 `max_iterations`、`max_tool_calls`，也不替代 Tool `max_retries` 或模型 `max_model_retries`。

## 7. 修改文件

- `tools/base.py`：RepeatPolicy 与 AgentTool 契约。
- `tools/java_market_client.py`：OrderFactsTool 的两次同调用策略。
- `tools/registry.py`：通用 RepeatPolicy 读取。
- `agent/orchestrator.py`：canonical signature、Loop Guard 与受控 HANDOFF。
- `observability/trace.py`：Loop Guard 安全字段。
- `decision/validation.py`：多 Observation 同路径兼容转换去重。
- `tests/test_decision_stage.py`、`tests/test_tool_registry.py`：V2-4 覆盖。

未修改 Router、Prompt、Provider、认证、Java 项目、`.env`，也未新增业务 Tool、RAG、Memory、Multi-Agent 或 polling。

## 8. 测试

针对性回归：

```text
52 passed in 0.47s
```

全量测试（项目指定 Conda 环境）：

```text
conda run --no-capture-output -n group-buy-agent python -m pytest -q
83 passed in 0.51s
```

新增/调整断言覆盖：OrderFactsTool 的第一、第二次相同调用允许；第三次执行前阻断并记录 Trace；不可重复 Tool 的第二次阻断；不同已验证参数允许；规范化后字段顺序一致的 signature；timeout Runtime retry 与模型 Action 分离；重复调用的多个 Observation；虚构 Evidence 拒绝。既有测试继续覆盖 max iterations、max tool calls、认证边界、V2-2 自描述 Registry、V2-3 dynamic path 不调用 legacy Router、Session/Handoff/Retry。

## 9. Remaining Issues

- 不支持定时轮询、最小刷新间隔或结果哈希策略；这些不属于本阶段。
- 多次 Observation 的同路径 Evidence 暂无版本化 provenance；未来只有在需解释冲突值时才设计该 Contract。
- 未新增独立 `TOOL_RETRY` Trace 事件，当前以现有事件和受控计数审计。

REPEAT_POLICY_CONTRACT = PASS

CANONICAL_TOOL_SIGNATURE = PASS

RETRY_REPEAT_SEPARATION = PASS

LEGITIMATE_REPEAT_ALLOWED = PASS

DUPLICATE_LOOP_BLOCKED = PASS

MULTI_OBSERVATION_REPEAT = PASS

EVIDENCE_REPEAT_SAFETY = PASS

TERMINATION_REGRESSION = PASS

AUTH_REGRESSION = PASS

FULL_TEST_SUITE = PASS

V2_4_ACCEPTANCE = PASS
