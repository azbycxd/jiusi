from pydantic import BaseModel, Field


class AuthContext(BaseModel):
    """Trusted identity injected by transport/auth middleware, never tool arguments."""

    authenticated_user_id: str = Field(min_length=1)
