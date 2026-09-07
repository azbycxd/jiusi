"""B 层确定性 EvidenceObligationEvaluator；不调用 LLM，也不解释事实值。"""
from .evidence_obligation import (
    EvidenceMatchMode,
    ObligationEvaluation,
    ObligationStatus,
)
from ..observations.evidence import EvidenceRegistry


class EvidenceObligationEvaluator:
    """从当前有效 Observation 重建 Registry，并逐 Condition 检查路径存在性。"""

    @staticmethod
    def _alias(evidence):
        return f"{evidence.tool_name}.{evidence.path}"

    def _matches(self, condition, evidence):
        alias = self._alias(evidence)
        for accepted in condition.accepted_paths:
            if condition.match_mode is EvidenceMatchMode.EXACT and alias == accepted:
                return True
            if condition.match_mode is EvidenceMatchMode.PREFIX and alias.startswith(accepted):
                return True
        return False

    @staticmethod
    def _current_observations(skill, observations):
        """复用 Skill ContextPolicy 并按 Tool 保留最新版本，避免过期事实满足义务。"""
        selected = skill.select_observations(observations)
        latest = {}
        for observation in selected:
            previous = latest.get(observation.tool_name)
            rank = (observation.sequence_no, observation.created_at)
            previous_rank = ((previous.sequence_no, previous.created_at)
                             if previous is not None else (-1, ""))
            if rank > previous_rank:
                latest[observation.tool_name] = observation
        return tuple(latest.values())

    def evaluate(self, skill, progress, observations):
        """返回所有 query-scoped required dimensions 的新评估，不原地修改 State。"""
        if progress is None:
            raise ValueError("缺少 SkillProgress")
        if not set(progress.required_dimensions) <= set(skill.possible_dimensions):
            raise ValueError("required_dimensions 超出 Skill possible_dimensions")
        registry = EvidenceRegistry()
        for observation in self._current_observations(skill, observations):
            registry.register_observation(observation)
        available = registry.list_available()
        evaluations = []
        for dimension in sorted(progress.required_dimensions):
            obligation = skill.evidence_obligation(dimension)
            satisfied = []
            missing = []
            for condition in obligation.conditions:
                matches = tuple(
                    item.evidence_id for item in available if self._matches(condition, item)
                )
                if matches:
                    satisfied.append((condition.name, matches))
                else:
                    missing.append(condition.name)
            status = ObligationStatus.SATISFIED if not missing else ObligationStatus.PENDING
            evaluations.append(ObligationEvaluation(
                dimension=dimension,
                status=status,
                satisfied_evidence=tuple(satisfied),
                missing_conditions=tuple(missing),
            ))
        return tuple(evaluations)
