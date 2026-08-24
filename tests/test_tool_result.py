from tools.schemas import ToolResult


def test_tool_result_distinguishes_retryable_business_outcome() -> None:
    result = ToolResult.infrastructure_failure("JAVA_TIMEOUT", "超时", retryable=True, source="java_facade")
    assert result.success is False
    assert result.error_code == "JAVA_TIMEOUT"
    assert result.retryable is True
    assert result.data == {}
