from __future__ import annotations

from decision.schemas import AgentAction


def _is_empty_placeholder(value: object) -> bool:
    return value is None or value == {} or value == [] or (isinstance(value, str) and not value.strip())


def normalize_agent_decision_payload(payload: object) -> object:
    """Remove only empty placeholders for fields absent from the selected action.

    Non-empty unrelated fields, action values, Tool names/arguments and evidence
    remain exactly as supplied so strict Pydantic and Harness validation can reject
    them. This is formatting normalization, never semantic repair.
    """
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    removable_by_action: dict[AgentAction, tuple[str, ...]] = {
        AgentAction.CALL_TOOL: ("final_answer", "used_evidence", "missing_information"),
        AgentAction.ANSWER: ("tool_name", "tool_arguments", "missing_information"),
        AgentAction.HANDOFF: ("tool_name", "tool_arguments", "final_answer", "used_evidence"),
    }
    try:
        action = AgentAction(normalized.get("action"))
        fields = removable_by_action[action]
    except (ValueError, TypeError):
        return normalized
    if action is AgentAction.HANDOFF and isinstance(normalized.get("missing_information"), str):
        if normalized["missing_information"].strip():
            # The Provider occasionally emits the one valid missing-information
            # item without its required list container. Preserve its text exactly.
            normalized["missing_information"] = [normalized["missing_information"]]
        else:
            normalized.pop("missing_information")
    for field in fields:
        if field in normalized and _is_empty_placeholder(normalized[field]):
            normalized.pop(field)
    return normalized
