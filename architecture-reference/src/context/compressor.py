"""语义保真的轻量 Context 压缩；不实现复杂摘要或真实 tokenizer。"""
from dataclasses import replace
import json


class ContextCompressor:
    """只删除低优先级重复项；Evidence、实体、Progress、Schema 不可改写。"""
    def estimate_tokens(self, value) -> int:
        text = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
        return max(1, (len(text) + 3) // 4)

    def trim_observations(self, observations, budget_tokens):
        retained = []
        used = 0
        for observation in reversed(observations):
            cost = self.estimate_tokens(observation.data)
            if retained and used + cost > budget_tokens:
                continue
            retained.append(observation)
            used += cost
        return tuple(reversed(retained))

    def compress_text(self, text: str, limit=1200):
        """只截断旧解释文本；业务事实不走这个入口。"""
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "…[低优先级说明已截断]"

    def fit(self, context, budget):
        observations = self.trim_observations(context.relevant_observations,
                                              budget.observation_budget)
        # Evidence 从保留下来的快照重建，避免留下已压缩 Observation 的孤儿引用。
        ids = {item.observation_id for item in observations}
        evidence = tuple(item for item in context.available_evidence
                         if item.observation_id in ids)
        estimate = self.estimate_tokens({
            "query": context.current_query,
            "instructions": context.skill_instructions,
            "observations": [item.data for item in observations],
            "evidence": [item.evidence_id for item in evidence],
            "progress": context.skill_progress,
            "tools": context.available_tools,
        })
        if estimate > budget.max_estimated_tokens:
            raise ValueError("CONTEXT_BUDGET_EXCEEDED")
        return replace(context, relevant_observations=observations,
                       available_evidence=evidence, estimated_tokens=estimate)
