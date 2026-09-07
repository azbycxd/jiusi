import unittest
from _core_support import make_orchestrator, request
from src.agent.state import TaskStatus
from src.decision.schemas import AnswerDecision, RequestInputDecision, ToolCallDecision


class RequestInputFlowTests(unittest.TestCase):
    def test_same_session_resume(self):
        decisions=[RequestInputDecision(("activityId",),"请提供活动编号。"),
                   ToolCallDecision("get_activity_facts",{"activityId":7}),
                   ToolCallDecision("get_user_eligibility_facts",{"activityId":7}),
                   AnswerDecision("已完成两维诊断。",("get_activity_facts.activity.status","get_user_eligibility_facts.eligibility.participation_limit_reached"))]
        agent,_,_,_=make_orchestrator(decisions)
        first=agent.handle_request(request("为什么我参加不了这个活动？"))
        self.assertEqual(first.task_status,TaskStatus.WAITING_INPUT)
        second=agent.handle_request(request("活动7"))
        self.assertEqual(second.task_id,first.task_id); self.assertEqual(second.task_status,TaskStatus.COMPLETED)


if __name__ == "__main__": unittest.main()
