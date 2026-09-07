"""模型 Repeat 与 Runtime Retry 分账。"""
import unittest
from _support import *
from src.harness.repeat_guard import RepeatGuard
from src.harness.capability_guard import GuardViolation
from src.tools.base import RepeatPolicy

class RepeatTests(unittest.TestCase):
    def test_canonical_key_order(self):
        guard = RepeatGuard()
        self.assertEqual(guard.signature("x", {"a": 1, "b": 2}), guard.signature("x", {"b": 2, "a": 1}))

    def test_repeatable_and_runtime_minimum(self):
        guard = RepeatGuard()
        signature = guard.signature("x", {"a": 1})
        with self.assertRaises(GuardViolation):
            guard.validate("x", {"a": 1}, [signature], RepeatPolicy(), 5)
        guard.validate("x", {"a": 1}, [signature], RepeatPolicy(True, 2), 2)
        with self.assertRaises(GuardViolation):
            guard.validate("x", {"a": 1}, [signature], RepeatPolicy(True, 3), 1)
