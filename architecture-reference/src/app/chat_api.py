"""Reference API：Request → Gateway → Orchestrator → 安全 Response。"""


class ChatApi:
    """不启动 FastAPI；authenticated_user_id 必须来自可信 HTTP 认证层。"""
    def __init__(self, gateway, orchestrator):
        self.gateway, self.orchestrator = gateway, orchestrator

    def post_chat(self, body, authenticated_user_id):
        if set(body) != {"session_id", "message"}:
            raise ValueError("Body 只允许 session_id 和 message")
        request = self.gateway.normalize(body["session_id"], body["message"],
                                         authenticated_user_id)
        state = self.orchestrator.handle_request(request)
        return {
            "task_id": state.task_id,
            "status": getattr(state.task_status, "value", state.task_status),
            "message": state.response_message,
            "missing_information": list(state.missing_information),
            "needs_human": getattr(state.task_status, "value", state.task_status) == "HANDOFF",
        }
