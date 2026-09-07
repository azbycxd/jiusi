# Harness：统一、确定、可测试的动作边界

## 1. 真实性声明

A：真实工程有能力、身份、Evidence、Repeat 和预算约束。
B：Reference 把它们显式分成 Guard，由 HarnessRuntime 组合。
C：熔断、分布式预算、写操作补偿没有在本批实现。
Reference v1.1 只同步 Prompt 的 Evidence Requirement 表达，不连接真实 Provider。

## 2. 三者职责

Orchestrator 推进请求、模型轮和状态。
HarnessRuntime 按顺序执行确定性约束。
Guard 判断一条规则，失败返回稳定异常 code。
Prompt 提供软指令，不能证明动作安全。
Tool 本身还保留输入/输出验证，构成边界内的防御。

## 3. Tool 前顺序

Decision Contract。
Capability：Skill、Runtime allowlist、Registry 三层交集。
Argument Schema：必填、类型、范围、枚举和未知字段。
Identity Boundary：模型不能控制身份和基础设施。
Parameter Grounding：规范参数与来源原值一致。
Repeat：模型主动同动作重复。
CompletionPolicy：事实已充分时是否允许继续。
Loop/Budget：下一次实际执行有没有预算。
全部成功后才能 Execute Tool。

## 4. 为什么 Completion 也参与 Tool 前检查

完成后模型可能继续调用范围内但无意义的工具。
Capability 只能证明“允许”，不能证明“必要”。
CompletionGuard 默认阻止已经充分后继续探索。
如果 Skill 明确允许补充规则解释，可提供 allow_additional Policy。
Policy 只可缩小或解释任务范围，不能越过能力交集。
不规定 Activity 与 Eligibility 调用顺序。

## 5. ANSWER 前顺序

Decision Contract → Completion → Evidence → Lifecycle/Budget。
remaining 非空时拒绝过早完成。
Evidence 必须解析到当前 Observation 的精确路径和值。
WAITING_INPUT、COMPLETED、HANDOFF、FAILED 不接受新的答案。
资源恰好用完但答案已经产生，应允许当前轮完成。
不应把“不能再调用 Tool”误判为“不能返回已有答案”。

## 6. CapabilityGuard

Skill allowed_tools 是任务范围。
Runtime allowlist 是当前部署可执行范围。
Registry 是实际注册能力。
三者任一不满足就不能执行。
refund_order 请求被拒绝，而不是由字符串拼接调用函数。
结构化错误为 CAPABILITY_DENIED。

## 7. ArgumentGuard 与 IdentityGuard

ArgumentGuard 返回规范化参数，签名使用该规范结果。
格式验证不做业务归属判断。
IdentityGuard 递归检查受保护字段和别名。
AuthContext 只能从可信对象读取。
不能从模型 arguments 中寻找“备用 userId”。
缺可信身份返回 AUTH_REQUIRED。

## 8. GroundingGuard

来源账本不是模型自述的可信证明。
USER_INPUT 对照 Runtime 已提取实体。
OBSERVATION 对照 ID、path、value。
RUNTIME 对照可信代码自己的值表。
UNKNOWN、缺项、重复来源项、值/类型不一致全部拒绝。
失败码 PARAMETER_GROUNDING_FAILED。

## 9. Repeat、Retry、Fallback、Replan

| 名词 | 发起者 | 是否新业务动作 |
|---|---|---|
| Repeat | 模型 | 再次请求相同规范动作 |
| Retry | Runtime | 同一动作因瞬时失败再执行 |
| Fallback | Runtime/策略 | 转安全处理或替代能力 |
| Replan | 决策层 | 根据新信息提出新路径 |

Repeat 历史只记录通过 Guard 的模型动作。
Retry 不再次增加该历史。
每次实际 Retry 仍增加 tool_call_count 和 attempt。
retry_count 表示已经实际发生的额外执行次数。
有重试建议但预算不足，不应虚增 retry_count。

## 10. Loop 与资源预算

LoopGuard 检查 max_iterations 和 max_tool_calls。
BudgetGuard 支持 model/tool 计数，以及可选 token、时间、费用估算。
None 表示尚未计量，不等于零。
配置了上限却没有对应快照，返回 BUDGET_MEASUREMENT_MISSING。
估算不能声称是 Provider 实收 Token 或真实费用。
本批没有外部计费系统。

## 11. TimeoutPolicy

TOOL_TIMEOUT、connection、HTTP_502/503 属瞬时只读失败。
AUTH_REQUIRED、INVALID_ARGUMENT、NOT_FOUND、业务条件失败不重试。
未知异常默认不重试，防止把编程错误变成重试风暴。
Tool 的 retryable 声明要被 Runtime 的明确分类约束。
实际网络超时应由生产 Client 处理。
Reference 的耗时观察不等于强制取消阻塞执行。

## 12. RetryPolicy

RetryDecision 包含 should_retry、retry_index、reason、backoff_ms。
max_retries=1 是首次一次加额外一次。
backoff_ms 只是调度建议，测试不 sleep。
模型与 Tool 重试独立。
写型副作用即使瞬时失败也默认拒绝重试。
幂等能力未建立前不能按只读策略处理写请求。

## 13. 统一执行入口

validate_before_tool_call 返回规范参数。
execute_checked 把合格动作写入 Repeat 历史。
Registry.call 生成一次 ToolResult。
handle_result 保存结果并调用 ObservationFactory。
成功时追加 Observation/Evidence，并由 EvidenceObligationEvaluator 用全部可信 Evidence
刷新 query-scoped Progress；不读取 Tool dimension 决定完成。
失败时 TimeoutPolicy 分类，RetryPolicy 判断，再检查预算。
重试耗尽标记 HANDOFF。
空候选集能完成候选维度；空规则召回不能证明规则解释充分。

### v1.1 handle_result 原子链

`ToolResult → State → ObservationFactory → EvidenceRegistry → EvidenceObligationEvaluator
→ State.apply_progress_evaluation`。失败仍写 ToolResult，但不生成 Observation，也不会满足
任何 Obligation。Tool success 只有 status、缺 within_valid_time 时，Progress 明确保持
PENDING；这与 Tool result_schema 是否成功是两个 Contract。

CompletionGuard 不再读取 Skill 静态维度全集。它验证
`progress.required_dimensions ⊆ skill.possible_dimensions`，ANSWER 必须 `progress.complete`；
Possible 中未被当前 Query 要求的 rule_explanation 不会阻止答案。

## 14. 与前批 Orchestrator 的接线说明

本批不重写前批 Orchestrator、Router 或 ContextBuilder。
Runtime 保留 validate_tool_action、validate_answer、can_continue 方法名。
需要传入 Registry 与可信 provenance/user_values。
旧骨架没有来源账本时会明确拒绝，不会伪造可信来源。
测试从 HarnessRuntime 的真实参考入口执行完整 Tool→Observation 链。
这证明 Batch 2 数据流，不宣称整个 Reference 应用已完成启动验收。

## 15. 失败隔离与安全错误

GuardViolation 暴露稳定 code 与安全文案。
客户端原始异常不进入 Observation。
一次权限失败不应生成下一轮“订单不存在”的虚构事实。
合同失败和业务条件受限分别统计。
失败交由上层选择 HANDOFF、用户输入或终止。

## 16. 生产扩展讨论

熔断负责持续下游失败时停止施压，与每次有限 Retry 不同。
Checkpoint 负责重启恢复，必须考虑恢复后是否重放动作。
写型 Tool 需要确认、幂等键、审计与事务/补偿。
分布式预算要防止多个实例各自以为仍有余额。
这些能力只作为 C 层设计，不在当前实现中。

## 17. 验证证据

离线测试记录 Guard 调用顺序，证明不是仅创建文件。
两种事实顺序都能完成进度并验证答案。
伪造参数来源在 Client.calls 仍为空时拒绝。
空数组证据通过，伪造路径拒绝。
timeout 后有限重试，与 Repeat 历史分别计数。
