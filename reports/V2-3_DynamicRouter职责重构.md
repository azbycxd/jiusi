# V2-3：Dynamic Agent Path 的 Router 职责重构

## 1. 重构前 Router 的真实职责

V1 `agent/router.py` 会：

- 通过关键词生成 `ORDER_FACTS` 或 `UNKNOWN` Intent；
- 通过正则提取订单号候选；
- 使用 Slot Validator 校验候选；
- 返回规范化 query、Intent、订单号和候选标记。

此前 `OrderFactsOrchestrator.handle_message` 无论是否配置 DecisionStage，都会调用 `route()`，将 `intent` 和 `out_trade_no` 写入 State，并记录 `ROUTED` Trace，之后才进入动态模型循环。

## 2. 为什么与 DecisionStage 存在职责重复

动态模式中的 `DecisionStage + LLM` 已基于 `user_query`、`available_tools`、observations 和 evidence 决定 `ANSWER`、`CALL_TOOL` 或 `HANDOFF`。它不读取 Router 的 Intent，也不使用 Router 提取的订单号调用 Tool。

因此关键词 Router 对动态路径造成了第二个业务语义判断来源：它既不决定 Tool，也不决定 HandOff，却会写入遗留 State 和产生误导性的 `ROUTED` Trace。

## 3. 重构后 Dynamic Path

```text
handle_message
-> load/create AgentState
-> user_query.strip()（确定性输入预处理）
-> INPUT_PREPARED Trace
-> TerminationPolicy
-> DecisionStage / LLM
-> ANSWER / CALL_TOOL / HANDOFF
```

动态主链不调用 `route()`，不读取或写入 `ContextState.intent`、`ContextState.out_trade_no`，也不依赖关键词、正则 SlotExtractor 或历史 Intent 来进入 Agent Loop、选择 Tool 或决定 Handoff。

订单 Tool 参数仍只走：

```text
CallToolDecision.tool_arguments
-> ToolRegistry.validate_arguments
-> OrderFactsArguments
-> OrderFactsTool.run(trusted AgentState, validated arguments)
```

## 4. compatibility_mode 如何处理

`compatibility_mode` 是保留的 V1/Phase 2B 过渡路径，继续使用 legacy `route()`、关键词 Intent 和订单号 Slot 状态，以保留等待订单号、Session 恢复和 Facts retrieval 行为。

该分支明确记录 `ROUTED(action=legacy_route)`；动态路径不再产生该 Trace。V2-2 的 Tool-owned `arguments_from_legacy_state` 仅供这一兼容分支构造已校验参数，正常 LLM Tool 调用不会使用它。

## 5. Router / InputPreprocessor 最终结构

- 未增加新的 InputPreprocessor 类：动态路径只需要 `strip()`，直接在 Orchestrator 中完成，避免形式化抽象。
- `agent/router.py` 保留为 legacy compatibility intent router 与 slot extractor，并在文档字符串中标识其边界。
- 未增加 Multi-Agent Router、classifier LLM、workflow selector 或 planner。

## 6. AgentState intent / slot 字段处理

| 字段/组件 | Dynamic Path | compatibility_mode | 说明 |
| --- | --- | --- | --- |
| `ContextState.intent` | 不读、不写 | 使用 | 保留为 V1 compatibility State。 |
| `ContextState.out_trade_no` | 不读、不写 | 使用 | 保留给 legacy Router/Session slot 恢复。 |
| `agent.slots.validate_out_trade_no` | 通过 `OrderFactsArguments` 校验 Tool 参数 | 校验 Router 候选 | Validator 仍是确定性输入契约，不是动态业务路由。 |
| `DecisionContext` | 使用 `user_query/observations/evidence/available_tools` | 不参与该旧兼容流 | 未重新引入 intent、route 或 slot。 |

没有为本阶段大面积删除 State 字段；它们已被明确标记为 compatibility-only，而不是 V2 动态事实来源。

## 7. ToolArguments 链路是否保持

保持 V2-2 Contract：动态模型的 Tool 参数经 Registry 解析为 `OrderFactsArguments` 并直接传给 `OrderFactsTool.run(state, arguments)`。新增测试证明即使 State 的 `out_trade_no` 为 `None`，模型 `CALL_TOOL` 仍可成功执行；调用后 Orchestrator 不会把该参数写回 State。

## 8. Trace 变化

| 路径 | Trace | 语义 |
| --- | --- | --- |
| Dynamic Agent Path | `INPUT_PREPARED(action=normalize_input)` | 仅表示确定性输入预处理完成。 |
| compatibility_mode | `ROUTED(action=legacy_route)` | 明确表示执行了遗留关键词 Router。 |

测试不只是删除旧断言：动态测试验证无 `ROUTED`、存在 `INPUT_PREPARED`，兼容测试验证保留 legacy `ROUTED`。

## 9. 修改文件

- `agent/orchestrator.py`：按是否有 DecisionStage 分离动态与 compatibility 路径；动态分支不调用 Router。
- `agent/router.py`：明确标记为 legacy compatibility Router。
- `agent/state.py`：明确 `intent` 和 `out_trade_no` 是 compatibility-only routing State。
- `tests/test_decision_stage.py`：新增 Router 隔离、无关键词输入、退款模型 Handoff、State slot 解耦与 Trace 语义断言。

未修改 Prompt、DecisionContext Contract、Observation、Evidence、ToolRegistry、认证、Provider、`.env` 或 Java 项目。

## 10. 新增/修改测试

- 动态路径 monkeypatch legacy `route()` 为失败函数，仍能进入 DecisionStage；
- 动态输入只 strip，Trace 为 `INPUT_PREPARED` 而非 `ROUTED`；
- 不命中旧关键词的“我这个团怎么还没凑齐？”仍由 Fake DecisionModel 选择并调用 Tool；
- 退款问题由 HandoffDecision 进入 Handoff，而非 Router UNKNOWN 提前结束；
- 动态 Tool 参数不依赖、也不回写 `ContextState.out_trade_no`；
- compatibility_mode 仍完成订单事实查询并记录 `ROUTED(action=legacy_route)`；
- V2-1 Observation/Evidence、V2-2 Tool self-description/Registry、认证、Capability、Retry、Termination、Session 与 Handoff 的原有测试均保留。

## 11. 完整 pytest

```text
conda run --no-capture-output -n group-buy-agent python -m pytest -q
77 passed in 0.47s
```

## 12. Remaining Issues

- `compatibility_mode` 及其 legacy Router/slot State 仍是过渡实现；未来移除该模式时可一并删除对应字段和适配器。
- 当前只有一个 Agent，因此没有、也不需要 Multi-Agent Domain Router。
- Refund Tool、RAG、RepeatPolicy、Redis/长期 Memory、Multi-Agent 与 Java 改动均不在本阶段范围内。

```text
DYNAMIC_ROUTER_REMOVED = PASS
LLM_SEMANTIC_DECISION_OWNER = PASS
TOOL_ARGUMENT_PATH_REGRESSION = PASS
COMPATIBILITY_MODE_REGRESSION = PASS
TRACE_SEMANTICS = PASS
OBSERVATION_REGRESSION = PASS
TOOL_REGISTRY_REGRESSION = PASS
AUTH_SAFETY_REGRESSION = PASS
FULL_TEST_SUITE = PASS
V2_3_ACCEPTANCE = PASS
```
