"""预算边界、答案生命周期与超时重试分类。"""
import unittest
from _support import *
from src.harness.loop_guard import LoopGuard
from src.harness.budget_guard import BudgetGuard, BudgetSnapshot
from src.harness.retry_policy import RetryPolicy
from src.harness.timeout_policy import TimeoutPolicy
from src.harness.capability_guard import GuardViolation

class LoopTests(unittest.TestCase):
    def test_exact_limit_answer_vs_next_action(self):
        state = make_state()
        state.tool_call_count = 5
        LoopGuard().validate(state, make_skill().runtime_budget)
        with self.assertRaises(GuardViolation):
            LoopGuard().validate(state, make_skill().runtime_budget, next_tool=True)

    def test_iteration_new_turn_limit(self):
        state = make_state()
        state.iteration_count = 8
        with self.assertRaises(GuardViolation):
            LoopGuard().validate(state, make_skill().runtime_budget, next_iteration=True)

    def test_budget_measurement_and_estimate(self):
        guard = BudgetGuard()
        self.assertEqual(guard.evaluate(BudgetSnapshot(), {"max_tokens": 100}).reason, "BUDGET_MEASUREMENT_MISSING")
        self.assertFalse(guard.evaluate(BudgetSnapshot(estimated_cost=2), {"max_cost": 1}).allowed)

    def test_retry_semantics_and_nonretryable_override(self):
        timeout = TimeoutPolicy().classify("TOOL_TIMEOUT")
        first = RetryPolicy().decide(timeout, 0, 1)
        self.assertEqual((first.should_retry, first.retry_index), (True, 1))
        self.assertFalse(RetryPolicy().decide(timeout, 1, 1).should_retry)
        self.assertFalse(RetryPolicy().decide(timeout, 0, 1, read_only=False).should_retry)
        for code in ("AUTH_REQUIRED", "INVALID_ARGUMENT", "NOT_FOUND", "UNEXPECTED", "BUSINESS_CONDITION_FAILED"):
            self.assertFalse(TimeoutPolicy().classify(code, True).retryable)
