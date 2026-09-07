"""从完整 State 选择当前 Skill/实体相关且最新的可信 Observation。"""
from datetime import datetime, timezone


class ContextSelector:
    """错误 ToolResult 不进入选择；同工具冲突默认只展示最新可信快照。"""
    def __init__(self, max_age_seconds: int | None = None):
        self.max_age_seconds = max_age_seconds

    @staticmethod
    def _contains(value, expected):
        if type(value) is type(expected) and value == expected:
            return True
        if isinstance(value, dict):
            return any(ContextSelector._contains(item, expected) for item in value.values())
        if isinstance(value, list):
            return any(ContextSelector._contains(item, expected) for item in value)
        return False

    def _entity_matches(self, observation, entities):
        if not entities:
            return True
        matched = [self._contains(observation.data, value) for value in entities.values()]
        return any(matched) or not any(
            key.lower().endswith("id") or key == "outTradeNo" for key in observation.data
        )

    def _fresh(self, observation, now):
        if self.max_age_seconds is None:
            return True
        created = datetime.fromisoformat(observation.created_at.replace("Z", "+00:00"))
        return (now-created).total_seconds() <= self.max_age_seconds

    def select(self, state, skill, tools, *, now=None):
        now = now or datetime.now(timezone.utc)
        candidates = []
        for observation in state.observations:
            try:
                tool = tools.get(observation.tool_name)
            except KeyError:
                continue
            if observation.tool_name not in skill.allowed_tools:
                continue
            if not self._fresh(observation, now):
                continue
            if not self._entity_matches(observation, getattr(state, "routing_entities", {})):
                continue
            candidates.append(observation)
        latest = {}
        for observation in candidates:
            key = observation.tool_name
            previous = latest.get(key)
            rank = (observation.sequence_no, observation.created_at)
            old_rank = (previous.sequence_no, previous.created_at) if previous else (-1, "")
            if rank > old_rank:
                latest[key] = observation
        return tuple(sorted(latest.values(), key=lambda item: item.sequence_no))
