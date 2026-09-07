"""Joinable Team 的完成条件是候选集合已被观察；空集合仍是完整事实。"""
from ...progress.requirements import ResolvedRequirements
from ...progress.evidence_obligation import EvidenceCondition, EvidenceMatchMode, EvidenceObligationSpec


POSSIBLE_DIMENSIONS = ("candidate_team_availability", "rule_explanation")
EVIDENCE_OBLIGATIONS = (
    EvidenceObligationSpec("candidate_team_availability", (
        EvidenceCondition("candidate_teams", (
            "get_joinable_team_facts.candidate_teams",
        )),
    )),
    EvidenceObligationSpec("rule_explanation", (
        EvidenceCondition("rule_content", ("search_group_buy_rules.rules[",),
                          match_mode=EvidenceMatchMode.PREFIX),
    )),
)


def resolve_requirements(_query, *, routing_intent=None, routing_entities=None):
    return ResolvedRequirements(frozenset({"candidate_team_availability"}),
                                ("QUERY_CANDIDATE_TEAMS",))


def complete(progress):
    return progress.complete
