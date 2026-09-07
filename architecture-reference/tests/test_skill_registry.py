import unittest
from _core_support import skill_registry
from src.routing.routing_result import Intent


class SkillRegistryTests(unittest.TestCase):
    def test_four_skills(self): self.assertEqual(len(skill_registry().list_skills()),4)
    def test_find_by_intent(self): self.assertEqual(skill_registry().find_by_intent(Intent.ORDER_DIAGNOSIS).name,"order_diagnosis")
    def test_describe_is_not_skill_object(self): self.assertIsInstance(skill_registry().describe()[0],dict)


if __name__ == "__main__": unittest.main()
