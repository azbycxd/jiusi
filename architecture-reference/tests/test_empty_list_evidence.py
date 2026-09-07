"""空集合回归：查询成功→Observation→合法证据。"""
import unittest
from _support import *

class EmptyListTests(unittest.TestCase):
    def test_java_style_alias_normalized_without_falsey_loss(self):
        data = fixtures()
        data[("joinable", 7)]["data"] = {"candidateTeams": []}
        registry = make_registry(ReferenceStub(data))
        result = registry.call("get_joinable_team_facts", {"activityId": 7}, make_state())
        self.assertTrue(result.success)
        obs = ObservationFactory().create(result)
        self.assertEqual(obs.get_path("candidate_teams"), [])
        self.assertEqual(obs.evidence[0].path, "candidate_teams")

    def test_empty_list_survives_full_chain(self):
        result = make_registry().call("get_joinable_team_facts", {"activityId": 7}, make_state())
        obs = ObservationFactory().create(result)
        registry = EvidenceRegistry()
        registry.register_observation(obs)
        alias = "get_joinable_team_facts.candidate_teams"
        self.assertTrue(registry.exists(alias))
        self.assertEqual(registry.resolve(alias).value, [])
        self.assertFalse(registry.exists(alias+"[0]"))

    def test_falsey_values_all_retained(self):
        obs = observation({"zero": 0, "flag": False, "missing": None, "empty": []})
        self.assertEqual(len(obs.evidence), 4)
