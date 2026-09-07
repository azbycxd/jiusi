"""参数执行链溯源，与答案证据无关。"""
import unittest
from _support import *
from src.harness.parameter_grounding_guard import ParameterGroundingGuard
from src.harness.capability_guard import GuardViolation

class GroundingTests(unittest.TestCase):
    def test_user_input_and_runtime(self):
        for source in (SourceType.USER_INPUT, SourceType.RUNTIME):
            entry = ParameterProvenance("activityId", 7, source, "entity")
            ParameterGroundingGuard().validate({"activityId": 7}, [entry],
                user_values={"entity": 7}, runtime_values={"entity": 7}, observations=[])

    def test_order_to_joinable(self):
        obs = observation({"references": {"activity_id": 7}}, "get_order_facts")
        entry = ParameterProvenance("activityId", 7, SourceType.OBSERVATION,
                                    "references.activity_id", obs.observation_id)
        ParameterGroundingGuard().validate({"activityId": 7}, [entry], user_values={},
                                          runtime_values={}, observations=[obs])

    def test_forged_value_path_unknown_and_missing(self):
        for entries in ([], provenance(8), [ParameterProvenance("activityId", 7, SourceType.UNKNOWN, "x")],
                        [ParameterProvenance("activityId", 7, SourceType.OBSERVATION, "bad", "absent")]):
            with self.subTest(entries=entries), self.assertRaises(GuardViolation) as caught:
                ParameterGroundingGuard().validate({"activityId": 7}, entries,
                    user_values={"activityId": 7}, runtime_values={}, observations=[])
            self.assertEqual(caught.exception.code, "PARAMETER_GROUNDING_FAILED")
