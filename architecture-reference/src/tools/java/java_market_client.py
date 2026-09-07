"""Java Facts 接口与离线 ReferenceStub；不导入任何 HTTP、MySQL、Redis 客户端。

A 层真实链：Python Tool → Java Facts HTTP API → Java Domain → Repository
→ MySQL/Redis。这里的 Protocol 映射接口职责，fixture 只是 B 层参考样例，
不表示实际数据库状态。生产响应还必须经过 HTTP、JSON、Envelope、code 校验。
Stub 只按显式键找数据，不默认返回一个成功空对象，不生成诊断结论。
"""
from copy import deepcopy
from typing import Protocol
from ..base import ToolExecutionError


class JavaMarketClient(Protocol):
    """身份只以 auth 参数传入，不与模型 arguments 合并。"""

    def get_order_facts(self, out_trade_no, auth):
        """返回规范订单对象或稳定 Client 错误。"""
        ...

    def get_activity_facts(self, activity_id, auth):
        """返回指定活动当前事实。"""
        ...

    def get_eligibility_facts(self, activity_id, auth):
        """返回当前可信用户在活动中的资格事实。"""
        ...

    def get_joinable_team_facts(self, activity_id, auth):
        """返回候选集合，包括合法空集合。"""
        ...


class ReferenceStub:
    """测试显式注入 fixture 与错误脚本；没有默认真实数据或网络后门。"""

    def __init__(self, fixtures=None, failures=None):
        self._fixtures = deepcopy(fixtures or {})
        self._failures = deepcopy(failures or {})
        self.calls = []

    def _fetch(self, operation, entity, auth):
        """按操作与实体查询；owner 再模拟 Java 二次权限校验。"""
        if not auth.authenticated_user_id:
            raise ToolExecutionError("AUTH_REQUIRED")
        self.calls.append((operation, entity))
        key = (operation, entity)
        queue = self._failures.get(key, [])
        if queue:
            code = queue.pop(0)
            if code:
                if code == "TOOL_TIMEOUT":
                    raise TimeoutError()
                if code == "TOOL_CONNECTION_ERROR":
                    raise ConnectionError()
                raise ToolExecutionError(code, code in {"HTTP_502", "HTTP_503"})
        item = self._fixtures.get(key)
        not_found = "ORDER_NOT_FOUND_OR_NOT_AUTHORIZED" if operation == "order" else "NOT_FOUND"
        if item is None:
            raise ToolExecutionError(not_found)
        if item.get("owner") not in (None, auth.authenticated_user_id):
            raise ToolExecutionError(not_found)
        return deepcopy(item["data"])

    def get_order_facts(self, out_trade_no, auth):
        """订单 fixture 不匹配与越权返回统一错误码。"""
        return self._fetch("order", out_trade_no, auth)

    def get_activity_facts(self, activity_id, auth):
        """活动 fixture 可以含过期、关闭等事实，仍属查询成功。"""
        return self._fetch("activity", activity_id, auth)

    def get_eligibility_facts(self, activity_id, auth):
        """资格限制是 data 字段，不是执行失败。"""
        return self._fetch("eligibility", activity_id, auth)

    def get_joinable_team_facts(self, activity_id, auth):
        """无候选团队用 candidate_teams=[] 表示查询成功。"""
        return self._fetch("joinable", activity_id, auth)
