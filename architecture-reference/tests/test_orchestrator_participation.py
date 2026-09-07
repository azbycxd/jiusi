import unittest
from _core_support import make_orchestrator, request
from src.agent.state import TaskStatus
from src.decision.schemas import AnswerDecision, ToolCallDecision


class ParticipationFlowTests(unittest.TestCase):
    def test_two_dimensions_then_grounded_answer(self):
        decisions=[ToolCallDecision("get_activity_facts",{"activityId":7}),
                   ToolCallDecision("get_user_eligibility_facts",{"activityId":7}),
                   AnswerDecision("活动已关闭且资格次数已达上限。",("get_activity_facts.activity.status","get_user_eligibility_facts.eligibility.participation_limit_reached"))]
        agent,model,_,_=make_orchestrator(decisions)
        state=agent.handle_request(request("为什么我参加不了活动7"))
        self.assertEqual(state.task_status,TaskStatus.COMPLETED)
        self.assertFalse(state.skill_progress.remaining_dimensions); self.assertEqual(len(model.contexts),3)


if __name__ == "__main__": unittest.main()
