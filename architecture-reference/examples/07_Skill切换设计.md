# Skill 切换、任务暂停与上下文隔离

## 第一轮用户输入

`为什么我参加不了这个活动？`

## Task / RoutingResult / Skill

Participation diagnosis 被选中，但缺 activityId。模型 REQUEST_INPUT，State 进入 WAITING_INPUT，pending_user_query 保存原目标。

```json
{"task_id":"task-participation","active_skill":"participation_diagnosis","task_status":"WAITING_INPUT","missing_information":["activityId"]}
```

## 第二轮明确切题

用户：`算了，查一下订单 644398015396。`

RoutingResult：

```json
{"intent":"ORDER_DIAGNOSIS","skill_name":"order_diagnosis","entities":{"outTradeNo":"644398015396"},"intent_switch":true}
```

## Orchestrator 状态更新

1. TaskStore 将旧 participation State 标记 inactive/pause。
2. SessionMemory 删除当前活跃键的旧快照。
3. 创建新 task_id、空 observations/tool_results/evidence/progress。
4. 加载 Order Skill；绝不把旧缺失 activityId 拼进新 Context。

## 新任务 DecisionContext #1

只含订单问题、Order Skill 指令、可用 Tool metadata、order_state=PENDING 及缺失 Condition。旧 Skill、旧 pending query、身份值均不可见。

## LLM Decision / Harness / Tool

```json
{"action":"CALL_TOOL","tool_name":"get_order_facts","tool_arguments":{"outTradeNo":"644398015396"}}
```

Capability、Argument、Identity、Provenance、Repeat、Budget 通过；Tool 成功形成 Order Observation/Evidence。Evaluator 确认 order.status Condition 后，order_state 才 SATISFIED。

## DecisionContext #2 / ANSWER

模型引用 `get_order_facts.order.status` 给出答案。EvidenceGuard 通过，State=`COMPLETED`。

## 与补参的区别

若第二轮只是 `活动是 100123`，Router 在 WAITING_INPUT 上下文中将其当补参，恢复旧 task；UNKNOWN 短文本不会自动导致切题。只有明确不同 Intent 才新建任务。

## 身份和 Session

TaskStore/SessionMemory 均不能只按 session_id 查找。不同 identity 即使复用同一字符串 Session，也不能看到暂停任务或 Observation。

## Trace 摘要

`REQUEST_INPUT → WAITING_INPUT → ROUTE(intent_switch) → TASK_PAUSED → NEW_TASK → SKILL_ACTIVE(order) → TOOL → OBSERVATION → ANSWER → COMPLETED`

## 为什么不是固定 Workflow

Skill 切换只改变任务能力范围；新 Skill 内的 Tool 决策仍由模型结合 Context 产生。TaskStore 管生命周期，不是 Planner。

## 面试追问

1. 何时补参，何时切题？
2. 为什么终态后不复用旧 State？
3. 暂停任务和长期记忆的差别？
4. 并发请求如何避免 state_version 冲突？
5. Skill unload 是否意味着销毁 Tool Registry？
