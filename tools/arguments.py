from pydantic import BaseModel, ConfigDict, Field

from agent.slots import validate_out_trade_no


class OrderFactsArguments(BaseModel):
    """Only model-controllable argument for get_order_facts; unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    out_trade_no: str = Field(alias="outTradeNo")


ORDER_FACTS_ARGUMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["outTradeNo"],
    "properties": {"outTradeNo": {"type": "string"}},
}


def normalize_order_facts_arguments(arguments: object) -> dict[str, str] | None:
    try:
        parsed = OrderFactsArguments.model_validate(arguments)
    except Exception:
        return None
    slot = validate_out_trade_no(parsed.out_trade_no)
    return {"outTradeNo": slot.value} if slot.is_valid else None
