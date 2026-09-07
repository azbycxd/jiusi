"""切题时旧 Task 暂停，新 Task 独立，允许后续切回。"""
import unittest
from _support import *
from src.memory.task_store import TaskStore

class TaskTests(unittest.TestCase):
    def test_switch_preserves_waiting_goal(self):
        store = TaskStore()
        first = store.create_task("s", "u", "为什么不能参与", task_id="a")
        first.mark_waiting_input(["activityId"])
        store.update_task(first)
        second = store.create_task("s", "u", "标签规则", task_id="b")
        self.assertEqual(store.get_active_task("s", "u").task_id, "b")
        resumed = store.resume_task("s", "u", "a")
        self.assertEqual(resumed.task_status, TaskStatus.WAITING_INPUT)
        self.assertEqual(resumed.pending_user_query, "为什么不能参与")
        self.assertEqual(second.observations, [])

    def test_identity_and_complete(self):
        store = TaskStore()
        store.create_task("s", "u", "问题", task_id="a")
        self.assertIsNone(store.get_task("s", "other", "a"))
        self.assertEqual(store.list_session_tasks("s", "other"), [])
        store.complete_task("s", "u", "a")
        self.assertIsNone(store.get_active_task("s", "u"))
        with self.assertRaises(ValueError):
            store.resume_task("s", "u", "a")

    def test_failed_switch_keeps_active(self):
        store = TaskStore()
        store.create_task("s", "u", "问题", task_id="a")
        with self.assertRaises(ValueError):
            store.switch_task("s", "u", "missing")
        self.assertEqual(store.get_active_task("s", "u").task_id, "a")
