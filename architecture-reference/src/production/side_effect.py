"""【生产化扩展设计，当前真实项目未实现】写型 Tool 的审批、幂等、事务与补偿契约。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class WriteActionRequest:
    tool_name:str
    business_id:str
    user_confirmed:bool
    idempotency_key:str
    preconditions:tuple[str,...]


class WriteActionGuard:
    def validate(self,request,auth_context,authorization):
        if not getattr(auth_context,"authenticated_user_id",None): raise PermissionError("AUTH_REQUIRED")
        if not request.user_confirmed: raise PermissionError("USER_CONFIRMATION_REQUIRED")
        if not request.idempotency_key: raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        if not authorization.allowed: raise PermissionError("BUSINESS_AUTHORIZATION_DENIED")
        if not request.preconditions: raise ValueError("PRECONDITION_REQUIRED")
        return True


# NON_IDEMPOTENT_WRITE 失败不能只靠 Loop 重试；需 action journal、事务边界、Saga/
# compensation、结果核验和人工对账。当前五个 Tool 全为 READ_ONLY。
