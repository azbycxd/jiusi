# RAG 规则问答链路

## 用户输入

`拼团的参与标签规则是什么？`

## Task / Intent / RoutingResult

Intent=`RULE_QA`，Skill=`rule_qa`，没有 activityId/outTradeNo 等实例实体。

```json
{"intent":"RULE_QA","skill_name":"rule_qa","entities":{},"source":"RULE"}
```

## SkillSpec 摘要

allowed tool 仅 `search_group_buy_rules`；required dimension=`rule_evidence`；它不能调用 Java Facts 冒充当前用户状态。

## 初始 AgentState

observations 空，Progress rule_evidence=PENDING。

## DecisionContext #1 / LLM Decision #1

```json
{"action":"CALL_TOOL","tool_name":"search_group_buy_rules","tool_arguments":{"query":"拼团参与标签规则","topK":3}}
```

## Harness Validation

Capability 通过；RuleSearchArguments 校验 query/topK；query 来自当前用户问题；身份不参与 RAG 参数；预算内。

## ToolResult

```json
{"success":true,"source":"rule_catalog","data":{"rules":[{"entry_id":"participation-tag","title":"参与标签规则","content":"用户需满足活动配置的参与标签条件。"}]}}
```

## Observation / Evidence / Progress

Observation 记录规则候选；PREFIX Condition 匹配 `search_group_buy_rules.rules[0].content`，rule_evidence=SATISFIED。若 `rules=[]`，空集合本身仍是事实，但不存在 `rules[` 前缀，Progress 保持 PENDING。

## DecisionContext #2 / ANSWER

```json
{"action":"ANSWER","final_answer":"规则要求用户满足活动配置的参与标签条件；具体某位用户是否满足仍需实时资格事实。","used_evidence":["search_group_buy_rules.rules[0].content"]}
```

## Harness 与最终状态

CompletionGuard 通过，EvidenceGuard 从实际 Observation 解析 content；状态 `COMPLETED`。答案没有声称当前用户一定满足或不满足。

## Trace 摘要

`ROUTED(rule_qa) → MODEL_DECISION → RULE_SEARCH → OBSERVATION → EVIDENCE → ANSWER → COMPLETED`

## 为什么不是固定 Workflow

纯规则问题只需 RAG；实例问题才使用 Java Facts。RAG 不是所有 Skill 的固定最后一步，检索顺序和是否需要检索取决于当前信息需求。

## 面试追问

1. 为什么当前词法检索足够？
2. Top-3 100% 为什么不是答案 100% 正确？
3. 空 matches 是成功还是失败？
4. RAG content 如何成为 Evidence？
5. 什么时候升级 Hybrid/Rerank？
