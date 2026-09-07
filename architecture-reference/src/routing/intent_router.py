"""轻量 Rule First Router；低置信才使用结构化 LLM Stub。

Router 选择任务，DecisionModel 规划任务内下一步，SkillRegistry 只查找已注册
的 SkillSpec。四个 Skill 不值得每次先付出一次模型调用，因此组合实体模式、
业务表达和规则表达评分；单个关键词不会直接成为高置信结论。

【生产化扩展设计，当前真实项目未实现】Skill 达到数百个时可先做领域分层、
候选 Skill 检索，再对小候选集执行 LLM fallback。
"""
from dataclasses import dataclass
import re
from typing import Protocol, Sequence
from .routing_result import INTENT_TO_SKILL, Intent, RoutingResult, RoutingSource


@dataclass(frozen=True)
class RoutingContext:
    """WAITING_INPUT 时只给 Router 最小任务摘要，不暴露完整 State。"""
    current_intent: Intent | None = None
    current_skill: str | None = None
    missing_information: tuple[str, ...] = ()
    waiting_input: bool = False


class LLMIntentRouter(Protocol):
    """Reference Stub 协议；实现方返回结构化结果，不在这里接 Provider。"""
    def classify(self, query: str, candidate_skills: Sequence[object],
                 session_context_summary: RoutingContext | None) -> RoutingResult: ...


class ReferenceLLMIntentRouter:
    """测试可注入的确定性结果，不伪装成真实 LLM。"""
    def __init__(self, result: RoutingResult | None = None):
        self.result = result
        self.calls = []

    def classify(self, query, candidate_skills=(), session_context_summary=None):
        self.calls.append((query, tuple(candidate_skills), session_context_summary))
        return self.result or RoutingResult(
            Intent.UNKNOWN, None, reason_code="LLM_UNAVAILABLE",
            source=RoutingSource.FALLBACK,
        )


class RuleBasedIntentRouter:
    """通过多组信号加权分类，显式处理冲突、缺实体与补参。"""
    SIGNALS = {
        Intent.PARTICIPATION_DIAGNOSIS: (
            (3, re.compile(r"(?:参加|参与|报名|参团).{0,8}(?:不了|失败|不能|不成功)")),
            (2, re.compile(r"(?:为什么|为何).{0,12}(?:活动|参加|参与)")),
            (3, re.compile(r"有效期|是否有效|活动状态")),
            (3, re.compile(r"参与限制|参与资格|次数限制")),
        ),
        Intent.ORDER_DIAGNOSIS: (
            (3, re.compile(r"订单|下单|交易号")),
            (2, re.compile(r"没拼成|未成团|订单状态|拼团订单")),
        ),
        Intent.JOINABLE_TEAM: (
            (3, re.compile(r"(?:还有|查找|有没有|哪些).{0,8}(?:团|队伍)")),
            (2, re.compile(r"(?:可加入|能加入|候选团|拼团列表)")),
        ),
        Intent.RULE_QA: (
            (3, re.compile(r"规则|是什么意思|如何计算|怎么算|标签")),
            (1, re.compile(r"一般|通常|平台规定")),
        ),
    }

    def extract_entities(self, query: str) -> dict[str, object]:
        entities = {}
        activity = re.search(r"(?:活动|活动号|活动ID)\s*[:：#]?\s*(\d{1,20})", query, re.I)
        if activity:
            entities["activityId"] = int(activity.group(1))
        order = re.search(r"(?:订单|订单号|交易号)\s*[:：#]?\s*([A-Za-z0-9][A-Za-z0-9_-]{5,31})", query)
        if order:
            entities["outTradeNo"] = order.group(1)
        return entities

    def _scores(self, query, entities):
        scores = {intent: 0 for intent in self.SIGNALS}
        matches = {intent: [] for intent in self.SIGNALS}
        for intent, rules in self.SIGNALS.items():
            for weight, pattern in rules:
                if pattern.search(query):
                    scores[intent] += weight
                    matches[intent].append(pattern.pattern)
        if "activityId" in entities:
            scores[Intent.PARTICIPATION_DIAGNOSIS] += 1
            scores[Intent.JOINABLE_TEAM] += 1
        if "outTradeNo" in entities:
            scores[Intent.ORDER_DIAGNOSIS] += 2
        return scores, matches

    @staticmethod
    def _is_slot_reply(query, context, entities):
        if not context or not context.waiting_input or not context.missing_information:
            return False
        supplied = set(entities) & set(context.missing_information)
        compact = re.sub(r"[\s，。,:：#]", "", query)
        return bool(supplied) and len(compact) <= 40

    def route(self, query: str, context=None, candidate_skills=()) -> RoutingResult:
        if not isinstance(query, str) or not query.strip():
            return RoutingResult(Intent.UNKNOWN, None, reason_code="EMPTY_QUERY")
        query = query.strip()
        entities = self.extract_entities(query)
        if self._is_slot_reply(query, context, entities):
            intent = context.current_intent or Intent.UNKNOWN
            return RoutingResult(
                intent, INTENT_TO_SKILL.get(intent), entities, 0.98,
                "WAITING_INPUT_SLOT_REPLY", RoutingSource.RULE, False, ("slot_reply",),
            )
        scores, matches = self._scores(query, entities)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best, best_score = ranked[0]
        second_score = ranked[1][1]
        if best_score == 0 or (best_score == second_score and best_score < 5):
            return RoutingResult(
                Intent.UNKNOWN, None, entities, 0.2 if best_score else 0.0,
                "AMBIGUOUS_INTENT" if best_score else "NO_BUSINESS_SIGNAL",
                RoutingSource.RULE,
            )
        confidence = min(0.98, 0.50 + best_score * 0.09 + (best_score-second_score)*0.04)
        current = context.current_intent if context else None
        switched = bool(context and context.waiting_input and current and best is not current)
        return RoutingResult(
            best, INTENT_TO_SKILL[best], entities, confidence,
            "INTENT_SWITCH" if switched else "RULE_SIGNALS_AGREE",
            RoutingSource.RULE, switched, tuple(matches[best]),
        )


class CompositeIntentRouter:
    """规则高置信直出；中低置信调用可选 Stub；失败稳定返回 UNKNOWN。"""
    def __init__(self, rule=None, fallback: LLMIntentRouter | None = None, threshold=0.80):
        self.rule = rule or RuleBasedIntentRouter()
        self.fallback = fallback
        self.threshold = threshold

    def route(self, query: str, context=None, candidate_skills=()) -> RoutingResult:
        result = self.rule.route(query, context, candidate_skills)
        if result.confidence >= self.threshold or self.fallback is None:
            return result
        fallback = self.fallback.classify(query, candidate_skills, context)
        if fallback.intent is Intent.UNKNOWN:
            return RoutingResult(
                Intent.UNKNOWN, None, result.entities,
                max(result.confidence, fallback.confidence),
                "ROUTER_FALLBACK_UNKNOWN", RoutingSource.FALLBACK,
            )
        current = context.current_intent if context else None
        return RoutingResult(
            fallback.intent, fallback.skill_name, fallback.entities,
            fallback.confidence, fallback.reason_code, RoutingSource.LLM,
            bool(context and context.waiting_input and current and fallback.intent is not current),
            fallback.matched_signals,
        )
