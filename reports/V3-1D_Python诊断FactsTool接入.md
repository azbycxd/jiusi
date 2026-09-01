# V3-1D：Python 诊断 Facts Tool 接入

## 1. Git / V2 frozen baseline

- V2 frozen baseline branch: `V2`
- V2 baseline commit: `e7dba64c6fe3f3ca1f21191688405bddc0f9352b` (`V2-10`)
- V3 working branch: `V3`
- V3 开始时的 HEAD 与 V2 baseline 相同；本次未改写 V2 历史，也没有直接在 `V2` 分支开发。

## 2. 修改文件

- `agent/state.py`：将两个新 Tool 加入显式 Capability allowlist。
- `agent/orchestrator.py`：在默认 generic ToolRegistry 中注册两个新 Tool。
- `tools/arguments.py`：新增两个严格 `activityId` 参数模型。
- `tools/base.py`：新增两个最小 Java client Protocol。
- `tools/facts.py`：新增 Activity 与 Eligibility 的严格 Pydantic 事实契约。
- `tools/java_market_client.py`：新增 Java HTTP client methods、ToolResult 映射及两个 AgentTool。
- 既有 V2 测试：把“默认 3 个能力”的断言更新为 V3 的 5 项显式 allowlist；原三项的名字、顺序、参数 schema 和实现未改变。
- `tests/test_activity_eligibility_facts.py`：新增 V3 Tool contract 与回归测试。

## 3. Java client

`JavaMarketClient` 增加：

- `get_activity_facts(auth, activity_id)` → `POST /api/v1/agent/activity/facts`
- `get_user_eligibility_facts(auth, activity_id)` → `POST /api/v1/agent/activity/eligibility-facts`

两者都复用现有 HTTP status → JSON → envelope code → Pydantic contract 的顺序，不把 Java response 作为任意 dict 透传。`AUTH_REQUIRED`、`INVALID_ARGUMENT`、`ACTIVITY_NOT_FOUND` 为非 retryable 业务失败；`INTERNAL_SERVICE_ERROR` 保持现有只读查询的有限 retry 语义；transport timeout/connection 仍映射为稳定 retryable Tool failure。

## 4. Activity Facts Tool

`get_activity_facts` 的唯一模型参数为严格正整数 `activityId`，`extra=forbid`。它只读取活动级事实：状态、开始/结束时间、tag scope、用户领取限制、评估时间与有效期判断。它不产生 diagnosis、原因或 recommendation。

Java camelCase 由 Pydantic 归一为 snake_case；成功 ToolResult 进入 `Observation` 后的典型 Evidence path 为：

```text
get_activity_facts.activity.status
get_activity_facts.activity.within_valid_time
```

## 5. Eligibility Facts Tool

`get_user_eligibility_facts` 同样只接受严格正整数 `activityId`。当前可信用户来自 `AgentState.authenticated_user_id`，由 Tool 在运行时构造 `AuthContext` 后交给 Java client；`userId`、token、Header、authorization 和 base URL 都不在 Tool schema 中。

它只返回当前可信用户在该活动下的标签门禁、参与次数、降级/切量与 release-range 事实，不复制 Activity 的状态或时间字段，也不推导 `eligible`、`tagMatched`、reasonCode 或 diagnosis。

典型 canonical Evidence path：

```text
get_user_eligibility_facts.tag_crowd_data_available
get_user_eligibility_facts.tag_gate_passed
get_user_eligibility_facts.tag_participation_allowed
get_user_eligibility_facts.participation_limit_reached
```

## 6. Pydantic contracts 与 false/null 边界

Activity contract 验证 `activity.activityId`、`status`、`startTime`、`endTime`、`tagScope`、`userTakeLimit`、`evaluatedAt`、`withinValidTime`。Eligibility contract 验证 V3-1C 所列的全部 11 个字段，且 `extra=forbid`。

已验证：

- `tagCrowdDataAvailable=false` 与 `tagGatePassed=true` 合法且原样保留；Python 不把它重写为 `tagMatched` 或自行推导 gate 结果。
- 所有重要 boolean `false` 都会成为有效 Evidence，未因 truthiness 被丢弃。
- 两个 contract 的 `user_take_limit=null` 保持 `None`，不会转为 `0`、不会 schema failure，也不会破坏 Observation；由于现有选择性 Evidence 机制，null 字段不生成 terminal Evidence。

## 7. Registry、RepeatPolicy 与 Model 可见性

Registry 没有按 Tool name 的特殊分支；每个 Tool 自描述 name、description、arguments schema、run 与 RepeatPolicy。默认 Registry 恰好为：

1. `get_order_facts`
2. `get_joinable_team_facts`
3. `search_group_buy_rules`
4. `get_activity_facts`
5. `get_user_eligibility_facts`

新 Facts Tool 使用 `RepeatPolicy(repeatable=false, max_same_call=1)`；相同 canonical model call 只允许首次调用。底层 Java connection failure 仍由既有 runtime retry policy 有限尝试一次额外 retry。DecisionContext 自动收到 5 项 Tool metadata；未在 Prompt 中添加固定“Activity → Eligibility”工作流。

## 8. Observation / Evidence / trusted identity

两项成功 ToolResult 都由现有 Orchestrator 统一写入 Context 的 `tool_results` 与 `observations`，并由 `Observation.from_successful_tool_result` 增加 Tool-name canonical prefix。Tool 不原地修改 AgentState。

测试验证 Tools 的模型可控 schema 只有 `activityId`，运行方法签名没有 user ID，空可信 identity 在 Java client 调用前得到 `AUTH_REQUIRED`。没有把可信身份写入测试报告、Trace 或 Evidence。

## 9. 测试

新增测试覆盖：

- 两个 Tool 的 valid response、严格参数、extra `userId` 等敏感字段拒绝；
- Activity `withinValidTime=false` Evidence、`userTakeLimit=null`；
- Eligibility 所有要求的 true/false 组合、fallback 组合、`userTakeLimit=null`、降级和 release-range false；
- `ACTIVITY_NOT_FOUND`、`AUTH_REQUIRED`、`INVALID_ARGUMENT`、`INTERNAL_SERVICE_ERROR` 映射；
- malformed JSON、connection failure、response schema mismatch / extra response field；
- trusted identity 注入、无 State side effect、有限 runtime retry；
- Registry size=5、两个新 arguments schema 与 generic ToolRegistry。

完整测试结果：`182 passed, 1 warning`。warning 为现有 FastAPI/Starlette third-party deprecation warning。

## 10. Java real preflight

只通过运行中的 Java HTTP 服务和新 `JavaMarketClient` 进行了 read-only preflight，公开测试 activityId 为 `100123`：

- Activity Facts: success, source=`java_market`，必需 Python contract 字段齐全；
- Eligibility Facts: success, source=`java_market`，必需 Python contract 字段齐全。

没有记录 trusted identity 值，未读取或修改 Java 源码。

## 11. 未进入 DiagnosisState 的原因与已知限制

本阶段目标只是扩展 generic Facts Tool 链路：Java HTTP → Pydantic → ToolResult → Observation → Evidence → Registry。现有 Agent Loop、Decision Contract、Evidence Guard、RepeatPolicy 总体机制、Session / Auth boundary、RAG、HTTP Contract 与 Eval baseline 均未重构。

没有新增 `DiagnosisState`、Planner、Router、Workflow、REQUEST_INPUT、Reflection 或 Multi-Agent，也未对 `SYSTEM_PROMPT` 加入业务诊断顺序。真实模型如何动态组合 Activity、Eligibility、其他 Facts 和规则知识将留给 V3-1E 验证。

```text
V2_BASELINE_IDENTIFIED = PASS
V3_WORKING_BRANCH = V3

V2_EXISTING_CONTRACT_CHANGED = NO

ACTIVITY_TOOL_IMPLEMENTED = PASS
ELIGIBILITY_TOOL_IMPLEMENTED = PASS

TOOL_REGISTRY_GENERIC = PASS
TOOL_REGISTRY_SIZE = 5

MODEL_CONTROLLED_IDENTITY = NO

ACTIVITY_RESPONSE_VALIDATED = PASS
ELIGIBILITY_RESPONSE_VALIDATED = PASS

TAG_FALLBACK_COMBINATION_SUPPORTED = PASS

FALSE_VALUE_EVIDENCE = PASS
NULL_VALUE_CONTRACT = PASS

JAVA_ERROR_MAPPING = PASS
REPEAT_POLICY = PASS

JAVA_HTTP_PREFLIGHT = PASS

PYTHON_FULL_TESTS = 182 passed, 1 warning
PYTHON_FULL_TESTS_PASS = PASS

DIAGNOSIS_STATE_ADDED = NO
PROMPT_WORKFLOW_ADDED = NO

READY_FOR_V3_1E = YES
V3_1D_ACCEPTANCE = PASS
```
