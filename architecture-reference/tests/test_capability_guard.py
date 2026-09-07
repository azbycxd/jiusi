"""三层 Capability 独立约束，不以文件存在作为通过依据。"""
import unittest
from _support import *
from src.harness.capability_guard import CapabilityGuard, GuardViolation

class CapabilityTests(unittest.TestCase):
    def test_intersection_allows(self):
        guard = CapabilityGuard()
        metadata = guard.validate("get_activity_facts", make_skill(), make_registry().names(), make_registry())
        self.assertEqual(metadata.name, "get_activity_facts")

    def test_refund_and_outside_skill_denied(self):
        guard = CapabilityGuard()
        registry = make_registry()
        for name in ("refund_order", "get_order_facts"):
            with self.subTest(name=name), self.assertRaises(GuardViolation) as caught:
                guard.validate(name, make_skill(), registry.names(), registry)
            self.assertEqual(caught.exception.code, "CAPABILITY_DENIED")

    def test_runtime_and_registration_both_required(self):
        guard = CapabilityGuard()
        for allowed, registry in [((), make_registry()), (("get_activity_facts",), ToolRegistry())]:
            with self.assertRaises(GuardViolation):
                guard.validate("get_activity_facts", make_skill(), allowed, registry)
