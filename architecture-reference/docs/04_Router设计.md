# Router 设计

## 职责边界

Router 决定“这是什么任务”；DecisionModel 决定“这个任务下一步做什么”；
SkillRegistry 只根据名称/Intent 返回已注册 SkillSpec。Router 不执行 Tool，也不创建
Skill 实例，更不维护诊断进度。

## RoutingResult

结果包含 `intent`、`skill_name`、`entities`、`confidence`、`reason_code`、`source`、
`intent_switch` 与审计用 `matched_signals`。Intent 有参与诊断、订单诊断、候选团队、
规则问答和 UNKNOWN；source 有 RULE、LLM、FALLBACK。

## Rule First

RuleBasedIntentRouter 并非关键词 if-else 堆。它把三类信息组合评分：

1. 强实体模式：activityId、outTradeNo。
2. 业务表达模式：不能参与、订单未成团、可加入团队。
3. 规则问答模式：含义、规则、计算或标签。

单个实体不能决定任务。多个意图得分接近时返回 UNKNOWN/低置信，避免错误高置信。
缺实体仍可以识别 Skill，后续由模型 REQUEST_INPUT。

## Composite Router

规则高置信时直接返回，降低延迟和成本；中低置信才调用 LLMIntentRouter 协议。
ReferenceLLMIntentRouter 是可注入 Stub，不连接真实 Provider。fallback 仍无法判断时，
Composite Router 稳定返回 UNKNOWN，由 Orchestrator HANDOFF。

不使用纯关键词，是因为“活动还有团吗”和“为什么不能参加活动”共享相同实体；
不对所有请求先用 LLM，是因为当前仅四个 Skill，规则高置信路径更可控。

## WAITING_INPUT 与 Intent Switch

原任务缺 activityId 时进入 WAITING_INPUT。后续“活动100123”同时满足缺失字段且表达
短，Router 标为 slot reply，Orchestrator 恢复原 query、合并实体并继续原 task_id。

若用户改说“算了，查订单644398015396”，明确新 Intent 触发 `intent_switch=true`：

1. TaskStore 暂停并保留旧 Task；
2. Orchestrator 新建 Order Task；
3. 新 AgentState 不携带旧参与诊断 Observation；
4. active task 切换到新任务。

UNKNOWN 不会被误当成切题，以免短补参被错误丢弃。

## 生产化扩展

【生产化扩展设计，当前真实项目未实现】当 Skill 达到数百个，可使用 domain routing、
候选 Skill retrieval、hierarchical routing，再对小候选集使用结构化 LLM fallback。
