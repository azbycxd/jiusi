# Context Engineering

## State 不等于 Context

AgentState 是完整、可恢复的程序工作状态：任务、身份、状态机、所有 ToolResult、
Observation、Progress、计数器与版本。DecisionContext 是当前模型轮的最小投影，
不复制另一套状态，也不暴露 auth、Header、Trace、内部错误和预算计数器。

## DecisionContext 字段

`task_id`、`skill_name`、`current_query`、`skill_instructions`、
`relevant_observations`、`available_evidence`、`skill_progress`、`available_tools`、
`context_version`、`estimated_tokens`。

ContextBuilder 从 AgentState 读取 current_query、observations 和 skill_progress，从
SkillSpec 读取 Prompt/allowed_tools，从 ToolRegistry 读取 Tool metadata。System Prompt
和 Decision Contract 在 Builder 中组合。

## ContextSelector

Selector 依次过滤：

1. Observation 是否来自当前 Skill 允许的 Tool；
2. 是否超过可选 freshness 上限；
3. 是否与当前 task 的业务实体匹配；
4. Skill-specific ContextPolicy 是否保留该事实；
5. 同 Tool 冲突事实只选择 sequence/timestamp 最新版本。

Selector 不读取 `possible_dimensions` 或 `required_dimensions`。Possible 描述能力空间，
Required 描述本次完成义务，Context Relevant 则由 allowed_tools、实体、时效与 Skill
ContextPolicy 决定；三者不能用同一个集合替代。

失败 ToolResult 不会生成 Observation，自然不能进入业务 Context。原始错误 detail、
Java stack 等也不会通过 ContextSelector 进入模型。

## 冲突事实

若 10:00 的 activity.status=EFFECTIVE 与 10:05 的 OVERDUE 同时保存在 State/Trace，
当前 DecisionContext 默认只放 sequence/timestamp 更新的一份。旧快照仍用于审计，
但不会让模型面对两个未标注冲突的当前事实。

## Compressor 与 Budget

ContextBudget 划分 system prompt、output、Observation、RAG 和 Tool metadata 预算；
当前数字只是工程示例，并非真实 tokenizer 或实验最优值。

不可压缩：Evidence 值、当前实体、身份边界指令、SkillProgress、Tool Schema 关键字段。
可压缩：旧自然语言解释、重复规则、长历史说明和低优先级旧 Observation。
长 ToolResult 必须先 normalize/project 成 Observation；不能把完整下游响应直接传模型。

ContextCompressor 只丢弃低优先级快照或截断说明文本，不改写业务事实。若保留预算仍
不足则明确失败，不靠摘要猜测改变事实语义。

## v1.1 Progress Snapshot

DecisionContext 获得的是安全深拷贝快照，而非可修改的 State Progress。快照包含本次
required_dimensions、每个维度 PENDING/SATISFIED、每个 Condition 已满足的 Evidence ID、
missing_conditions 和 remaining_dimensions。模型由“还缺 within_valid_time”选择下一动作，
而不是只看到模糊的“activity_state 未检查”。可信身份、Trace 和错误细节仍不进入快照。

真实项目 A 层仍使用最小 DiagnosisProgress；Condition 级快照是 Reference v1.1 的 B 层重构。
