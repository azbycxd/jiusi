"""SkillSpec 的显式注册表；Router 选谁，Registry 负责找到谁。"""
from .base import SkillSpec


class SkillRegistry:
    def __init__(self, skills=()):
        self._items = {}
        for skill in skills:
            self.register(skill)

    def register(self, skill: SkillSpec):
        if not isinstance(skill, SkillSpec) or not skill.name:
            raise TypeError("只允许注册具名 SkillSpec")
        if skill.name in self._items:
            raise ValueError("Skill 名称重复")
        self._items[skill.name] = skill
        return skill

    def get(self, name: str) -> SkillSpec:
        if name not in self._items:
            raise KeyError("Skill 未注册")
        return self._items[name]

    def find_by_intent(self, intent) -> SkillSpec | None:
        value = getattr(intent, "value", intent)
        matches = [skill for skill in self._items.values() if value in skill.intents]
        if len(matches) > 1:
            raise ValueError("一个 Intent 匹配多个 Skill")
        return matches[0] if matches else None

    def list_skills(self):
        return tuple(self._items.values())

    def names(self):
        return tuple(self._items)

    def describe(self, names=None):
        selected = self.names() if names is None else names
        return tuple({
            "name": self.get(name).name,
            "description": self.get(name).description,
            "required_entities": self.get(name).required_entities,
            "allowed_tools": self.get(name).allowed_tools,
        } for name in selected)

    def candidate_skills(self, query: str = ""):
        """四 Skill 阶段返回轻量描述；百 Skill 候选检索属于生产扩展。"""
        return self.describe()
