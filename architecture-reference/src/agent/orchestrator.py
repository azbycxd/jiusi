"""教学型在线 Agent 主链。

Orchestrator 只推进流程，不推理 Activity/Eligibility/Order 等业务顺序。
业务范围和完成条件来自 SkillSpec/SkillProgress；确定性硬约束统一进入 HarnessRuntime。
"""
from dataclasses import dataclass
from uuid import uuid4

from .state import AgentState, TaskStatus
from ..decision.actions import DecisionAction
from ..decision.validator import DecisionValidationError, DecisionValidator
from ..harness.capability_guard import GuardViolation
from ..observations.provenance import ParameterProvenance, SourceType
from ..routing.intent_router import RoutingContext
from ..routing.routing_result import Intent


TERMINAL = {TaskStatus.COMPLETED, TaskStatus.HANDOFF, TaskStatus.FAILED,
            TaskStatus.WAITING_INPUT}


@dataclass(frozen=True)
class PreparedRequest:
    session_id: str
    authenticated_user_id: str
    message: str


class Orchestrator:
    """Router 定任务、Model 提议动作、Harness 约束、Orchestrator 推进。"""

    def __init__(self, router, skills, context_builder, model, harness, tools,
                 memory, task_store=None, trace_recorder=None):
        self.router = router
        self.skills = skills
        self.context_builder = context_builder
        self.model = model
        self.harness = harness
        self.tools = tools
        self.memory = memory
        self.task_store = task_store
        self.trace = trace_recorder
        self.decision_validator = DecisionValidator()

    def handle_request(self, request):
        """一次 HTTP 请求的同步 Reference：可能完成，也可能等待输入/转人工。"""
        prepared = self._prepare_request(request)
        state, pre_routing = self._load_or_create_state(prepared)
        try:
            task = self._resolve_current_task(state)
            routing = self._route_if_needed(task, pre_routing)
            if routing.intent is Intent.UNKNOWN or not routing.skill_name:
                return self._handle_handoff(task, "UNKNOWN_CAPABILITY",
                                            "当前能力无法可靠识别该任务。")
            skill = self._load_skill(routing.skill_name)
            self._activate_skill(task, skill, routing)
            return self._run_agent_loop(task, skill)
        except (GuardViolation, DecisionValidationError, KeyError, ValueError) as error:
            code = getattr(error, "code", "ORCHESTRATION_CONTRACT_FAILURE")
            return self._handle_handoff(state, code, "当前请求无法安全继续，建议转人工。")
        except Exception:
            # Reference 最外层兜底不返回异常文本或堆栈。
            state.task_status = TaskStatus.FAILED
            state.response_message = "当前服务暂时无法完成请求。"
            self._record_transition(state, "FAILED", "UNEXPECTED_RUNTIME_FAILURE")
            return self._finalize(state)

    def _prepare_request(self, request):
        """Gateway 已认证；这里再次检查形状，但不从 message 读取身份。"""
        session = getattr(request, "session_id", None)
        identity = getattr(request, "authenticated_user_id", None)
        message = getattr(request, "message", None)
        if not all(isinstance(value, str) and value.strip()
                   for value in (session, identity, message)):
            raise ValueError("请求上下文不完整")
        return PreparedRequest(session.strip(), identity.strip(), message.strip())

    def _load_or_create_state(self, request):
        """WAITING_INPUT 先判断补参或切题；不能让 Memory 无条件拼接消息。"""
        existing = self.memory.load(request.session_id, request.authenticated_user_id)
        if existing is None or existing.task_status in {
            TaskStatus.COMPLETED, TaskStatus.HANDOFF, TaskStatus.FAILED
        }:
            state = AgentState(request.session_id, uuid4().hex,
                               request.authenticated_user_id,
                               current_query=request.message)
            return state, None
        if existing.task_status is not TaskStatus.WAITING_INPUT:
            existing.current_query = request.message
            return existing, None
        context = self._routing_context(existing)
        routing = self.router.route(request.message, context,
                                    self.skills.candidate_skills(request.message))
        if self._detect_intent_switch(existing, routing):
            self._pause_old_task(existing)
            self.memory.delete(existing.session_id, existing.authenticated_user_id)
            state = AgentState(request.session_id, uuid4().hex,
                               request.authenticated_user_id,
                               current_query=request.message)
            return state, routing
        self._resume_waiting_task(existing, request.message, routing)
        return existing, routing

    def _resolve_current_task(self, state):
        """本 Reference 每次只推进一个活跃 Task；多 Task 快照由 TaskStore 保存。"""
        if state.task_status in TERMINAL and state.task_status is not TaskStatus.WAITING_INPUT:
            raise ValueError("终态任务不能继续")
        return state

    def _routing_context(self, state):
        try:
            intent = Intent(state.routing_intent) if state.routing_intent else None
        except ValueError:
            intent = None
        return RoutingContext(intent, state.active_skill,
                              tuple(state.missing_information),
                              state.task_status is TaskStatus.WAITING_INPUT)

    def _detect_intent_switch(self, state, routing):
        """只有明确新意图才切题；UNKNOWN 不吞掉合法的短补参。"""
        if routing.intent_switch:
            return True
        return bool(state.routing_intent and routing.intent is not Intent.UNKNOWN
                    and routing.intent.value != state.routing_intent)

    def _pause_old_task(self, state):
        """切题只暂停，不把旧 Participation 等 Observation 带入新 Task。"""
        if self.task_store is not None:
            self.task_store.import_state(state, active=False)
        self._record_transition(state, "TASK_PAUSED", "INTENT_SWITCH")

    def _resume_waiting_task(self, state, message, routing):
        original = state.pending_user_query or state.current_query
        state.current_query = f"{original}\n用户补充信息：{message}"
        state.pending_user_query = None
        state.missing_information.clear()
        state.routing_entities.update(routing.entities)
        state.task_status = TaskStatus.REASONING
        self._record_transition(state, "REASONING", "WAITING_INPUT_RESUMED")

    def _route_if_needed(self, state, pre_routing=None):
        if pre_routing is not None and pre_routing.intent is not Intent.UNKNOWN:
            return pre_routing
        if state.active_skill and state.routing_intent:
            skill = self.skills.get(state.active_skill)
            return self.router.route(state.current_query, self._routing_context(state), (skill,))
        return self.router.route(state.current_query, None,
                                 self.skills.candidate_skills(state.current_query))

    def _load_skill(self, name):
        """Router 不直接 new Skill；唯一加载入口是 SkillRegistry。"""
        return self.skills.get(name)

    def _activate_skill(self, state, skill, routing):
        if state.active_skill and state.active_skill != skill.name:
            raise ValueError("未经过 Intent Switch 不能替换 Skill")
        state.active_skill = skill.name
        state.routing_intent = routing.intent.value
        state.routing_entities.update(routing.entities)
        state.runtime_budget = dict(skill.runtime_budget)
        if state.skill_progress is None:
            self._initialize_skill_progress(state, skill)
        state.task_status = TaskStatus.SKILL_ACTIVE
        self._record_transition(state, "SKILL_ACTIVE", routing.reason_code)

    def _initialize_skill_progress(self, state, skill):
        """Resolver 按 Query 裁剪 Required；Orchestrator 不含业务关键词规则。"""
        state.skill_progress = skill.create_progress(
            state.current_query,
            state.current_query,
            routing_intent=state.routing_intent,
            routing_entities=state.routing_entities,
        )

    def _run_agent_loop(self, state, skill):
        """有限 Loop：Build Context → Decision → Harness → Dispatch。"""
        while state.task_status not in TERMINAL:
            try:
                self.harness.can_continue(state, skill)
            except GuardViolation as error:
                return self._handle_handoff(state, error.code, "本次任务已达到安全执行上限。")
            context = self._build_context(state, skill)
            decision = self._request_decision(context, state)
            decision = self._validate_decision(decision)
            outcome = self._dispatch_decision(decision, state, skill)
            if outcome is not None:
                return outcome
        return self._finalize(state)

    def _build_context(self, state, skill):
        return self.context_builder.build(state, skill, self.tools)

    def _request_decision(self, context, state):
        state.task_status = TaskStatus.REASONING
        state.iteration_count += 1
        state.model_call_count += 1
        decision = self.model.decide(context)
        state.model_call_history.append({"iteration": state.iteration_count,
                                         "action": getattr(getattr(decision, "action", None),
                                                           "value", None)})
        self._record_transition(state, "MODEL_DECISION", "MODEL_RETURNED")
        return decision

    def _validate_decision(self, decision):
        normalized = self.decision_validator.parse(decision)
        return self.harness.validate_decision(normalized)

    def _dispatch_decision(self, decision, state, skill):
        if decision.action is DecisionAction.CALL_TOOL:
            return self._handle_tool_call(decision, state, skill)
        if decision.action is DecisionAction.ANSWER:
            return self._handle_answer(decision, state, skill)
        if decision.action is DecisionAction.REQUEST_INPUT:
            return self._handle_request_input(decision, state, skill)
        return self._handle_handoff(state, decision.reason_code, decision.message)

    def _handle_tool_call(self, decision, state, skill):
        state.task_status = TaskStatus.ACTION
        provenance, user_values = self._parameter_provenance(decision, state)
        result = self._execute_tool(decision, state, skill, provenance, user_values)
        if not result.success:
            return self._handle_tool_failure(result, state, skill)
        self._handle_tool_success(result, state, skill)
        return None

    def _execute_tool(self, decision, state, skill, provenance, user_values):
        """所有 Guard 与有限 Retry 经 Harness；Orchestrator 不复制判断。"""
        return self.harness.execute_checked(
            decision, state, skill, provenance=provenance,
            user_values=user_values, runtime_values={},
        )

    def _handle_tool_success(self, result, state, skill):
        """Observation/Evidence/Progress 已由 Harness.handle_result 原子式推进。"""
        state.task_status = TaskStatus.OBSERVING
        self._evaluate_skill_completion(state, skill)
        state.task_status = TaskStatus.REASONING
        self._record_transition(state, "OBSERVING", f"{result.tool_name}:SUCCESS")

    def _handle_tool_failure(self, result, state, skill):
        """Harness 已完成错误分类和有限重试；失败不产生 Observation。"""
        action = skill.failure_action(unavailable=True, retryable=False)
        if action == "CONTINUE" and state.task_status is not TaskStatus.HANDOFF:
            state.task_status = TaskStatus.REASONING
            return None
        if state.task_status is not TaskStatus.HANDOFF:
            state.mark_handoff(result.error_code or "TOOL_FAILURE")
        state.response_message = "当前事实查询失败，无法可靠给出业务结论。"
        self._record_transition(state, "HANDOFF", result.error_code or "TOOL_FAILURE")
        return self._finalize(state)

    def _create_observation(self, result, state, skill):
        """公共扩展点；默认创建工作由 Harness.handle_result 统一完成。"""
        before = len(state.observations)
        observation = self.harness.handle_result(result, state, skill)
        return observation if len(state.observations) > before else None

    def _evaluate_skill_completion(self, state, skill):
        """信息充分并不直接生成答案；模型仍需给出有 Evidence 的 ANSWER。"""
        return skill.is_complete(state.skill_progress)

    def _handle_answer(self, decision, state, skill):
        evidence = self.harness.validate_answer(decision, state, skill)
        state.response_message = decision.final_answer
        state.mark_completed(list(evidence))
        self._record_transition(state, "COMPLETED", "ANSWER_VALIDATED")
        return self._finalize(state)

    def _handle_request_input(self, decision, state, skill):
        """只允许请求 Skill 声明且尚未具备的业务实体。"""
        missing = set(decision.missing_information)
        allowed = set(skill.required_entities) - set(state.routing_entities)
        if not missing or not missing <= allowed or not skill.security_policy.allow_request_input:
            raise GuardViolation("REQUEST_INPUT_NOT_ALLOWED", "缺失信息不属于可补业务实体")
        state.mark_waiting_input(list(decision.missing_information))
        state.response_message = decision.question
        self._record_transition(state, "WAITING_INPUT", "REQUEST_INPUT")
        return self._finalize(state)

    def _handle_handoff(self, state, reason_code, message):
        state.mark_handoff(reason_code or "HANDOFF")
        state.response_message = message or "当前能力无法可靠继续，建议转人工。"
        self._record_transition(state, "HANDOFF", reason_code or "HANDOFF")
        return self._finalize(state)

    def _persist_state(self, state):
        previous = self.memory.load(state.session_id, state.authenticated_user_id)
        expected = previous.state_version if previous else 0
        saved = self.memory.save(state, expected_version=expected)
        if self.task_store is not None:
            self.task_store.import_state(saved, active=saved.task_status not in TERMINAL)
        return saved

    def _record_transition(self, state, stage, reason):
        if self.trace is not None:
            self.trace.record_state_transition(
                trace_id=state.trace_id, task_id=state.task_id,
                stage=stage, reason_code=reason,
            )

    def _finalize(self, state):
        return self._persist_state(state)

    def _parameter_provenance(self, decision, state):
        """参数格式与来源分离；优先绑定用户实体，其次绑定 Observation 路径。"""
        user_values = dict(state.routing_entities)
        user_values["query"] = state.current_query
        ledger = []
        for name, value in decision.tool_arguments.items():
            if name in user_values and type(user_values[name]) is type(value) and user_values[name] == value:
                ledger.append(ParameterProvenance(name, value, SourceType.USER_INPUT, name))
                continue
            source = self._find_observation_value(state.observations, value)
            if source is None:
                ledger.append(ParameterProvenance(name, value, SourceType.UNKNOWN, "unknown"))
            else:
                observation_id, path = source
                ledger.append(ParameterProvenance(name, value, SourceType.OBSERVATION,
                                                  path, observation_id))
        return tuple(ledger), user_values

    def _find_observation_value(self, observations, target):
        for observation in reversed(observations):
            found = self._walk_value(observation.data, target)
            if found is not None:
                return observation.observation_id, found
        return None

    def _walk_value(self, value, target, path=""):
        if path and type(value) is type(target) and value == target:
            return path
        if isinstance(value, dict):
            for key, item in value.items():
                found = self._walk_value(item, target, f"{path}.{key}" if path else key)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for index, item in enumerate(value):
                found = self._walk_value(item, target, f"{path}[{index}]")
                if found is not None:
                    return found
        return None
