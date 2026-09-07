# REQUEST_INPUT 两轮恢复与切题

## 第一轮用户输入

`为什么我参加不了这个活动？`

## Task / RoutingResult / Skill

Router 识别 `PARTICIPATION_DIAGNOSIS`，但 entities 中缺 activityId。Skill required_entities=`[activityId]`。

## 初始 AgentState

```json
{"current_query":"为什么我参加不了这个活动？","routing_entities":{},"task_status":"SKILL_ACTIVE"}
```

## DecisionContext #1 / LLM Decision #1

模型只能请求 Skill 允许的业务实体：

```json
{"action":"REQUEST_INPUT","missing_information":["activityId"],"question":"请提供活动编号。"}
```

## Harness / State 更新

Decision Contract 通过；Orchestrator 再检查 missing 是 required_entities 子集。State：

```json
{"task_status":"WAITING_INPUT","pending_user_query":"为什么我参加不了这个活动？","missing_information":["activityId"],"observations":[]}
```

SessionMemory 以 `(session_id, authenticated_identity)` 保存快照，HTTP 返回 needs_human=false。

## 第二轮路径 A：补充 activityId

用户同身份、同 Session 输入：`活动是 100123`。

Router 将其识别为补参而非新独立问题；State 恢复：current_query 合并原问题与补充，routing_entities 写入 activityId，pending/missing 清空，状态转 REASONING。

后续 DecisionContext 包含原诊断目标和 activityId。模型按 participation Skill 动态调用 Activity/Eligibility，生成 Observation/Evidence，Progress 清空后 ANSWER → COMPLETED。

## 第二轮路径 B：明确切题

用户输入：`算了，帮我查订单 123`。

RoutingResult=`ORDER_DIAGNOSIS` 且 intent_switch=true。TaskStore 暂停旧 participation task；Memory 不把旧 Observation 带入新任务；Orchestrator 创建新 task_id 和干净 State，再加载 order_diagnosis Skill。

## 新 Session / 跨身份

新 Session 没有旧 WAITING_INPUT；同 session_id 但不同 authenticated identity 也加载不到旧 State。消息中自称 userId 不改变认证键。

## Trace 摘要

补参：`ROUTED → REQUEST_INPUT → WAITING_INPUT → SESSION_LOAD → WAITING_INPUT_RESUMED → MODEL_DECISION...`

切题：`WAITING_INPUT → INTENT_SWITCH → TASK_PAUSED → NEW_TASK → ORDER_DIAGNOSIS`。

## 为什么不是固定 Workflow

恢复只还原 Task 目标和实体；下一 Tool 仍由模型依据 Context 决定。切题也由 RoutingResult 表达，不在 Memory 里拼接所有文本。

## 面试追问

1. REQUEST_INPUT 与 HANDOFF 的语义差异？
2. 为什么 UNKNOWN 短回复不能自动判切题？
3. Session key 为什么必须包含 identity？
4. pending_user_query 是否等于长期记忆？
5. 并发双写在生产中如何升级？
