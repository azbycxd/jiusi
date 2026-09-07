def select(observations):
    return [item for item in observations
            if item.tool_name in {"get_joinable_team_facts", "search_group_buy_rules"}]
