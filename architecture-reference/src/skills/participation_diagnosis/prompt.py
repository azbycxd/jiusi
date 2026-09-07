"""参与失败诊断专用中文 Prompt。"""
PROMPT = """
【任务目标】找出用户当前不能参加指定活动的原因。
【完成语义】开放式诊断需要活动有效性与用户资格两个独立 Evidence Requirement。
没有固定 Tool 顺序，应根据当前 Observation、缺失 Condition 与可用 Tool metadata 选择下一步。
找到一个成立原因不代表开放式诊断完成；仍有 Required Evidence 时继续取证。
维度完成后立即停止，不得扩展查询候选团队等无关能力。
规则知识仅在用户目标确实需要解释时使用，不能替代活动或资格实时事实。
""".strip()
