import unittest
from _core_support import core_registry, skill_registry
from _support import make_state
from src.observations.observation import ObservationFactory
from src.tools.tool_result import ToolResult
from src.context.selector import ContextSelector


class ContextConflictTests(unittest.TestCase):
    def test_latest_fact_wins_projection(self):
        skill=skill_registry().get("participation_diagnosis"); state=make_state(skill)
        factory=ObservationFactory()
        state.append_observation(factory.create(ToolResult.success_result("get_activity_facts",{"activity":{"status":"EFFECTIVE"}}),1))
        state.append_observation(factory.create(ToolResult.success_result("get_activity_facts",{"activity":{"status":"OVERDUE"}}),2))
        selected=ContextSelector().select(state,skill,core_registry())
        self.assertEqual(len(selected),1); self.assertEqual(selected[0].data["activity"]["status"],"OVERDUE")


if __name__ == "__main__": unittest.main()
