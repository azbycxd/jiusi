import unittest
from _core_support import core_registry, skill_registry
from _support import make_state, observation
from src.context.selector import ContextSelector


class ContextSelectorTests(unittest.TestCase):
    def test_unrelated_tool_removed(self):
        skill=skill_registry().get("participation_diagnosis"); state=make_state(skill)
        state.append_observation(observation()); state.append_observation(observation({"order":{"status":"CLOSE"}},"get_order_facts"))
        self.assertEqual([o.tool_name for o in ContextSelector().select(state,skill,core_registry())],["get_activity_facts"])
    def test_error_result_not_available(self):
        state=make_state(skill_registry().get("participation_diagnosis"))
        self.assertEqual(ContextSelector().select(state,skill_registry().get("participation_diagnosis"),core_registry()),())


if __name__ == "__main__": unittest.main()
