import unittest
from _support import *
from src.routing.intent_router import RuleBasedIntentRouter, RoutingContext
from src.routing.routing_result import Intent


class RouterTests(unittest.TestCase):
    def setUp(self): self.router = RuleBasedIntentRouter()
    def test_participation(self):
        r=self.router.route("为什么我参加不了活动100123")
        self.assertEqual(r.intent, Intent.PARTICIPATION_DIAGNOSIS); self.assertEqual(r.entities["activityId"],100123)
    def test_order(self): self.assertEqual(self.router.route("订单644398015396为什么没拼成").intent, Intent.ORDER_DIAGNOSIS)
    def test_joinable(self): self.assertEqual(self.router.route("活动100123还有团吗").intent, Intent.JOINABLE_TEAM)
    def test_rule(self): self.assertEqual(self.router.route("CLOSE是什么意思").intent, Intent.RULE_QA)
    def test_activity_control(self): self.assertEqual(self.router.route("活动100123是否还在有效期内").intent, Intent.PARTICIPATION_DIAGNOSIS)
    def test_eligibility_control(self): self.assertEqual(self.router.route("活动100123当前参与限制").intent, Intent.PARTICIPATION_DIAGNOSIS)
    def test_ambiguous(self): self.assertEqual(self.router.route("活动100123").intent, Intent.UNKNOWN)
    def test_intent_switch_and_slot_reply(self):
        ctx=RoutingContext(Intent.PARTICIPATION_DIAGNOSIS,"participation_diagnosis",("activityId",),True)
        self.assertFalse(self.router.route("活动100123",ctx).intent_switch)
        self.assertTrue(self.router.route("算了，查订单644398015396",ctx).intent_switch)


if __name__ == "__main__": unittest.main()
