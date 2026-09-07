"""按 Skill 能力源选择事实；不读取 Possible/Required Progress Dimension。"""
ALLOWED_TOOLS = frozenset({
    "get_activity_facts",
    "get_user_eligibility_facts",
    "search_group_buy_rules",
})


def select(observations):
    return [item for item in observations if item.tool_name in ALLOWED_TOOLS]
