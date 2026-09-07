"""同身份恢复、跨身份隔离与快照版本。"""
import unittest
from types import SimpleNamespace
from _support import *
from src.memory.session_memory import SessionMemory

class SessionTests(unittest.TestCase):
    def test_deepcopy_load_and_save(self):
        memory = SessionMemory()
        state = make_state()
        memory.save(state)
        state.missing_information.append("tamper")
        loaded = memory.load("s", "reference-owner")
        self.assertEqual(loaded.missing_information, [])
        loaded.missing_information.append("again")
        self.assertEqual(memory.load("s", "reference-owner").missing_information, [])

    def test_same_session_resume_and_identity(self):
        memory = SessionMemory()
        state = make_state()
        state.mark_waiting_input(["activityId"])
        memory.save(state)
        self.assertIsNone(memory.load("s", "other"))
        resumed = memory.resume("s", "reference-owner", "活动是 7")
        self.assertIn("为什么不能参与", resumed.current_query)
        self.assertIn("活动是 7", resumed.current_query)
        self.assertEqual(resumed.task_status, TaskStatus.REASONING)
        self.assertEqual(resumed.missing_information, [])

    def test_version_and_delete(self):
        memory = SessionMemory()
        saved = memory.save(make_state(), expected_version=0)
        memory.save(saved, expected_version=saved.state_version)
        with self.assertRaises(ValueError):
            memory.save(saved, expected_version=saved.state_version)
        self.assertFalse(memory.delete("s", "other"))
        self.assertTrue(memory.delete("s", "reference-owner"))

    def test_new_identity_never_inherits(self):
        memory = SessionMemory()
        state = make_state()
        state.mark_waiting_input(["activityId"])
        memory.save(state)
        new = memory.load_or_create(SimpleNamespace(session_id="s", authenticated_user_id="new", message="新问题"))
        self.assertEqual(new.current_query, "新问题")
        self.assertEqual(new.observations, [])
