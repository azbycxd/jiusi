"""失败不产生 Observation，业务限制不等于查询失败。"""
import unittest
from _support import *

class ObservationTests(unittest.TestCase):
    def test_failure_has_no_observation(self):
        result = ToolResult.failure_result("x", "TOOL_TIMEOUT", retryable=True)
        self.assertIsNone(ObservationFactory().create(result))

    def test_success_business_restriction(self):
        result = ToolResult.success_result("x", {"participation_limit_reached": True})
        obs = ObservationFactory().create(result)
        self.assertTrue(obs.get_path("participation_limit_reached"))

    def test_data_and_path_are_copied(self):
        data = {"teams": []}
        result = ToolResult.success_result("x", data)
        data["teams"].append("poison")
        obs = ObservationFactory().create(result)
        retrieved = obs.get_path("teams")
        retrieved.append("poison")
        self.assertEqual(obs.get_path("teams"), [])

    def test_internal_auth_fields_rejected(self):
        with self.assertRaises(ValueError):
            observation({"token": "must-not-be-evidence"})
