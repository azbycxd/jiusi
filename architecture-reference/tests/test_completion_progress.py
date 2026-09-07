import unittest
from _core_support import skill_registry
from _support import observation
from src.progress.evaluator import EvidenceObligationEvaluator


class CompletionProgressTests(unittest.TestCase):
    def test_open_diagnosis_needs_two_dimensions(self):
        skill=skill_registry().get("participation_diagnosis"); p=skill.create_progress("为什么参加不了")
        facts={"eligibility":{"participation_limit_reached":True,
                "tag_participation_allowed":False,"market_downgraded":False,
                "user_within_release_range":True}}
        evaluations=EvidenceObligationEvaluator().evaluate(
            skill,p,(observation(facts,"get_user_eligibility_facts"),))
        p.apply_evaluations(evaluations)
        self.assertFalse(skill.is_complete(p)); self.assertEqual(p.remaining_dimensions,{"activity_validity"})
    def test_control_query_needs_one_dimension(self):
        skill=skill_registry().get("participation_diagnosis"); p=skill.create_progress("活动是否还在有效期内？")
        self.assertEqual(p.required_dimensions,{"activity_validity"})


if __name__ == "__main__": unittest.main()
