"""候选团队查询专用中文 Prompt。"""
PROMPT = """
【任务目标】判断指定活动当前是否存在可加入的拼团队伍。
必须获得候选团队集合的实时 Observation，具体能力从可用 Tool metadata 选择。
candidate_teams=[] 表示查询成功且当前没有候选团队，不是 Tool 失败。
target_count、complete_count 等统计字段不是“可加入团队数量”，不得混淆。
查询成功后停止，不调用订单或资格 Tool；规则仅在解释条件时可选。
""".strip()
