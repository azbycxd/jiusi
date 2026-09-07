import unittest
from _core_support import make_orchestrator, request
from src.agent.state import TaskStatus


class HandoffFlowTests(unittest.TestCase):
    def test_unknown_capability_handoff_without_model(self):
        agent,model,_,_=make_orchestrator([])
        state=agent.handle_request(request("请帮我修改数据库"))
        self.assertEqual(state.task_status,TaskStatus.HANDOFF); self.assertEqual(len(model.contexts),0)


if __name__ == "__main__": unittest.main()
