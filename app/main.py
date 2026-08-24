from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from agent.orchestrator import OrderDiagnosisOrchestrator


app = FastAPI(title="Group Buy Agent", version="0.1.0")
orchestrator = OrderDiagnosisOrchestrator()


class ChatRequest(BaseModel):
    """Untrusted client input. Identity is deliberately not part of this model."""

    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "v1-stub"}


@app.post("/v1/chat")
def chat(request: ChatRequest, x_authenticated_user_id: str | None = Header(default=None)) -> dict:
    if not x_authenticated_user_id:
        raise HTTPException(status_code=401, detail="missing trusted authentication context")
    state = orchestrator.handle_message(
        session_id=request.session_id,
        authenticated_user_id=x_authenticated_user_id,
        user_query=request.message,
    )
    return {
        "session_id": state.session_id,
        "status": state.status.value,
        "answer": state.final_answer,
        "missing_fields": state.missing_fields,
        "needs_human": state.needs_human,
    }
