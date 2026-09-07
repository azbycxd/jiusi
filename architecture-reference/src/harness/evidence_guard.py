"""A 层答案证据检查；只接受当前 Observation EvidenceRegistry 的引用。

例如候选团队结果为 []，candidate_teams 路径存在且合法；
candidate_teams[0] 不存在时必须拒绝，不允许 Python 负索引语义。
available_tools、source_files 和自报文案不是业务 Evidence。
这能检查来源与原值，不能声称证明任意自然语言答案的全部逻辑正确性。
"""
from .capability_guard import GuardViolation


class EvidenceGuard:
    """在 ANSWER 前解析精确证据版本；业务回答默认必须引用至少一项。"""

    def validate(self, used_evidence, registry, *, required=True):
        """不存在路径、错索引、篡改值或歧义版本均稳定拒绝。"""
        if not isinstance(used_evidence, (list, tuple)):
            raise GuardViolation("EVIDENCE_NOT_AVAILABLE", "证据引用必须是列表")
        if required and not used_evidence:
            raise GuardViolation("EVIDENCE_NOT_AVAILABLE", "业务回答缺少证据")
        try:
            return registry.validate_used_evidence(used_evidence)
        except (KeyError, ValueError, TypeError, AttributeError):
            raise GuardViolation("EVIDENCE_NOT_AVAILABLE", "证据路径或原值不可用") from None
