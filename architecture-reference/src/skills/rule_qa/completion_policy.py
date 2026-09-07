"""Rule QA 只有真正召回至少一条规则 Evidence 才满足。"""
from ...progress.requirements import ResolvedRequirements
from ...progress.evidence_obligation import (
    EvidenceCondition,
    EvidenceMatchMode,
    EvidenceObligationSpec,
)


POSSIBLE_DIMENSIONS = ("rule_evidence",)
EVIDENCE_OBLIGATIONS = (
    EvidenceObligationSpec("rule_evidence", (
        EvidenceCondition("rule_content", (
            "search_group_buy_rules.rules[",
        ), EvidenceMatchMode.PREFIX),
    )),
)


def resolve_requirements(_query, *, routing_intent=None, routing_entities=None):
    return ResolvedRequirements(frozenset({"rule_evidence"}), ("QUERY_RULE_EVIDENCE",))


def complete(progress):
    return progress.complete
