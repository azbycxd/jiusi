"""订单上下文只保留订单事实和可选规则证据。"""


def select(observations):
    return [item for item in observations
            if item.tool_name in {"get_order_facts", "search_group_buy_rules"}]
