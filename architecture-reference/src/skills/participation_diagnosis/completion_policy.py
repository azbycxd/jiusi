"""Participation 的 Query Requirement 与 Evidence Obligation；不表达 Tool 顺序。"""
from ...progress.requirements import ResolvedRequirements
from ...progress.evidence_obligation import (
    EvidenceCondition,
    EvidenceMatchMode,
    EvidenceObligationSpec,
)


POSSIBLE_DIMENSIONS = (
    "activity_validity",
    "user_eligibility",
    "rule_explanation",
)

EVIDENCE_OBLIGATIONS = (
    EvidenceObligationSpec("activity_validity", (
        EvidenceCondition("activity_status", (
            "get_activity_facts.activity.status",
        )),
        EvidenceCondition("within_valid_time", (
            "get_activity_facts.activity.within_valid_time",
        )),
    )),
    EvidenceObligationSpec("user_eligibility", (
        EvidenceCondition("participation_limit_reached", (
            "get_user_eligibility_facts.eligibility.participation_limit_reached",
        )),
        EvidenceCondition("tag_participation_allowed", (
            "get_user_eligibility_facts.eligibility.tag_participation_allowed",
        )),
        EvidenceCondition("market_downgraded", (
            "get_user_eligibility_facts.eligibility.market_downgraded",
        )),
        EvidenceCondition("user_within_release_range", (
            "get_user_eligibility_facts.eligibility.user_within_release_range",
        )),
    )),
    EvidenceObligationSpec("rule_explanation", (
        EvidenceCondition("rule_content", (
            "search_group_buy_rules.rules[",
        ), EvidenceMatchMode.PREFIX),
    )),
)


def resolve_requirements(query, *, routing_intent=None, routing_entities=None):
    """只依据问题与基础路由语义裁剪 Required；额外参数不含可信身份。"""
    text = query or ""
    if any(term in text for term in ("有效期", "是否有效", "活动状态")):
        return ResolvedRequirements(frozenset({"activity_validity"}),
                                    ("QUERY_ACTIVITY_VALIDITY",))
    if any(term in text for term in ("参与限制", "资格", "次数限制")) and "为什么" not in text:
        return ResolvedRequirements(frozenset({"user_eligibility"}),
                                    ("QUERY_USER_ELIGIBILITY",))
    if any(term in text for term in ("规则", "规定", "条款")) and not any(
        term in text for term in ("为什么", "参加不了", "不能参加")
    ):
        return ResolvedRequirements(frozenset({"rule_explanation"}),
                                    ("QUERY_RULE_EXPLANATION",))
    return ResolvedRequirements(
        frozenset({"activity_validity", "user_eligibility"}),
        ("OPEN_PARTICIPATION_DIAGNOSIS",),
    )


def complete(progress):
    return progress.complete
