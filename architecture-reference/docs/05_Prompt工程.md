# Prompt 工程

## 分层

模型输入由三类稳定指令和运行时数据构成：Base System Prompt、Skill Prompt、
Decision Contract，以及 Context 中的 Observation、Evidence、Progress 和 Tool metadata。
Prompt 全中文，但字段名保持契约中的稳定英文名称。

## Base System Prompt

全局约束覆盖：角色、业务边界、实时 Facts 与 RAG 分工、可信身份、Tool 使用、
Evidence、四种控制动作、失败语义、隐私和不输出隐藏思维过程。

Base Prompt 不维护 Tool 参数白名单。合法字段来自每个 Tool 的 arguments_schema；
Harness 另行验证参数值的 Provenance。Prompt 是软约束，不能替代代码安全边界。

## Decision Contract

- CALL_TOOL：`action/tool_name/tool_arguments`
- ANSWER：`action/answer/used_evidence`
- REQUEST_INPUT：`action/missing_information/question`
- HANDOFF：`action/reason_code/message`

Prompt 给出合法 JSON 与非法示例。DecisionValidator 执行 Extra Field reject；Harness
继续执行 Capability、Identity、Grounding、Completion 和 Evidence 校验。

## 四个 Skill Prompt

参与诊断强调两个独立维度、不固定顺序和完成后停止；订单诊断禁止由 CLOSE 推出退款；
候选团队明确空集合语义；规则问答禁止用一般规则推断实时实例。差异位于 Skill，
而不是在 Orchestrator 写业务分支。

## 一个真实 Prompt Engineering 教训

旧 System Prompt 曾全局禁止 `activityId`。当新增 Joinable Team Tool 后，activityId
已经是合法参数，于是 Prompt 与 Tool Schema 互相冲突。正确修复不是在 Prompt 再抄
一份允许名单，而是：

1. Tool Schema 成为参数格式的唯一结构来源；
2. Skill.allowed_tools 控制当前任务可调用范围；
3. IdentityGuard 拒绝身份和基础设施字段；
4. ParameterGroundingGuard 验证参数值来自用户或 Observation。

这说明 Prompt 负责引导，代码 Contract 才负责强制。
