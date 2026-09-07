"""A 层 订单状态与拼团事实 Tool 的 Reference 实现。

由 Registry/Harness 调用；只接收 outTradeNo 业务参数。
公共 AgentTool.run 依次校验参数、提取可信身份、调用 _invoke、验证结果、
映射 timeout/connection/contract 错误；本模块不向模型暴露身份字段。
例如 业务状态不满足条件仍可以是一次成功查询。
"""
from ..base import AgentTool, RepeatPolicy
from ..arguments import OrderFactsArguments


class OrderFactsTool(AgentTool):
    """订单状态与拼团事实单一动作；Skill 决定它是否属于当前任务。"""

    name = "get_order_facts"
    description = "订单状态与拼团事实"
    arguments_type = OrderFactsArguments
    result_schema = {"order": dict}
    dimension = "order_state"
    repeat_policy = RepeatPolicy(repeatable=False, max_same_call=1)
    source = "reference_java_stub"

    def __init__(self, client):
        """注入 JavaMarketClient Protocol；Reference 默认不创建外部连接。"""
        self.client = client

    def _invoke(self, arguments, auth):
        """仅向指定 Client 方法传递规范实体和可信身份上下文。"""
        return self.client.get_order_facts(arguments.out_trade_no, auth)

    def validate_result(self, data):
        """公共 JSON 安全校验之后，再检查本业务对象的内部结构。"""
        result = super().validate_result(data)
        facts = result["order"]
        if not isinstance(facts.get("status"), str) or not facts["status"]:
            raise ValueError("业务对象缺少状态字段")
        return result
