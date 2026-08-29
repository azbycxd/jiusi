# V2-2：Tool 自描述与 ToolRegistry 通用化

## 1. 重构前 Tool / Registry 结构

重构前，`OrderFactsTool` 仅声明 `name` 并从 `AgentState.out_trade_no` 读取业务参数；`ToolRegistry` 则保存另一份 `get_order_facts` 专属 description、JSON Schema 和参数校验分支。动态 Orchestrator 在拿到模型参数后把 `outTradeNo` 写入 State，再调用无参数的 Tool。

```text
LLM tool_arguments
-> Orchestrator 写入 ContextState.out_trade_no
-> ToolRegistry 的 get_order_facts 专属校验
-> OrderFactsTool.run(state)
```

这使 Tool 的身份、描述、参数契约和执行参数来源分散在多个模块。

## 2. 重构后结构

```text
OrderFactsTool metadata / arguments_schema / run(state, arguments)
-> ToolRegistry（register / get / describe / validate / call）
-> validated OrderFactsArguments
-> OrderFactsTool.run(trusted AgentState, validated arguments)
-> ToolResult -> Observation -> DecisionContext -> LLM
```

Registry 不再包含任一业务 Tool 的 name、description、schema 或参数分支。动态 Orchestrator 只保存经过 Registry 校验的参数对象用于调用签名、重复调用保护和 `registry.call`；不再将模型传入的订单号写回 State。

## 3. 修改文件

- `tools/base.py`：定义统一的 `AgentTool` Protocol。
- `tools/arguments.py`：将 `OrderFactsArguments` 设为强类型 Pydantic Contract，并将 slot 规范化放入字段校验。
- `tools/java_market_client.py`：`OrderFactsTool` 自声明 Metadata，并改为 `run(state, arguments)`。
- `tools/registry.py`：改为通用注册、Metadata 描述、模型参数校验与调用分派。
- `agent/orchestrator.py`：动态调用链传递已校验 `BaseModel` 参数，不再写入订单号 State 槽。
- `tests/test_tool_registry.py`：新增 Tool 自描述、参数安全、通用 Registry 与 State 解耦覆盖。
- `tests/test_decision_stage.py`、`tests/test_order_facts_client.py`、`tests/test_decision_normalization.py`：迁移新调用接口并保留已有行为断言。

## 4. AgentTool Contract

```text
AgentTool
  name: str
  description: str
  arguments_schema: type[BaseModel]
  run(state: AgentState, arguments: BaseModel) -> ToolResult
```

该 Contract 的 `state` 只提供受信任 Agent Runtime 上下文（尤其是认证身份）；每次业务 Tool Call 的模型可控参数由独立的、已校验的 `arguments` 对象提供。

## 5. OrderFactsTool Metadata

`OrderFactsTool` 现在自行声明：

- `name = get_order_facts`；
- 订单、拼团、活动和引用事实查询的 description；
- `arguments_schema = OrderFactsArguments`；
- `run(state, arguments)`。

`ToolRegistry.available_tools` 自动调用 `tool.arguments_schema.model_json_schema(by_alias=True)`，因此 DecisionContext 和真实模型载荷继续使用的参数 Schema 直接来自 Tool 本身。`outTradeNo` 仍是唯一必填字符串参数，且 Schema 的 `additionalProperties=false`。

## 6. ToolArguments validation 链路

```text
LLM CALL_TOOL.tool_arguments
-> ToolRegistry.validate_arguments
-> OrderFactsArguments.model_validate
-> StrictStr + validate_out_trade_no
-> validated OrderFactsArguments
-> ToolRegistry.call
-> OrderFactsTool.run(state, arguments)
```

空值、非字符串、非法字符、超长值和未知字段均会被拒绝。`userId`、`authenticatedUserId`、Header 等额外字段因 `extra=forbid` 被拒绝。可信 `authenticated_user_id` 仍只来自 AgentState，并由 Tool 构造 AuthContext 传给 Java Client。

## 7. Registry 通用化结果

Registry 只负责：

1. `register`（重复名称拒绝）；
2. `get`；
3. 从 Tool Metadata 自动生成 `available_tools`；
4. 调用各 Tool 自己的 arguments_schema；
5. 在 Capability 与注册表双重允许后分派 `run(state, validated_arguments)`。

`ToolRegistry` 中已不存在 `get_order_facts`、description 字典或针对具体 Tool 的 Schema/参数 `if/else`。一个测试专用的第二自描述 Tool 也能使用同一 Registry 完成 Schema 生成、参数校验和调用，未新增任何业务能力。

## 8. Orchestrator 的 Tool 专属逻辑

动态 Agent Loop 中，Orchestrator 不包含 `get_order_facts` 名称、`outTradeNo` 字段或 `OrderFactsArguments` Schema 细节。它只检查 Capability、调用 Registry、处理 ToolResult、生成 Observation，并执行 Retry/Termination。

为保留 V1 的显式 `compatibility_mode`，OrderFactsTool 提供一个仅限旧兼容流的 `arguments_from_legacy_state` 适配器；通用 Registry 查找唯一适配器后返回 `(tool_name, validated_arguments)`。这使 Orchestrator 不再构造或解析订单 Tool 参数。正常 LLM 动态路径不使用该适配器。

## 9. Auth / Capability 是否保持

保持三层边界：

```text
AgentState.capability allowlist
+ ToolRegistry registered tools
+ Tool arguments_schema validation
```

不存在的 `refund_order` 在参数校验和调用边界均被拒绝。模型无法通过参数提供身份、认证 Header、SQL 或 URL；OrderFactsTool 从可信 State 获取身份。 

## 10. Observation / Evidence 是否保持

V2-1 链路未改变：

```text
ToolResult(success)
-> Observation(tool_name, normalized data, evidence)
-> ContextState.observations
-> DecisionContext(observations, derived evidence)
-> Evidence Validation
```

`ContextState.order_facts`、独立 `ContextState.evidence` 和 `DecisionContext.facts` 均未恢复。Evidence 仍使用 `<tool_name>.<data_path>`。

## 11. 新增 / 修改测试

- OrderFactsTool 自描述 `name`、`description`、`arguments_schema`；
- available_tools 自动等同于 Tool Metadata 与 Pydantic JSON Schema；
- Registry 源码不含 `get_order_facts` 业务分支；
- 合法订单参数可校验并规范化；
- 空值、错误类型、`userId`、`authenticatedUserId`、Header 均被拒绝；
- 未注册 `refund_order` 在校验与调用边界均拒绝；
- Tool 使用 validated arguments，可信身份来自 State，且 State 无订单号时可成功执行；
- 第二测试 Tool 验证 Registry 对多自描述 Tool 的基础设施通用性；
- CALL_TOOL -> Tool -> Observation -> ANSWER、Evidence Validation、认证、Capability、Retry、Termination、Session、HANDOFF 和真实模型载荷相关的既有回归均通过。

## 12. 完整 pytest

```text
conda run --no-capture-output -n group-buy-agent python -m pytest -q
74 passed in 0.41s
```

## 13. Remaining Issues

- 当前仍只有一个真实业务 Tool；测试用第二 Tool 只用于证明 Registry 通用性。
- RepeatPolicy、轮询、RAG、退款 Tool、Redis/长期 Memory、Multi-Agent 和 Java 项目修改不在本阶段范围内。
- `compatibility_mode` 仍是过渡路径；其 State 到参数适配已收拢到 Tool 自身，未来移除该模式时可一并删除适配器。

```text
TOOL_SELF_DESCRIPTION = PASS
TOOL_ARGUMENT_CONTRACT = PASS
TOOL_ARGUMENT_STATE_DECOUPLING = PASS
REGISTRY_GENERICIZATION = PASS
AVAILABLE_TOOLS_AUTO_GENERATION = PASS
AUTH_BOUNDARY_REGRESSION = PASS
OBSERVATION_REGRESSION = PASS
V1_DYNAMIC_LOOP_REGRESSION = PASS
FULL_TEST_SUITE = PASS
V2_2_ACCEPTANCE = PASS
```
