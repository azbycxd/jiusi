# V2-5C：get_joinable_team_facts Python Tool 接入

## 1. 第二 Tool 架构

本阶段新增只读事实 Tool：

```text
AgentState (trusted authenticated_user_id)
  -> OrderFactsOrchestrator
  -> ToolRegistry / CapabilityState
  -> get_joinable_team_facts(activityId)
  -> JoinableTeamFactsTool
  -> JavaMarketClient
  -> POST /api/v1/agent/team/joinable-facts
  -> ToolResult
  -> Observation
  -> DecisionContext
```

模型可控输入仅为 `activityId`。身份不在 Tool 参数、请求 body、ToolCallSignature 或模型可见上下文中，而是由 `AgentState` 构造 `AuthContext` 后交给 `JavaMarketClient` 的既有可信身份注入机制。

## 2. 修改文件

- `tools/arguments.py`：新增严格的 `JoinableTeamFactsArguments`。
- `tools/facts.py`：新增 `JoinableTeamFacts`、`CandidateTeamFacts`、`TeamStatistics` 白名单 Pydantic Contract。
- `tools/base.py`：新增窄接口 `JoinableTeamFactsClient`。
- `tools/java_market_client.py`：在现有 `JavaMarketClient` 中复用 HTTP/envelope 边界，扩展第二个 API 方法与 Tool。
- `agent/state.py`：Capability 增加第二 Tool；通用 Observation 数据路径支持列表索引。
- `agent/orchestrator.py`：默认 Registry 复用一个 `JavaMarketClient` 注册两个 Tool。
- `tests/test_joinable_team_facts.py`：新增 V2-5C 合同、边界、Observation 和动态链路测试。
- `tests/test_state.py`、`tests/test_order_facts_client.py`：更新默认双 Tool 断言。

未修改 Java、Router、SYSTEM_PROMPT、Provider、认证机制、`.env`、数据库或其它业务 Tool。

## 3. Arguments Contract

```python
class JoinableTeamFactsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    activity_id: StrictInt = Field(alias="activityId", gt=0)
```

该 Contract 拒绝空值、`activityId <= 0`、布尔值、字符串数字以及所有额外字段。测试覆盖了 `userId`、`authenticatedUserId`、`outTradeNo`、`token`、`header`、`url`、`sql`、`limit`、`topK` 等字段，均无法进入 Tool。

## 4. JoinableTeamFacts Contract

Java data 经以下严格 Contract（camelCase alias 到 Python snake_case）规范化：

```text
JoinableTeamFacts
  activity_id
  candidate_teams: list[CandidateTeamFacts]
  statistics: TeamStatistics
```

根对象、候选团队和统计对象均 `extra=forbid`；Java 返回未列入 Contract 的敏感字段不会透传到 `ToolResult` 或 Observation。成功数据必须完成 `JoinableTeamFacts.model_validate(data)`，失败则稳定映射为 `TOOL_CONTRACT_MISMATCH`。

## 5. JavaMarketClient 扩展

`JavaMarketClient` 新增：

```text
get_joinable_team_facts(auth, activity_id)
```

它调用 `POST /api/v1/agent/team/joinable-facts`，body 精确为 `{"activityId": <int>}`。HTTP transport、HTTP status、JSON、Java envelope、Java code 与 Pydantic data schema 均复用同一个 `_post_envelope()` 边界。

网络连接错误仍为 `TOOL_CONNECTION_ERROR` 且 `retryable=true`；非法 JSON 为 `TOOL_MALFORMED_JSON`；结构错误或 data 额外字段为 `TOOL_CONTRACT_MISMATCH`；Java `AUTH_REQUIRED` 仍为不可重试的稳定 ToolResult。

## 6. Tool Metadata 与 RepeatPolicy

`JoinableTeamFactsTool` 自描述为：

- `name=get_joinable_team_facts`
- 输入为 `activityId`
- 返回实时可加入候选团队及活动既有团队统计
- `repeat_policy=RepeatPolicy(repeatable=True, max_same_call=2)`

description 明确将 statistics 表述为活动既有团队统计，而非“当前可加入团队数量”。未暴露 RepeatPolicy 给模型，Loop Guard 仍由 Runtime 控制。

## 7. Registry / Capability

默认 `CapabilityState.allowed_tools` 仅允许：

```text
get_order_facts
get_joinable_team_facts
```

默认 Orchestrator 使用同一个 `JavaMarketClient` 注册两个 Tool。`ToolRegistry` 未增加 Tool-name 分支；`available_tools` 自动同时提供两个 metadata/schema。`refund_order` 等未注册 Tool 仍在 validation 与 call 双边被拒绝。

## 8. ToolResult → Observation 与 Evidence

成功 ToolResult 使用规范化 snake_case data 并追加 `Observation(tool_name="get_joinable_team_facts", ...)`；没有新增 `joinable_team_facts`、`team_facts` 或 statistics 专属 State 字段。

Evidence 包含：

- `activity_id`
- `statistics.all_team_count`
- `statistics.all_team_complete_count`
- `statistics.all_team_user_count`
- 非空候选列表的确定性数组路径，例如 `candidate_teams.0.team_id`

`Observation` 的通用数据路径校验最小扩展为支持列表索引，不覆盖其它 Observation。动态 FakeDecisionModel 测试证明第二轮 `DecisionContext` 同时保有两个 Tool metadata，并能读取该 Tool 的 Observation/Evidence；所有 cited evidence 都经既有 Evidence validation。

## 9. 空候选语义

`candidateTeams=[]` 是正常、成功的业务事实：`ToolResult.success=True`、Observation 正常生成、没有 `NOT_FOUND` / `HANDOFF` / Tool Error。statistics 仍完整保留，且没有把 `allTeamCount` 等字段错误重命名为 joinable/available/remaining 团队数。

## 10. Auth / Privacy

`JoinableTeamFactsTool.run(state, arguments)` 从可信 `state.authenticated_user_id` 构建 `AuthContext`。缺失身份在 HTTP 前稳定返回 `AUTH_REQUIRED`；模型 arguments 不能携带身份、header、token、SQL 或 URL。真实请求和 Trace 均未输出认证 Header、身份值、Token 或 API Key。

## 11. 测试

新增覆盖包括：严格参数与越权字段、成功 camelCase → snake_case 解析、候选团队 Evidence、空候选正常成功、malformed JSON、严格 schema mismatch、额外隐私字段隔离、网络错误、Java AUTH_REQUIRED、可信身份注入、Tool 无副作用、Tool metadata、通用 Registry/Capability、未知 Tool 拒绝、完整动态 `CALL_TOOL → Observation → ANSWER` 链路。

既有测试继续覆盖 V2-1 Observation、V2-2 Registry、V2-3 dynamic path 不调用 Router、V2-4 RepeatPolicy/Loop Guard、Auth、Retry、Termination、Session 与 HANDOFF。

完整 pytest：

```text
conda run --no-capture-output -n group-buy-agent python -m pytest -q
103 passed in 0.40s
```

## 12. 真实 Java Smoke

使用项目配置的真实 Java 服务和安全测试身份，从 `AgentState → JoinableTeamFactsTool → JavaMarketClient → HTTP → ToolResult → Observation` 执行：

```text
activityId=100123
success=true
source=java_market
activity_id=100123
candidate_team_count=0
statistics_present=true
observation_created=true
```

本次真实返回的空候选列表按正常成功语义处理；未修改数据库或制造候选数据。

## 13. Remaining Issues

- 本阶段未做 V2-5D Multi-Tool 真实模型行为验证。
- 按要求未修改 SYSTEM_PROMPT；审计发现其中已有对 `activityId` 的通用禁止表述。第二 Tool metadata 已会进入 DecisionContext，但真实模型对该输入的选择行为应在 V2-5D 以独立 Prompt/安全策略审计处理，不能在本阶段用规则硬编码绕过。
- 未新增轮询、定时器、scheduler、写型 Tool、RAG 或长期 Memory。

JOINABLE_TOOL_CONTRACT = PASS

JOINABLE_ARGUMENT_SECURITY = PASS

JAVA_CLIENT_INTEGRATION = PASS

REGISTRY_MULTI_TOOL = PASS

CAPABILITY_MULTI_TOOL = PASS

JOINABLE_OBSERVATION = PASS

JOINABLE_EVIDENCE = PASS

EMPTY_CANDIDATE_SEMANTICS = PASS

AUTH_PRIVACY_REGRESSION = PASS

REPEAT_POLICY_REGRESSION = PASS

DYNAMIC_AGENT_REGRESSION = PASS

PYTHON_FULL_TEST_SUITE = PASS

LIVE_JAVA_TOOL_SMOKE = PASS

V2_5C_ACCEPTANCE = PASS
