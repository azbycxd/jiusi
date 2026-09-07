"""Decision JSON 的软约束；真正 Schema/权限/Evidence 校验由 Harness 执行。"""

DECISION_CONTRACT_PROMPT = """
【输出总则】
只返回一个 JSON 对象，不增加 Markdown、解释或额外字段。action 只能是以下四种。

【CALL_TOOL】
字段：action、tool_name、tool_arguments。
示例：{"action":"CALL_TOOL","tool_name":"<从available_tools选择>",
       "tool_arguments":{"<schema字段>":"<有来源的值>"}}
tool_arguments 的合法字段只看当前 Tool Schema；不得添加 userId、Header 或 URL。

【ANSWER】
字段：action、answer、used_evidence。used_evidence 必须是非空证据引用数组。
示例：{"action":"ANSWER","answer":"基于已观察事实的回答。",
       "used_evidence":["<tool_name>.<fact_path>"]}

【REQUEST_INPUT】
字段：action、missing_information、question。只能请求 Tool Schema 允许由用户提供的
业务实体，例如 activityId、outTradeNo；不得请求身份、Token、SQL 等受保护字段。
示例：{"action":"REQUEST_INPUT","missing_information":["activityId"],
       "question":"请提供活动编号。"}

【HANDOFF】
字段：action、reason_code、message。
示例：{"action":"HANDOFF","reason_code":"CAPABILITY_UNAVAILABLE",
       "message":"当前能力无法可靠处理该问题，建议转人工。"}

【非法示例】
CALL_TOOL 同时带 answer；ANSWER 没有 used_evidence；REQUEST_INPUT 请求 userId；
Tool 参数带 Schema 外字段；返回第五种 action；添加 reasoning 或隐藏思维字段。

以上是 Prompt 软约束，不构成安全边界。Runtime/Harness 必须再次执行严格解析、
Extra Field reject、Capability、身份、参数来源、完成度与 Evidence 校验。
""".strip()
