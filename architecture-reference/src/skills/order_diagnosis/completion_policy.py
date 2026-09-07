"""Order Skill 的最小 v1.1 迁移：订单状态事实足以完成当前实例问题。"""
from ...progress.requirements import ResolvedRequirements
from ...progress.evidence_obligation import EvidenceCondition, EvidenceMatchMode, EvidenceObligationSpec


POSSIBLE_DIMENSIONS = ("order_state", "rule_explanation")
EVIDENCE_OBLIGATIONS = (
    EvidenceObligationSpec("order_state", (
        EvidenceCondition("order_status", ("get_order_facts.order.status",)),
    )),
    EvidenceObligationSpec("rule_explanation", (
        EvidenceCondition("rule_content", ("search_group_buy_rules.rules[",),
                          match_mode=EvidenceMatchMode.PREFIX),
    )),
)


def resolve_requirements(_query, *, routing_intent=None, routing_entities=None):
    return ResolvedRequirements(frozenset({"order_state"}), ("QUERY_ORDER_STATE",))


def complete(progress):
    return progress.complete
