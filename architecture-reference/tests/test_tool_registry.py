"""Registry 自描述接线和 Tool 正常/异常路径。"""
import unittest
from _support import *
from src.tools.base import SideEffectLevel

class RegistryTests(unittest.TestCase):
    def test_fifth_tool_returns_rule_observation(self):
        from types import SimpleNamespace
        from src.tools.rag.search_group_buy_rules_tool import SearchGroupBuyRulesTool
        class LocalRetriever:
            def search(self, query):
                return [SimpleNamespace(entry_id="r1", title="规则", content="参考规则内容")]
        registry = make_registry()
        registry.register(SearchGroupBuyRulesTool(LocalRetriever()))
        result = registry.call("search_group_buy_rules", {"query": "规则"}, make_state())
        self.assertTrue(result.success)
        obs = ObservationFactory().create(result)
        self.assertEqual(obs.get_path("rules[0].entry_id"), "r1")
        self.assertEqual(len(registry.list_metadata()), 5)

    def test_connection_and_auth_failure(self):
        client = ReferenceStub(fixtures(), {("activity", 7): ["TOOL_CONNECTION_ERROR"]})
        result = make_registry(client).call("get_activity_facts", {"activityId": 7}, make_state())
        self.assertEqual(result.error_code, "TOOL_CONNECTION_ERROR")
        self.assertTrue(result.retryable)
        state = make_state()
        state.authenticated_user_id = ""
        result = make_registry().call("get_activity_facts", {"activityId": 7}, state)
        self.assertEqual(result.error_code, "AUTH_REQUIRED")
        self.assertFalse(result.retryable)
    def test_metadata_and_no_duplicate(self):
        registry = make_registry()
        self.assertEqual(len(registry.list_metadata()), 4)
        self.assertTrue(all(m.side_effect_level is SideEffectLevel.READ_ONLY for m in registry.list_metadata()))
        with self.assertRaises(ValueError):
            registry.register(registry.get("get_order_facts"))
        registry.unregister("get_order_facts")
        with self.assertRaises(KeyError):
            registry.get("get_order_facts")

    def test_four_tools_normalize_results(self):
        registry = make_registry()
        for name, args in (("get_order_facts", {"outTradeNo": "o-7"}),
                           ("get_activity_facts", {"activityId": 7}),
                           ("get_user_eligibility_facts", {"activityId": 7}),
                           ("get_joinable_team_facts", {"activityId": 7})):
            result = registry.call(name, args, make_state())
            self.assertTrue(result.success)
            self.assertEqual(result.tool_name, name)
            self.assertNotIn("reference-owner", repr(result))

    def test_ownership_and_missing_are_indistinguishable(self):
        registry = make_registry()
        state = make_state()
        state.authenticated_user_id = "another"
        forbidden = registry.call("get_order_facts", {"outTradeNo": "o-7"}, state)
        absent = registry.call("get_order_facts", {"outTradeNo": "absent"}, state)
        self.assertEqual(forbidden.error_code, absent.error_code)
        self.assertEqual(forbidden.error_message, absent.error_message)

    def test_contract_error_and_unexpected(self):
        data = fixtures()
        data[("activity", 7)]["data"] = {"activity": {"status": 1}}
        result = make_registry(ReferenceStub(data)).call("get_activity_facts", {"activityId": 7}, make_state())
        self.assertEqual(result.error_code, "TOOL_CONTRACT_FAILURE")
        class BrokenClient:
            def get_activity_facts(self, entity, auth):
                raise RuntimeError("secret SQL stack")
        result = ActivityFactsTool(BrokenClient()).run({"activityId": 7}, make_state())
        self.assertEqual(result.error_code, "TOOL_UNEXPECTED_ERROR")
        self.assertNotIn("SQL", repr(result))
