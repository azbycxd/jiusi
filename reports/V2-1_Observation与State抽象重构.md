# V2-1：Observation 与 State 抽象重构

## 1. 重构前结构

V1 的成功工具结果在 Orchestrator 中被拆分为两份订单事实状态：

```text
ToolResult
  -> ContextState.order_facts
  -> ContextState.evidence
  -> DecisionContext(facts, evidence)
```

该结构依赖单一 `get_order_facts` Tool。`order_facts` 和独立 `evidence` 都是可变 State 字段，未来增加第二个 Tool 时容易产生命名冲突和不同步风险。

## 2. 重构后结构

```text
ToolResult（执行成功/失败的完整业务结果）
  -> 成功时：Observation(tool_name, data, evidence)
  -> ContextState.observations
  -> DecisionContext(observations, derived evidence, available_tools)
  -> DecisionStage -> LLM Decision
```

`ContextState` 现在以 `observations` 作为后续模型决策的唯一业务事实主来源；`tool_results` 仍完整保留每一次执行的成功、错误码、可重试性和来源。失败的 ToolResult 不生成 Observation。

## 3. 修改文件

- `agent/state.py`：新增 `Observation`；移除活动 `order_facts` 与独立 `evidence` State 字段；新增 Observation 与数据/Evidence 一致性校验。
- `agent/orchestrator.py`：成功 ToolResult 改为写入 Observation，并由 observations 构建下一轮 DecisionContext。
- `tools/java_market_client.py`：保持 `OrderFacts` Pydantic 校验，ToolResult.data 改为直接保存规范化 OrderFacts 数据；Evidence 字段路径统一为数据的 snake_case 路径。
- `decision/schemas.py`：DecisionContext 改为接收 `observations`，`evidence` 变成从 Observation 聚合得到的只读属性。
- `decision/stage.py`、`decision/validation.py`：以 Observation 构建上下文、验证带 Tool 前缀的 Evidence，并保留确定性的旧路径兼容。
- `decision/real_llm.py`：模型可见载荷从 `facts` 改为 `observations`，仍只发送经过筛选的 DecisionContext。
- `scripts/run_phase2b_live_integration.py`、`scripts/run_phase2c_2_1_live_integration.py`、`tests/acceptance_runner.py`：输出迁移为 observations。
- `tests/test_state.py`、`tests/test_decision_stage.py`、`tests/test_order_facts_client.py`、`tests/test_real_llm.py`、`tests/test_decision_normalization.py`：迁移 V1 断言并补充 V2-1 覆盖。

## 4. Observation Contract

```text
Observation
  tool_name: 产生观察结果的允许 Tool 名称
  data:      经过具体 Tool Contract 校验后的规范化业务数据
  evidence:  支持后续 ANSWER 的结构化 Evidence
```

现有 Java 链路仍严格为：

```text
Java HTTP Response
  -> OrderFacts Pydantic Contract
  -> ToolResult(data=normalized OrderFacts)
  -> Observation(get_order_facts, data, evidence)
```

Observation 的 Evidence 必须以 `<tool_name>.<data_path>` 命名，并同时满足：路径属于自身 `data`，且 Evidence 值与该规范化数据一致。例如：

```text
get_order_facts.order.status
get_order_facts.team.status
get_order_facts.team.target_count
get_order_facts.team.complete_count
```

因此本次通用化没有把 Java 任意字典直接交给模型，也没有把 ToolResult 和 Observation 合并。

## 5. ToolResult → Observation → DecisionContext 实际链路

1. Harness 按 allowlist 调用 `get_order_facts`。
2. `OrderFactsTool` 返回统一 ToolResult；Tool 不修改 AgentState。
3. Orchestrator 总是保存 ToolResult；仅当 `success=true` 时创建 Observation。
4. Observation 写入 `ContextState.observations`，引用 ID 仍由同一 Observation.data 提取。
5. 下一轮 `DecisionStage.build_context` 只接收 `user_query + observations + available_tools`。
6. `RealLLMDecisionModel` 只收到 DecisionContext 的 observations 与派生 evidence，不会收到完整 AgentState、可信身份、Header、Trace 或异常。

## 6. Evidence 聚合与验证

`DecisionContext.evidence` 是对当前 observations 中 Evidence 的聚合属性，不在 ContextState 中另存副本。验证逻辑只接受 Observation 中已有的完整 Tool 前缀路径。

为兼容 V1/Provider 的旧输出，`facts.order.status` 或裸 `order.status` 仅当恰好一个 Observation 拥有匹配 Evidence 时，确定性地迁移为 `get_order_facts.order.status`。没有匹配或有多个匹配时不猜测，随后以 `MODEL_EVIDENCE_NOT_AVAILABLE` 拒绝。虚构 Evidence 的严格拒绝逻辑未放宽。

## 7. 旧字段与兼容性

活动运行路径中已不存在：

- `ContextState.order_facts` / `AgentState.order_facts`；
- 独立的 `ContextState.evidence` / `AgentState.evidence`；
- `DecisionContext.facts`。

没有保留这些字段作为新的事实来源。唯一兼容行为是 Decision Validation 对旧 Evidence 路径的无歧义规范化，目的是平滑兼容当前未做大规模 Prompt 调整的 Provider 输出；它不复制或恢复 V1 State 字段。

内部兼容性变化：成功 `get_order_facts` 的 `ToolResult.data` 从 `{"facts": ...}` 改为直接规范化 Facts。当前仓库内测试、验收脚本和运行路径已同步迁移；不存在面向外部 HTTP 的 ToolResult 数据接口。

## 8. 新增与调整测试

- 成功 `get_order_facts` 仅生成一个 `get_order_facts` Observation，且数据来自规范化 Facts；
- Observation Evidence 的 Tool 前缀、路径和实际值一致；
- 失败 ToolResult、超时/重试路径不生成 Observation；
- DecisionContext 首轮为空 observations，下一轮来自 Observation，不再读取 order_facts；
- 两个构造 Observation 可同时进入 Context，并正确聚合 Evidence；
- 虚构 Evidence 继续被拒绝；
- `facts.` 旧前缀在唯一 Observation 下能确定性迁移；
- V1 动态 CALL_TOOL → Tool → ANSWER、身份边界、无效参数、模型/工具重试、Termination、Session 和 HANDOFF 回归测试保留并通过。

## 9. 测试结果

针对性测试：

```text
conda run --no-capture-output -n group-buy-agent python -m pytest -q \
  tests/test_state.py tests/test_decision_stage.py tests/test_order_facts_client.py \
  tests/test_real_llm.py tests/test_decision_normalization.py
59 passed in 0.66s
```

完整回归：

```text
conda run --no-capture-output -n group-buy-agent python -m pytest -q
62 passed in 0.67s
```

`--no-capture-output` 仅用于规避 Windows Conda 对包含中文失败输出的 GBK 回收编码问题；仍使用指定的 `group-buy-agent` Conda 环境。

## 10. Remaining Issues

- 当前只有 `get_order_facts` 真实 Tool；多 Observation 支持已由 Contract 与测试验证，尚未新增业务 Tool。
- ToolRegistry 的 Tool metadata/参数分派仍是 V1 显式 allowlist 结构，本阶段按范围未重构。
- Redis Session、长期 Memory、RAG、退款能力、Multi-Agent、Prompt 大规模调优均未实施。
- Java、认证边界、真实 Provider 配置和 `.env` 未修改；本阶段未执行新的真实 LLM/Java 联调。

```text
OBSERVATION_CONTRACT = PASS
STATE_OBSERVATION_MIGRATION = PASS
DECISION_CONTEXT_MIGRATION = PASS
MULTI_OBSERVATION_SUPPORT = PASS
EVIDENCE_VALIDATION = PASS
V1_DYNAMIC_LOOP_REGRESSION = PASS
V1_SAFETY_REGRESSION = PASS
V2_1_ACCEPTANCE = PASS
```
