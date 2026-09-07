"""【A 当前真实实现映射】规则知识与实时 Facts 的使用边界。"""
from enum import Enum


class KnowledgePolicy(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    NONE = "NONE"

    def permits_retrieval(self):
        """NONE 禁止规则检索，其余值只表达是否需要，不替代实时 Facts。"""
        return self is not KnowledgePolicy.NONE

    def requires_evidence(self):
        """REQUIRED 时规则 Evidence 是回答完成条件。"""
        return self is KnowledgePolicy.REQUIRED
