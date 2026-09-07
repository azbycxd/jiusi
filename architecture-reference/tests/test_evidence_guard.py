"""精确路径、版本、原值与内部字段伪造测试。"""
import unittest
from dataclasses import replace
from _support import *
from src.harness.evidence_guard import EvidenceGuard
from src.harness.capability_guard import GuardViolation

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.obs = observation({"teams": [{"team_id": "T"}]})
        self.registry = EvidenceRegistry()
        self.registry.register_observation(self.obs)

    def test_array_path_and_fake_paths(self):
        valid = self.obs.tool_name + ".teams[0].team_id"
        self.assertEqual(EvidenceGuard().validate([valid], self.registry)[0].value, "T")
        for path in ("teams[1].team_id", "teams[-1].team_id", "available_tools", "source_files"):
            with self.subTest(path=path), self.assertRaises(GuardViolation):
                EvidenceGuard().validate([self.obs.tool_name+"."+path], self.registry)

    def test_forged_evidence_value(self):
        evidence = self.registry.list_available()[0]
        with self.assertRaises(GuardViolation):
            EvidenceGuard().validate([replace(evidence, value="forged")], self.registry)

    def test_bool_cannot_impersonate_integer_evidence(self):
        obs = observation({"count": 1})
        registry = EvidenceRegistry()
        registry.register_observation(obs)
        with self.assertRaises(GuardViolation):
            EvidenceGuard().validate([replace(obs.evidence[0], value=True)], registry)

    def test_same_tool_version_ambiguity(self):
        newer = observation({"teams": [{"team_id": "NEW"}]})
        self.registry.register_observation(newer)
        with self.assertRaises(KeyError):
            self.registry.resolve(self.obs.tool_name+".teams[0].team_id")
        self.assertEqual(self.registry.resolve(self.obs.evidence[0].evidence_id).value, "T")

    def test_context_metadata_not_registrable(self):
        with self.assertRaises(ValueError):
            observation({"source_files": ["internal.py"]})
