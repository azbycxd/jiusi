"""可信请求上下文；Gateway 创建；模型不可见；映射真实认证边界。"""
from dataclasses import dataclass
@dataclass(frozen=True)
class RequestContext: session_id:str; authenticated_user_id:str; message:str
