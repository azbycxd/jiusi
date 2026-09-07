import unittest
from src.decision.actions import DecisionAction
from src.decision.schemas import AnswerDecision, RequestInputDecision, ToolCallDecision
from src.decision.validator import DecisionValidationError, DecisionValidator


class DecisionSchemaTests(unittest.TestCase):
    def setUp(self): self.validator=DecisionValidator()
    def test_tool(self): self.assertIsInstance(self.validator.parse({"action":"CALL_TOOL","tool_name":"x","tool_arguments":{}}),ToolCallDecision)
    def test_answer(self): self.assertEqual(self.validator.parse({"action":"ANSWER","answer":"a","used_evidence":["x.y"]}).action,DecisionAction.ANSWER)
    def test_request_input(self): self.assertIsInstance(self.validator.parse({"action":"REQUEST_INPUT","missing_information":["activityId"],"question":"编号？"}),RequestInputDecision)
    def test_extra_rejected(self):
        with self.assertRaises(DecisionValidationError): self.validator.parse({"action":"HANDOFF","reason_code":"X","message":"m","reasoning":"secret"})


if __name__ == "__main__": unittest.main()
