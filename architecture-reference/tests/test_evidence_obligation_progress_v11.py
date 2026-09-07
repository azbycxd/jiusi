"""v1.1 Evidence-Obligation-Driven Progress 的核心契约与两条动态路径。"""
import unittest

from _core_support import core_registry, make_orchestrator, request, skill_registry
from _support import make_skill, make_state, observation, provenance
from src.context.builder import ContextBuilder
from src.context.selector import ContextSelector
from src.decision.actions import Action
from src.decision.schemas import AnswerDecision, Decision, ToolCallDecision
from src.harness.capability_guard import GuardViolation
from src.harness.completion_guard import CompletionGuard
from src.harness.runtime import HarnessRuntime
from src.observations.observation import ObservationFactory
from src.progress.evaluator import EvidenceObligationEvaluator
from src.progress.evidence_obligation import (
    EvidenceCondition,
    EvidenceMatchMode,
    EvidenceObligationSpec,
    ObligationStatus,
)
from src.progress.requirements import ResolvedRequirements
from src.skills.base import KnowledgePolicy, SkillSpec
from src.tools.tool_result import ToolResult


ELIGIBILITY = {"eligibility": {
    "participation_limit_reached": False,
    "tag_participation_allowed": False,
    "market_downgraded": False,
    "user_within_release_range": False,
}}


class EvidenceObligationProgressTests(unittest.TestCase):
    def setUp(self):
        self.skill = skill_registry().get("participation_diagnosis")
        self.runtime = HarnessRuntime.default(core_registry())

    def _state(self, query="为什么我参加不了活动7"):
        state = make_state(self.skill)
        state.current_query = query
        state.skill_progress = self.skill.create_progress(query)
        state.routing_entities = {"activityId": 7}
        return state

    def _handle(self, state, tool_name, data):
        return self.runtime.handle_result(
            ToolResult.success_result(tool_name, data), state, self.skill
        )

    def test_01_possible_and_required_are_distinct(self):
        progress = self.skill.create_progress("活动7是否还在有效期内？")
        self.assertEqual(set(self.skill.possible_dimensions), {
            "activity_validity", "user_eligibility", "rule_explanation"
        })
        self.assertEqual(progress.required_dimensions, {"activity_validity"})

    def test_02_completion_uses_required_subset_not_possible_all(self):
        state = self._state("活动7是否还在有效期内？")
        self._handle(state, "get_activity_facts", {
            "activity": {"status": "EFFECTIVE", "within_valid_time": True}
        })
        answer = Decision(Action.ANSWER, final_answer="仍在有效期", used_evidence=(
            "get_activity_facts.activity.status",
            "get_activity_facts.activity.within_valid_time",
        ))
        self.assertTrue(self.runtime.validate_answer(answer, state, self.skill))
        self.assertNotIn("user_eligibility", state.skill_progress.required_dimensions)

    def test_03_tool_success_with_partial_activity_stays_pending(self):
        state = self._state("活动7是否还在有效期内？")
        result = ToolResult.success_result(
            "get_activity_facts", {"activity": {"status": "EFFECTIVE"}}
        )
        self.assertEqual(core_registry().get("get_activity_facts").validate_result(result.data),
                         result.data)
        observation_result = self.runtime.handle_result(result, state, self.skill)
        self.assertIsNotNone(observation_result)
        self.assertEqual(state.skill_progress.obligation_status["activity_validity"],
                         ObligationStatus.PENDING)
        self.assertIn("within_valid_time",
                      state.skill_progress.missing_conditions["activity_validity"])

    def test_04_later_activity_evidence_satisfies_obligation(self):
        state = self._state("活动7是否还在有效期内？")
        self._handle(state, "get_activity_facts", {"activity": {"status": "EFFECTIVE"}})
        self._handle(state, "get_activity_facts", {
            "activity": {"status": "EFFECTIVE", "within_valid_time": False}
        })
        self.assertEqual(state.skill_progress.obligation_status["activity_validity"],
                         ObligationStatus.SATISFIED)

    def test_05_partial_eligibility_stays_pending(self):
        state = self._state()
        partial = {
            "eligibility": {"participation_limit_reached": False}
        }
        self.assertEqual(core_registry().get("get_user_eligibility_facts").validate_result(partial),
                         partial)
        self._handle(state, "get_user_eligibility_facts", partial)
        self.assertEqual(state.skill_progress.obligation_status["user_eligibility"],
                         ObligationStatus.PENDING)
        self.assertEqual(set(state.skill_progress.missing_conditions["user_eligibility"]), {
            "tag_participation_allowed", "market_downgraded", "user_within_release_range"
        })

    def test_06_complete_eligibility_satisfies(self):
        state = self._state()
        self._handle(state, "get_user_eligibility_facts", ELIGIBILITY)
        self.assertEqual(state.skill_progress.obligation_status["user_eligibility"],
                         ObligationStatus.SATISFIED)

    def test_07_boolean_false_is_evidence(self):
        state = self._state()
        self._handle(state, "get_user_eligibility_facts", ELIGIBILITY)
        satisfied = state.skill_progress.satisfied_evidence["user_eligibility"]
        self.assertEqual(set(satisfied), {
            "participation_limit_reached", "tag_participation_allowed",
            "market_downgraded", "user_within_release_range"
        })

    def test_08_empty_candidate_teams_satisfies(self):
        skill = skill_registry().get("joinable_team")
        state = make_state(skill)
        runtime = HarnessRuntime.default(core_registry())
        result = runtime.execute_checked(
            Decision(Action.CALL_TOOL, "get_joinable_team_facts", {"activityId": 7}),
            state, skill, provenance=provenance(), user_values={"activityId": 7}
        )
        self.assertEqual(result.data["candidate_teams"], [])
        self.assertTrue(state.skill_progress.complete)

    def test_09_empty_rules_do_not_satisfy(self):
        skill = skill_registry().get("rule_qa")
        state = make_state(skill)
        HarnessRuntime.default(core_registry()).handle_result(
            ToolResult.success_result("search_group_buy_rules", {"rules": []}), state, skill
        )
        self.assertFalse(state.skill_progress.complete)

    def test_10_nonempty_rules_satisfy_prefix(self):
        skill = skill_registry().get("rule_qa")
        state = make_state(skill)
        HarnessRuntime.default(core_registry()).handle_result(
            ToolResult.success_result("search_group_buy_rules", {"rules": [
                {"entry_id": "r1", "title": "规则", "content": "内容"}
            ]}), state, skill
        )
        self.assertTrue(state.skill_progress.complete)

    def test_11_unrelated_observation_does_not_satisfy(self):
        state = self._state("活动7是否还在有效期内？")
        state.observations.append(observation({"order": {"status": "CLOSE"}},
                                              "get_order_facts"))
        evaluations = EvidenceObligationEvaluator().evaluate(
            self.skill, state.skill_progress, state.observations
        )
        state.apply_progress_evaluation(evaluations)
        self.assertFalse(state.skill_progress.complete)

    def test_12_fabricated_evidence_ref_does_not_satisfy(self):
        state = self._state("活动7是否还在有效期内？")
        state.evidence_refs.append("get_activity_facts.activity.within_valid_time")
        evaluations = EvidenceObligationEvaluator().evaluate(
            self.skill, state.skill_progress, state.observations
        )
        state.apply_progress_evaluation(evaluations)
        self.assertFalse(state.skill_progress.complete)

    def test_13_condition_accepts_alternative_tool_path(self):
        obligation = EvidenceObligationSpec("business_status", (
            EvidenceCondition("status", ("tool_a.status", "tool_b.state")),
        ))
        resolver = lambda query, **_: ResolvedRequirements(
            frozenset({"business_status"}), ("TEST_BUSINESS_STATUS",)
        )
        skill = SkillSpec(
            "alternate", "1", "test", (), ("tool_a", "tool_b"),
            KnowledgePolicy.NONE, "中文", "context", "evidence", "complete", "failure",
            ("business_status",), (obligation,), requirement_resolver=resolver,
        )
        progress = skill.create_progress("状态")
        obs = ObservationFactory().create(
            ToolResult.success_result("tool_b", {"state": "READY"})
        )
        progress.apply_evaluations(
            EvidenceObligationEvaluator().evaluate(skill, progress, (obs,))
        )
        self.assertTrue(progress.complete)

    def test_14_harness_never_uses_tool_dimension_as_completion(self):
        state = self._state("活动7是否还在有效期内？")
        self._handle(state, "get_activity_facts", {"activity": {"status": "EFFECTIVE"}})
        self.assertTrue(state.observations)
        self.assertFalse(state.skill_progress.complete)

    def test_15_control_query_full_orchestrator_e2e(self):
        decisions = [
            ToolCallDecision("get_activity_facts", {"activityId": 7}),
            AnswerDecision("活动当前不在有效时间内。", (
                "get_activity_facts.activity.status",
                "get_activity_facts.activity.within_valid_time",
            )),
        ]
        agent, model, _, _ = make_orchestrator(decisions)
        state = agent.handle_request(request("活动7是否还在有效期内？", session="control-v11"))
        self.assertEqual(state.task_status.value, "COMPLETED")
        self.assertEqual(state.tool_call_count, 1)
        self.assertEqual(state.skill_progress.required_dimensions, {"activity_validity"})

    def test_16_participation_path_a_activity_then_eligibility(self):
        decisions = [
            ToolCallDecision("get_activity_facts", {"activityId": 7}),
            ToolCallDecision("get_user_eligibility_facts", {"activityId": 7}),
            AnswerDecision("证据充分。", (
                "get_activity_facts.activity.status",
                "get_user_eligibility_facts.eligibility.participation_limit_reached",
            )),
        ]
        state = make_orchestrator(decisions)[0].handle_request(
            request("为什么我参加不了活动7", session="path-a-v11")
        )
        self.assertEqual(state.task_status.value, "COMPLETED")

    def test_17_full_eligibility_alone_cannot_answer_open_diagnosis(self):
        state = self._state()
        self.runtime.execute_checked(
            Decision(Action.CALL_TOOL, "get_user_eligibility_facts", {"activityId": 7}),
            state, self.skill, provenance=provenance(), user_values={"activityId": 7}
        )
        with self.assertRaises(GuardViolation) as caught:
            self.runtime.validate_answer(
                Decision(Action.ANSWER, final_answer="提前回答", used_evidence=(
                    "get_user_eligibility_facts.eligibility.participation_limit_reached",
                )), state, self.skill
            )
        self.assertEqual(caught.exception.code, "COMPLETION_INCOMPLETE")

    def test_18_possible_rule_explanation_is_not_forced(self):
        state = self._state()
        self._handle(state, "get_activity_facts", {
            "activity": {"status": "EFFECTIVE", "within_valid_time": True}
        })
        self._handle(state, "get_user_eligibility_facts", ELIGIBILITY)
        self.assertTrue(state.skill_progress.complete)
        self.assertNotIn("rule_explanation", state.skill_progress.required_dimensions)
        with self.assertRaises(GuardViolation) as caught:
            CompletionGuard().validate(
                self.skill, state.skill_progress,
                Decision(Action.CALL_TOOL, "search_group_buy_rules", {"query": "规则"})
            )
        self.assertEqual(caught.exception.code, "COMPLETION_ALREADY_SUFFICIENT")

    def test_19_participation_path_b_eligibility_then_activity(self):
        decisions = [
            ToolCallDecision("get_user_eligibility_facts", {"activityId": 7}),
            ToolCallDecision("get_activity_facts", {"activityId": 7}),
            AnswerDecision("证据充分。", (
                "get_user_eligibility_facts.eligibility.participation_limit_reached",
                "get_activity_facts.activity.within_valid_time",
            )),
        ]
        state = make_orchestrator(decisions)[0].handle_request(
            request("为什么我参加不了活动7", session="path-b-v11")
        )
        self.assertEqual(state.task_status.value, "COMPLETED")

    def test_20_context_contains_condition_level_progress_snapshot(self):
        state = self._state("活动7是否还在有效期内？")
        self._handle(state, "get_activity_facts", {"activity": {"status": "EFFECTIVE"}})
        context = ContextBuilder().build(state, self.skill, core_registry())
        dimension = context.skill_progress["dimensions"]["activity_validity"]
        self.assertEqual(dimension["status"], "PENDING")
        self.assertEqual(dimension["missing_conditions"], ("within_valid_time",))

    def test_21_resolver_cannot_escape_possible_dimensions(self):
        resolver = lambda query, **_: ResolvedRequirements(
            frozenset({"not_possible"}), ("BAD_RESOLVER",)
        )
        skill = SkillSpec(
            "bad", "1", "bad", (), (), KnowledgePolicy.NONE,
            "中文", "context", "progress", "complete", "failure",
            ("possible",), (), requirement_resolver=resolver,
        )
        with self.assertRaises(ValueError):
            skill.create_progress("query")

    def test_22_selector_does_not_require_progress_dimensions_attribute(self):
        class ContextOnlySkill:
            allowed_tools = ("get_activity_facts",)

            @staticmethod
            def select_observations(items):
                return tuple(items)

        state = self._state()
        state.observations.append(observation())
        selected = ContextSelector().select(state, ContextOnlySkill(), core_registry())
        self.assertEqual(len(selected), 1)


if __name__ == "__main__":
    unittest.main()
