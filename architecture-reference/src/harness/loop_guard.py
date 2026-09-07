"""A 层全局循环边界；用于开始新模型轮或新 Tool 调用前。

max_iterations 限制模型轮，max_tool_calls 包括自动 Retry 的实际调用。
预算恰好用完后仍允许在当前模型轮返回 ANSWER；不能错误阻断已经完成的答案。
Completion 判断信息充分，LoopGuard 仅防止资源无限消耗。
"""
from .capability_guard import GuardViolation


class LoopGuard:
    """输入计数采用已发生次数；将要发生的动作独立占用预算。"""

    def validate(self, state, budget, *, next_iteration=False, next_tool=False):
        """是否开始新轮由调用方显式声明，避免 <= / < 边界歧义。"""
        iterations = state.iteration_count + int(next_iteration)
        calls = state.tool_call_count + int(next_tool)
        if state.iteration_count < 0 or state.tool_call_count < 0:
            raise GuardViolation("LOOP_LIMIT", "非法控制计数")
        if iterations > budget["max_iterations"] or calls > budget["max_tool_calls"]:
            raise GuardViolation("LOOP_LIMIT", "循环或工具调用达到安全上限")
        return (iterations, calls)
