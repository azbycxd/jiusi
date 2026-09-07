# Skill 设计：Possible、Required 与 Evidence Obligation

## Skill 是完整任务边界

Skill 比 Intent 重：它声明实体、允许 Tool、知识策略、Context、Requirement、Evidence Obligation、完成条件、失败策略、预算和安全策略。Skill 比 Tool 高：Tool 只执行一次受限动作。Skill 不是 SubAgent，不拥有独立模型或自治循环。

## v1.0 到 v1.1

v1.0 使用 Tool/Dimension-driven minimal Progress，解决了模型在开放诊断中提前 ANSWER，但 `progress_dimensions` 同时表达“可能涉及”和“本次必须检查”，且成功 Tool 的 `dimension` 会直接变成 checked，完成语义仍偏粗。

v1.1 是 Evidence-Obligation-Driven Progress：限制“本次必须获得哪些可信 Evidence”，而不是“必须调用哪些 Tool”。这是 v1.0 冻结后的单点 Reference 修正。

## SkillSpec v1.1 字段

| 字段 | 作用 |
|---|---|
| `required_entities` | 可由用户补齐的业务实体 |
| `allowed_tools` | Skill 级最小能力集合 |
| `knowledge_policy` | RAG 必需、可选或禁用 |
| `prompt_policy` | 当前任务中文指令 |
| `possible_dimensions` | Skill 理论上可能涉及的能力空间，不是本次必做全集 |
| `requirement_resolver` | 按 Query/基础路由语义输出 `ResolvedRequirements` |
| `evidence_obligations` | 每个维度需要满足的 Evidence Conditions |
| `completion_policy` | Progress 完整后是否允许 ANSWER |
| `failure_policy` | 补参、有限重试或 HANDOFF |
| `runtime_budget` | 循环、模型与 Tool 上限 |

## RequirementResolver

输入仅为当前 Query，以及确有需要时的 routing_intent/routing_entities；不能访问 authenticated identity、Trace、ToolResult error 或内部系统字段。输出 `ResolvedRequirements(required_dimensions, reason_codes)`。

硬约束：`required_dimensions ⊆ possible_dimensions`。Resolver 越界属于架构错误，不能静默接受。

Participation 示例：

- “活动 7 是否还在有效期？”→ `{activity_validity}`。
- “我在活动 7 有什么参与限制？”→ `{user_eligibility}`。
- “为什么我参加不了活动 7？”→ `{activity_validity, user_eligibility}`。
- 规则解释只有在规则本身是目标时才进入 Required；开放诊断默认不强制 RAG。

## Evidence Obligation

一个 Dimension 含多个必须满足的 `EvidenceCondition`。Condition 用 `accepted_paths` 和 EXACT/PREFIX 匹配真实 Evidence；一个 Condition 可接受多个不同来源，因此它不是 Tool Name Obligation。

`activity_validity` 要求：

1. `activity_status`：`get_activity_facts.activity.status`。
2. `within_valid_time`：`get_activity_facts.activity.within_valid_time`。

Tool success 但只有 status 时，Observation 合法存在，Dimension 仍为 PENDING。只有两个 Condition 都存在才 SATISFIED。

`user_eligibility` 最小要求 participation_limit_reached、tag_participation_allowed、market_downgraded、user_within_release_range。布尔 false 是完整事实；Evaluator 只判断事实是否被观察，不生成“能/不能参加”的自然语言结论。

## 四个 Skill 的最小迁移

- participation：Possible 为 activity_validity、user_eligibility、rule_explanation；Required 由 Query 裁剪。
- order：Possible 为 order_state、rule_explanation；当前实例问题最小要求 order.status。
- joinable_team：Required 为 candidate_team_availability；`candidate_teams=[]` 仍 SATISFIED。
- rule_qa：Required 为 rule_evidence；PREFIX 必须匹配至少一条 `rules[0]...`，`rules=[]` 保持 PENDING。

## 生命周期

Router 选 Skill → Skill 解析 Query Requirements → 创建全部 PENDING 的 SkillProgress → ToolResult 成功生成 Observation/Evidence → EvidenceObligationEvaluator 刷新状态 → CompletionGuard 只看 query-scoped Progress。

## 为什么不是固定 Workflow

Evidence Condition 描述“需要什么事实”，accepted_paths 允许不同可信 Tool 提供等价事实；available_tools metadata 告诉模型当前能力。模型可先 Activity 后 Eligibility，也可反向执行。Progress 不保存 Tool 顺序，Prompt 也不写 Dimension→固定 Tool 映射。

## 真实性边界

真实项目 A 层仍是已验证有效的最小 DiagnosisProgress。Possible Dimensions、RequirementResolver、Evidence Obligation、EvidenceObligationEvaluator 属于 B 层 Architecture Reference v1.1 重构；不能说真实线上已部署完整 Evidence Obligation Framework。
