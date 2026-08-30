from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from agent.slots import validate_out_trade_no


class OrderFactsArguments(BaseModel):
    """Only model-controllable argument for get_order_facts; unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    out_trade_no: StrictStr = Field(alias="outTradeNo")

    @field_validator("out_trade_no")
    @classmethod
    def out_trade_no_must_be_a_valid_slot(cls, value: str) -> str:
        slot = validate_out_trade_no(value)
        if not slot.is_valid:
            raise ValueError(slot.error_code or "OUT_TRADE_NO_INVALID")
        return slot.value


class JoinableTeamFactsArguments(BaseModel):
    """Only model-controllable argument for get_joinable_team_facts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    activity_id: StrictInt = Field(alias="activityId", gt=0)


class SearchGroupBuyRulesArguments(BaseModel):
    """Only model-controllable argument for search_group_buy_rules."""

    model_config = ConfigDict(extra="forbid")

    query: StrictStr = Field(min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("RULE_SEARCH_QUERY_INVALID")
        if len(normalized) > 500:
            raise ValueError("RULE_SEARCH_QUERY_INVALID")
        return normalized
