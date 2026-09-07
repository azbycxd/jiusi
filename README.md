# Group Buy Agent

Evidence-Grounded Business Diagnosis Agent：面向拼团业务的独立 Python Agent 服务。它以可信 Java 业务事实与规则知识为依据完成诊断，不直连数据库、不执行写操作，也不把身份控制交给模型。

## Architecture

`Client → FastAPI /v1/chat → Orchestrator + AgentState → DecisionContext → RealLLMDecisionModel → validated Decision → ToolRegistry → AgentTool → Java / RAG → Observation + Evidence → ANSWER / REQUEST_INPUT / HANDOFF`

`AgentState` 保存控制状态、当前会话和 Observation；`DecisionContext` 只向模型暴露当前问题、相关 Observation/Evidence、诊断进度与显式 Tool 描述。可信身份、认证 Header、内部异常、Trace 与服务配置不会进入模型上下文。

## Agent loop

模型只可提出严格的 `CALL_TOOL`、`ANSWER`、`REQUEST_INPUT` 或 `HANDOFF`。编排器验证 Tool 名称、参数、Evidence 引用、重复调用与资源上限，再执行 Tool；没有固定 Workflow 或关键词 Router。`REQUEST_INPUT → WAITING_INPUT` 允许同身份同 Session 补齐实体参数后恢复原任务；能力不足或不可靠时使用 `HANDOFF`。

## Tools and RAG

当前显式 allowlist 有 5 个只读 Tools：`get_order_facts`、`get_joinable_team_facts`、`get_activity_facts`、`get_user_eligibility_facts`、`search_group_buy_rules`。

Java Facts 提供实时业务事实；RAG 仅检索规则 Catalog，不承担订单、活动或资格等实时事实。Java 返回 Facts，Python 模型基于 Evidence 作出自然语言解释，Java 不提供 LLM 诊断结论。

## Diagnosis and grounding

开放式“为什么不能参与”诊断会启用最小 `DiagnosisProgress(goal, required_dimensions, checked_dimensions, remaining_dimensions)`。它只控制当前诊断是否还有直接相关的事实维度待验证，不是 Planner、长期 Memory 或 hypothesis tree。最终 ANSWER 的 `used_evidence` 必须映射到实际 Observation；Tool 参数 provenance 与 Evidence provenance 分开校验。

## Security and recovery

- 模型只能控制 Tool Schema 中的业务参数；trusted identity 来自 HTTP 认证上下文/AgentState。
- 无 shell、SQL、Redis、generic HTTP 或自动注册 Tool。
- Tool/Model 超时采用有限重试；失败映射为安全失败或 HANDOFF，不暴露 Stack、SQL、Header 或凭证。
- Session 仅为进程内恢复；新 Session 与跨身份 Session 不继承旧 State。

## Run and evaluate

必须使用项目 Conda 环境：

```powershell
conda run -n group-buy-agent python -m pip install -r requirements.txt
conda run -n group-buy-agent python -m pytest -q
conda run -n group-buy-agent python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

真实评测和验收记录位于 `reports/`；V3-3 覆盖真实 HTTP、真实 Provider、Java Facts、RAG、会话隔离与安全边界。开发环境的 `X-Authenticated-User-Id` 仅用于模拟可信身份边界，客户端请求体不接受用户 ID。
