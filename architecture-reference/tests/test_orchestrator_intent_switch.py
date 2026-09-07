import unittest
from _core_support import make_orchestrator, request
from src.agent.state import TaskStatus
from src.decision.schemas import HandoffDecision, RequestInputDecision


class IntentSwitchFlowTests(unittest.TestCase):
    def test_waiting_task_paused_and_new_task_clean(self):
        agent,_,_,tasks=make_orchestrator([RequestInputDecision(("activityId",),"活动号？"),HandoffDecision("DEMO","演示结束")])
        old=agent.handle_request(request("为什么我参加不了这个活动？"))
        new=agent.handle_request(request("算了，查订单644398015396"))
        self.assertNotEqual(old.task_id,new.task_id); self.assertEqual(new.active_skill,"order_diagnosis")
        self.assertEqual(new.observations,[]); self.assertIsNotNone(tasks.get_task(old.session_id,old.authenticated_user_id,old.task_id))


if __name__ == "__main__": unittest.main()
