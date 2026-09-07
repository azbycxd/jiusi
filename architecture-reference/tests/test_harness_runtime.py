"""统一入口验证全部 Guard 的实际执行及有限重试。"""
import unittest
from _support import *
from src.harness.runtime import HarnessRuntime
from src.harness.capability_guard import GuardViolation
from src.progress.evaluator import EvidenceObligationEvaluator

class RuntimeTests(unittest.TestCase):
    def test_request_input_cannot_request_auth(self):
        runtime = HarnessRuntime.default(make_registry())
        runtime.validate_decision(Decision(Action.REQUEST_INPUT, missing_information=("activityId",)))
        with self.assertRaises(GuardViolation):
            runtime.validate_decision(Decision(Action.REQUEST_INPUT, missing_information=("token",)))

    def test_tool_budget_prevents_extra_retry_accounting(self):
        client = ReferenceStub(fixtures(), {("activity", 7): ["TOOL_TIMEOUT"]})
        state = make_state()
        runtime = HarnessRuntime.default(make_registry(client))
        result = runtime.execute_checked(
            Decision(Action.CALL_TOOL, "get_activity_facts", {"activityId": 7}),
            state, make_skill(max_tool_calls=1),
            provenance=provenance(), user_values={"activityId": 7})
        self.assertFalse(result.success)
        self.assertEqual(state.tool_retry_count, 0)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(state.task_status, TaskStatus.HANDOFF)

    def test_complete_progress_stops_additional_tool(self):
        state = make_state()
        skill = make_skill()
        state.observations.extend((
            observation(),
            observation({"eligibility":{"participation_limit_reached":True,
                         "tag_participation_allowed":False,"market_downgraded":False,
                         "user_within_release_range":True}}, "get_user_eligibility_facts"),
        ))
        state.apply_progress_evaluation(
            EvidenceObligationEvaluator().evaluate(skill, state.skill_progress, state.observations)
        )
        runtime = HarnessRuntime.default(make_registry())
        with self.assertRaises(GuardViolation) as caught:
            runtime.execute_checked(Decision(Action.CALL_TOOL, "get_activity_facts", {"activityId": 7}),
                                    state, skill, provenance=provenance(),
                                    user_values={"activityId": 7})
        self.assertEqual(caught.exception.code, "COMPLETION_ALREADY_SUFFICIENT")
        self.assertEqual(state.tool_call_count, 0)

    def test_model_retry_is_independent(self):
        runtime = HarnessRuntime.default(make_registry())
        self.assertTrue(runtime.should_retry_model("MODEL_TIMEOUT", 0, 1).should_retry)
        self.assertFalse(runtime.should_retry_model("MODEL_TIMEOUT", 1, 1).should_retry)
        self.assertFalse(runtime.should_retry_model("AUTH_REQUIRED", 0, 1).should_retry)

    def test_guard_composition_order(self):
        runtime = HarnessRuntime.default(make_registry())
        order = []
        def wrap(target, method, name):
            original = getattr(target, method)
            def record(*args, **kwargs):
                order.append(name)
                return original(*args, **kwargs)
            setattr(target, method, record)
        for target, method, name in (
            (runtime.capability_guard, "validate", "capability"),
            (runtime.argument_guard, "validate", "argument"),
            (runtime.identity_guard, "build_auth_context", "identity"),
            (runtime.parameter_grounding_guard, "validate", "grounding"),
            (runtime.repeat_guard, "validate", "repeat"),
            (runtime.completion_guard, "validate", "completion"),
            (runtime.loop_guard, "validate", "loop"),
            (runtime.budget_guard, "validate", "budget")):
            wrap(target, method, name)
        runtime.validate_before_tool_call(
            Decision(Action.CALL_TOOL, "get_activity_facts", {"activityId": 7}),
            make_state(), make_skill(), provenance=provenance(), user_values={"activityId": 7})
        self.assertEqual(order, ["capability", "argument", "identity", "grounding",
                                 "repeat", "completion", "loop", "budget"])

    def test_illegal_tool_and_missing_provenance_stop_before_execution(self):
        client = ReferenceStub(fixtures())
        runtime = HarnessRuntime.default(make_registry(client))
        for decision in (Decision(Action.CALL_TOOL, "refund_order", {}),
                         Decision(Action.CALL_TOOL, "get_activity_facts", {"activityId": 7})):
            with self.assertRaises(GuardViolation):
                runtime.execute_checked(decision, make_state(), make_skill())
        self.assertEqual(client.calls, [])

    def test_two_orders_and_grounded_answer(self):
        for names in (("get_activity_facts", "get_user_eligibility_facts"),
                      ("get_user_eligibility_facts", "get_activity_facts")):
            state = make_state()
            skill = make_skill()
            runtime = HarnessRuntime.default(make_registry())
            for name in names:
                runtime.execute_checked(Decision(Action.CALL_TOOL, name, {"activityId": 7}),
                                        state, skill, provenance=provenance(), user_values={"activityId": 7})
            answer = Decision(Action.ANSWER, final_answer="两个维度已有事实。",
                              used_evidence=tuple(state.evidence_refs))
            self.assertTrue(runtime.validate_before_answer(answer, state, skill))
            self.assertEqual(state.skill_progress.remaining_dimensions, set())
            self.assertEqual(state.tool_call_count, 2)

    def test_early_answer_and_forged_evidence(self):
        state = make_state()
        runtime = HarnessRuntime.default(make_registry())
        with self.assertRaises(GuardViolation) as caught:
            runtime.validate_answer(Decision(Action.ANSWER, final_answer="过早", used_evidence=()), state, make_skill())
        self.assertEqual(caught.exception.code, "COMPLETION_INCOMPLETE")
        skill = make_skill()
        state.observations.extend((
            observation(),
            observation({"eligibility":{"participation_limit_reached":True,
                         "tag_participation_allowed":False,"market_downgraded":False,
                         "user_within_release_range":True}}, "get_user_eligibility_facts"),
        ))
        state.apply_progress_evaluation(
            EvidenceObligationEvaluator().evaluate(skill, state.skill_progress, state.observations)
        )
        with self.assertRaises(GuardViolation) as caught:
            runtime.validate_answer(Decision(Action.ANSWER, final_answer="伪造", used_evidence=("available_tools",)),
                                    state, skill)
        self.assertEqual(caught.exception.code, "EVIDENCE_NOT_AVAILABLE")

    def test_retry_once_not_repeat_and_success(self):
        client = ReferenceStub(fixtures(), {("activity", 7): ["TOOL_TIMEOUT"]})
        state = make_state()
        runtime = HarnessRuntime.default(make_registry(client))
        result = runtime.execute_checked(Decision(Action.CALL_TOOL, "get_activity_facts", {"activityId": 7}),
                                         state, make_skill(), provenance=provenance(), user_values={"activityId": 7})
        self.assertTrue(result.success)
        self.assertEqual((state.tool_call_count, state.tool_retry_count, len(state.tool_call_history)), (2, 1, 1))
        self.assertEqual(len(state.observations), 1)

    def test_timeout_exhaustion_handoff(self):
        client = ReferenceStub(fixtures(), {("activity", 7): ["TOOL_TIMEOUT"] * 3})
        state = make_state()
        runtime = HarnessRuntime.default(make_registry(client))
        result = runtime.execute_checked(Decision(Action.CALL_TOOL, "get_activity_facts", {"activityId": 7}),
                                         state, make_skill(), provenance=provenance(), user_values={"activityId": 7})
        self.assertFalse(result.success)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(state.task_status, TaskStatus.HANDOFF)
        self.assertEqual(state.observations, [])

    def test_exact_tool_budget_still_accepts_answer(self):
        state = make_state()
        skill = make_skill(max_tool_calls=2)
        runtime = HarnessRuntime.default(make_registry())
        for name in skill.allowed_tools:
            runtime.execute_checked(Decision(Action.CALL_TOOL, name, {"activityId": 7}),
                                    state, skill, provenance=provenance(), user_values={"activityId": 7})
        runtime.validate_answer(Decision(Action.ANSWER, final_answer="完成", used_evidence=tuple(state.evidence_refs)), state, skill)
