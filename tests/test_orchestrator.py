import pytest

from agent.orchestrator import OrderDiagnosisOrchestrator
from agent.state import AgentStatus
from eval.evaluator import run_v1_cases


def test_missing_order_then_resume_same_task() -> None:
    agent = OrderDiagnosisOrchestrator()
    first = agent.handle_message("session-1", "user-1", "我的拼团为什么没有成功？")
    assert first.status is AgentStatus.WAITING_USER
    second = agent.handle_message("session-1", "user-1", "202608240001")
    assert second.status is AgentStatus.FINISHED
    assert second.diagnosis_code == "GROUP_IN_PROGRESS"


@pytest.mark.parametrize(
    ("order_no", "status"),
    [
        ("202608240004", AgentStatus.FINISHED),
        ("202608240005", AgentStatus.HANDOFF),
        ("202608240006", AgentStatus.FAILED),
        ("202608240007", AgentStatus.HANDOFF),
        ("202608240008", AgentStatus.HANDOFF),
    ],
)
def test_stub_failure_and_handoff_paths(order_no: str, status: AgentStatus) -> None:
    state = OrderDiagnosisOrchestrator().handle_message("s-" + order_no, "user-1", f"查询拼团订单 {order_no}")
    assert state.status is status


def test_v1_eval_cases_have_expected_outcomes() -> None:
    metrics = run_v1_cases()
    assert metrics["task_success"] == 8
    # case_007's Tool succeeds but its unfamiliar Java reasonCode still requires HANDOFF.
    assert metrics["tool_success"] == 3
    assert metrics["handoff"] == 3
    assert metrics["retry_count"] == 2
