"""A 层规则检索 Tool 的参考边界；可接受离线 Retriever 或明确规则列表。

这里只组装检索结果，不扩展 Batch 3 的检索算法；无结果使用 rules=[]。
规则的来源标记与 Java Facts 分开，不能以规则推断当前订单或资格状态。
通用执行壳继承参数验证、可信上下文检查、结果校验和错误映射。
"""
from ..base import AgentTool
from ..arguments import RuleSearchArguments


class SearchGroupBuyRulesTool(AgentTool):
    """规则是稳定解释，不是实时实例事实。"""

    name = "search_group_buy_rules"
    description = "检索拼团规则条目，不查询实时业务状态"
    arguments_type = RuleSearchArguments
    result_schema = {"rules": list}
    dimension = "rule_evidence"
    source = "reference_rule_catalog"

    def __init__(self, retriever, entries=None):
        """entries 兼容已有 LexicalRetriever 的显式 Catalog 参数。"""
        self.retriever = retriever
        self.entries = entries

    def _invoke(self, arguments, auth):
        """只使用 query，不把身份放入检索文本或返回值。"""
        if self.entries is None:
            entries = self.retriever.search(arguments.query)
        else:
            entries = self.retriever.search(arguments.query, self.entries, top_k=3)
        if not isinstance(entries, (list, tuple)):
            raise ValueError("检索结果必须为条目集合")
        rules = []
        for entry in entries:
            if hasattr(entry, "model_visible"):
                # KnowledgeEntry 只投影业务知识；source_files 等治理字段留在 Catalog 侧。
                rules.append(entry.model_visible())
            else:
                # 兼容早期极简 Reference fixture，不扩散到生产 Contract。
                rules.append({"entry_id": entry.entry_id, "title": entry.title,
                              "content": entry.content})
        return {"rules": rules}

    def validate_result(self, data):
        """必须是规则条目对象；空列表有效，但不自动证明规则问答完成。"""
        result = super().validate_result(data)
        for entry in result["rules"]:
            identifier = entry.get("knowledge_id", entry.get("entry_id")) if isinstance(entry, dict) else None
            if not isinstance(identifier, str) or not all(
                isinstance(entry.get(key), str) for key in ("title", "content")
            ):
                raise ValueError("规则条目契约不匹配")
        return result
