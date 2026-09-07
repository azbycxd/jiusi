import unittest
from _core_support import core_registry, skill_registry
from _support import make_state, observation
from src.context.builder import ContextBuilder


class ContextBuilderTests(unittest.TestCase):
    def test_projection_reads_state(self):
        skill=skill_registry().get("participation_diagnosis"); state=make_state(skill)
        state.routing_entities={"activityId":7}; state.append_observation(observation())
        ctx=ContextBuilder().build(state,skill,core_registry())
        self.assertEqual(ctx.current_query,state.current_query); self.assertEqual(len(ctx.relevant_observations),1)
    def test_tools_are_skill_scoped(self):
        skill=skill_registry().get("order_diagnosis"); state=make_state(skill)
        names={item["name"] for item in ContextBuilder().build(state,skill,core_registry()).available_tools}
        self.assertEqual(names,{"get_order_facts","search_group_buy_rules"})


if __name__ == "__main__": unittest.main()
