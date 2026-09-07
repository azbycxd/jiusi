import unittest
from _core_support import core_registry, skill_registry
from _support import make_state
from src.context.builder import ContextBuilder


class ContextSecurityTests(unittest.TestCase):
    def test_auth_never_projected(self):
        skill=skill_registry().get("order_diagnosis"); state=make_state(skill)
        text=repr(ContextBuilder().build(state,skill,core_registry()))
        self.assertNotIn("reference-owner",text); self.assertNotIn("authenticated_user_id",text)


if __name__ == "__main__": unittest.main()
