"""A 层可信身份边界；模型只能提供业务参数，不能配置运行环境。

Prompt 提醒不能阻止 user_id、authenticatedUserId 或嵌套 Header 注入。
Guard 在动作前递归检查字段；AuthContext 由已有 RequestContext/AgentState 构造。
Python 内对象本身不是密码学认证：生产仍需可信 Gateway 完成认证。
Reference 的 AuthContext 不进入 Tool Schema、Observation 或 Trace。
"""
from dataclasses import dataclass, field
from ..observations.observation import normalize_key
from .capability_guard import GuardViolation

PROTECTED = {"userid", "authenticateduserid", "token", "authorization", "header",
             "headers", "sql", "rediskey", "baseurl", "apikey", "password"}


@dataclass(frozen=True)
class AuthContext:
    """只提供给 Client 的可信身份；repr 避免意外日志泄漏。"""

    authenticated_user_id: str = field(repr=False)


class IdentityGuard:
    """模型输入检查与可信身份注入两个入口分开，绝不合并模型参数。"""

    def validate_model_arguments(self, arguments):
        """递归拒绝受保护键名，不通过删除字段来容忍注入。"""
        if isinstance(arguments, dict):
            for key, value in arguments.items():
                if normalize_key(key) in PROTECTED:
                    raise GuardViolation("IDENTITY_BOUNDARY_VIOLATION", "不允许模型控制认证或基础设施")
                self.validate_model_arguments(value)
        elif isinstance(arguments, list):
            for value in arguments:
                self.validate_model_arguments(value)

    def build_auth_context(self, trusted_context):
        """仅读取可信对象属性；缺失身份稳定拒绝，不从 arguments 寻找替代。"""
        identity = getattr(trusted_context, "authenticated_user_id", None)
        if not isinstance(identity, str) or not identity.strip():
            raise GuardViolation("AUTH_REQUIRED", "缺少可信认证上下文")
        return AuthContext(identity)
