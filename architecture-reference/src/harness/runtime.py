"""B 层统一 Harness Runtime，映射 A 层已实现的确定性边界。

Orchestrator 推进任务，Runtime 编排 Guard 顺序，单个 Guard 只执行一条规则。
Tool 前：Decision → Capability → Schema → Identity → Grounding → Repeat
→ CompletionPolicy → Loop/Budget。所有检查成功才允许产生调用副作用。
ANSWER 前：Completion → Evidence → Lifecycle/Budget。Tool failure 通过
TimeoutPolicy 分类和 RetryPolicy 限定次数；本参考只执行显式离线 Tool。
"""
from ..decision.actions import Action
from ..observations.observation import ObservationFactory
from ..observations.evidence import EvidenceRegistry
from ..progress.evaluator import EvidenceObligationEvaluator
from ..tools.base import SideEffectLevel
from .capability_guard import CapabilityGuard, GuardViolation
from .argument_guard import ArgumentGuard
from .identity_guard import IdentityGuard
from .parameter_grounding_guard import ParameterGroundingGuard
from .evidence_guard import EvidenceGuard
from .repeat_guard import RepeatGuard
from .loop_guard import LoopGuard
from .completion_guard import CompletionGuard
from .budget_guard import BudgetGuard, BudgetSnapshot
from .timeout_policy import TimeoutPolicy
from .retry_policy import RetryPolicy


class HarnessRuntime:
    """统一入口可注入 Guard；保留兼容方法名，缺必要上下文时明确拒绝。"""

    def __init__(self, registry=None, runtime_allowlist=None, *,
                 capability_guard=None, argument_guard=None, identity_guard=None,
                 parameter_grounding_guard=None, evidence_guard=None, repeat_guard=None,
                 loop_guard=None, completion_guard=None, budget_guard=None,
                 timeout_policy=None, retry_policy=None,
                 evidence_obligation_evaluator=None):
        self.registry = registry
        self.runtime_allowlist = frozenset(
            runtime_allowlist if runtime_allowlist is not None
            else registry.names() if registry is not None else ()
        )
        self.capability_guard = capability_guard or CapabilityGuard()
        self.argument_guard = argument_guard or ArgumentGuard()
        self.identity_guard = identity_guard or IdentityGuard()
        self.parameter_grounding_guard = parameter_grounding_guard or ParameterGroundingGuard()
        self.evidence_guard = evidence_guard or EvidenceGuard()
        self.repeat_guard = repeat_guard or RepeatGuard()
        self.loop_guard = loop_guard or LoopGuard()
        self.completion_guard = completion_guard or CompletionGuard()
        self.budget_guard = budget_guard or BudgetGuard()
        self.timeout_policy = timeout_policy or TimeoutPolicy()
        self.retry_policy = retry_policy or RetryPolicy()
        self.evidence_obligation_evaluator = (
            evidence_obligation_evaluator or EvidenceObligationEvaluator()
        )

    @classmethod
    def default(cls, registry, runtime_allowlist=None):
        """显式注册的工具集合构成默认 Runtime 能力，不扫描函数。"""
        return cls(registry, runtime_allowlist)

    def validate_decision(self, decision):
        """动作契约校验在能力判断前执行，不相信仅能解析 JSON 就合规。"""
        if not isinstance(decision.action, Action):
            raise GuardViolation("DECISION_CONTRACT_FAILED", "动作不在允许枚举中")
        if decision.action is Action.CALL_TOOL:
            valid = (bool(decision.tool_name) and isinstance(decision.tool_arguments, dict)
                     and decision.final_answer is None and not decision.used_evidence
                     and not decision.missing_information)
        elif decision.action is Action.ANSWER:
            valid = (isinstance(decision.final_answer, str) and bool(decision.final_answer.strip())
                     and not decision.tool_name and not decision.tool_arguments
                     and not decision.missing_information)
        else:
            valid = not decision.tool_name and not decision.tool_arguments and not decision.final_answer and not decision.used_evidence
            if decision.action is Action.REQUEST_INPUT:
                valid = valid and bool(decision.missing_information)
        if not valid:
            raise GuardViolation("DECISION_CONTRACT_FAILED", "动作字段不符合契约")
        if decision.action is Action.REQUEST_INPUT:
            fields = decision.missing_information
            if not isinstance(fields, (list, tuple)) or any(
                not isinstance(name, str) or not name.strip() for name in fields
            ):
                raise GuardViolation("DECISION_CONTRACT_FAILED", "缺失信息必须是业务字段列表")
            self.identity_guard.validate_model_arguments({name: None for name in fields})
        return decision

    def validate_before_tool_call(self, decision, state, skill, *, provenance=(),
                                  user_values=None, runtime_values=None, snapshot=None,
                                  allow_additional=None):
        """返回已规范化参数；Grounding 缺少可信账本即拒绝，不凭空构造来源。"""
        self.validate_decision(decision)
        if decision.action is not Action.CALL_TOOL or self.registry is None:
            raise GuardViolation("CAPABILITY_DENIED", "缺少注册表或不是工具动作")
        self.capability_guard.validate(decision.tool_name, skill, self.runtime_allowlist, self.registry)
        tool = self.registry.get(decision.tool_name)
        normalized = self.validate_tool_arguments(decision.tool_arguments, tool.arguments_type)
        self.validate_identity(decision.tool_arguments, state)
        self.validate_parameter_grounding(normalized, provenance,
                                         user_values=user_values or {},
                                         runtime_values=runtime_values or {},
                                         observations=state.observations)
        self.validate_repeat(decision.tool_name, normalized, state, skill)
        self.completion_guard.validate(skill, state.skill_progress, decision,
                                       allow_additional=allow_additional)
        self.validate_loop_and_budget(state, skill, next_tool=True, snapshot=snapshot)
        return normalized

    def validate_tool_action(self, decision, state, skill, **context):
        """前批调用名的兼容入口；所有验证仍统一委托。"""
        return self.validate_before_tool_call(decision, state, skill, **context)

    def validate_tool_arguments(self, arguments, contract):
        """格式与来源分阶段，规范化后才做签名。"""
        return self.argument_guard.validate(arguments, contract)

    def validate_identity(self, arguments, trusted_context):
        """模型参数不得携带身份；合法身份从可信对象提取。"""
        self.identity_guard.validate_model_arguments(arguments)
        return self.identity_guard.build_auth_context(trusted_context)

    def validate_parameter_grounding(self, arguments, provenance, **sources):
        """原值、Provenance 值和来源值三方对照。"""
        return self.parameter_grounding_guard.validate(arguments, provenance, **sources)

    def validate_repeat(self, name, normalized, state, skill):
        """验证尚未执行的模型动作，自动 Retry 不调用此入口。"""
        return self.repeat_guard.validate(name, normalized, state.tool_call_history,
                                         self.registry.repeat_policy(name),
                                         skill.runtime_budget.get("max_same_call", 1))

    def validate_loop_and_budget(self, state, skill, *, next_tool=False,
                                next_model=False, snapshot=None):
        """新模型轮和实际 Tool 调用各占预算，答案不预测额外 Tool。"""
        limits = skill.runtime_budget
        self.loop_guard.validate(state, limits, next_iteration=next_model, next_tool=next_tool)
        snapshot = snapshot or BudgetSnapshot(state.model_call_count, state.tool_call_count)
        if snapshot.model_calls != state.model_call_count or snapshot.tool_calls != state.tool_call_count:
            raise GuardViolation("BUDGET_SNAPSHOT_STALE", "预算快照计数与 State 不一致")
        return self.budget_guard.validate(snapshot, limits, next_model=int(next_model),
                                          next_tool=int(next_tool))

    def can_continue(self, state, skill):
        """由 Orchestrator 开始新模型轮前调用，计数由推进方更新。"""
        return self.validate_loop_and_budget(state, skill, next_model=True)

    def validate_completion(self, skill, progress, decision):
        """业务完成 Guard；不把资源次数当作完成维度。"""
        return self.completion_guard.validate(skill, progress, decision)

    def validate_evidence(self, used_evidence, observations, *, required=True):
        """只从当前业务快照建索引，不从 Tool metadata 中找引用。"""
        registry = EvidenceRegistry()
        for observation in observations:
            registry.register_observation(observation)
        return self.evidence_guard.validate(used_evidence, registry, required=required)

    def validate_before_answer(self, decision, state, skill, *, snapshot=None):
        """完成条件、精确证据、生命周期、预算依次检查。"""
        self.validate_decision(decision)
        if decision.action is not Action.ANSWER:
            raise GuardViolation("DECISION_CONTRACT_FAILED", "当前动作不是回答")
        self.validate_completion(skill, state.skill_progress, decision)
        evidence = self.validate_evidence(decision.used_evidence, state.observations)
        status = getattr(state.task_status, "value", state.task_status)
        if status in {"COMPLETED", "HANDOFF", "FAILED", "WAITING_INPUT"}:
            raise GuardViolation("LIFECYCLE_FAILED", "当前状态不接受回答")
        self.validate_loop_and_budget(state, skill, snapshot=snapshot)
        return evidence

    def validate_answer(self, decision, state, skill):
        """兼容前批调用名，返回经过真实注册表解析的 Evidence。"""
        return self.validate_before_answer(decision, state, skill)

    def should_retry_tool(self, result, retry_count, max_retries, *, read_only=True):
        """Tool 错误分类优先，不把业务失败或权限错误当瞬时失败。"""
        classification = self.timeout_policy.classify(result.error_code, result.retryable)
        return self.retry_policy.decide(classification, retry_count, max_retries,
                                        read_only=read_only)

    def should_retry_model(self, error_code, retry_count, max_retries):
        """模型重试独立记账；不影响 Tool Repeat 历史。"""
        classification = self.timeout_policy.classify(error_code)
        return self.retry_policy.decide(classification, retry_count, max_retries)

    def handle_result(self, result, state, skill):
        """结果入 State；成功生成事实后，以全部 Evidence 刷新 Obligations。"""
        state.append_tool_result(result)
        observation = ObservationFactory().create(result, len(state.observations) + 1)
        if observation is not None:
            state.append_observation(observation)
            state.evidence_refs.extend(observation.evidence)
            if state.skill_progress is not None:
                evaluations = self.evidence_obligation_evaluator.evaluate(
                    skill, state.skill_progress, state.observations
                )
                state.apply_progress_evaluation(evaluations)
        return observation

    def execute_checked(self, decision, state, skill, **context):
        """离线参考执行入口：先全部 Guard，再至多初次加配置次数 Retry。"""
        arguments = self.validate_before_tool_call(decision, state, skill, **context)
        signature = self.repeat_guard.signature(decision.tool_name, arguments)
        state.tool_call_history.append(signature)
        tool = self.registry.get(decision.tool_name)
        auth = self.identity_guard.build_auth_context(state)
        maximum = skill.runtime_budget.get("max_tool_retries", 1)
        for retry_count in range(maximum + 1):
            try:
                original = context.get("snapshot")
                snapshot = None
                if original is not None:
                    # 更新调用计数；估算指标由调用方提供，不能自行伪造 token/费用。
                    snapshot = BudgetSnapshot(state.model_call_count, state.tool_call_count,
                                              original.estimated_tokens, original.elapsed_ms,
                                              original.estimated_cost)
                self.validate_loop_and_budget(state, skill, next_tool=True, snapshot=snapshot)
            except GuardViolation as error:
                state.mark_handoff(error.code)
                if retry_count:
                    return result
                raise
            if retry_count:
                state.tool_retry_count += 1
            result = self.registry.call(decision.tool_name, arguments, auth, attempt=retry_count + 1)
            self.handle_result(result, state, skill)
            if result.success:
                return result
            retry = self.should_retry_tool(result, retry_count, maximum,
                                            read_only=tool.side_effect_level is SideEffectLevel.READ_ONLY)
            if not retry.should_retry:
                state.mark_handoff(retry.reason)
                return result
        raise RuntimeError("有限循环不应越过最终重试判断")
