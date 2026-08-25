from pydantic import BaseModel, ConfigDict, Field


class OrderFact(BaseModel):
    status: str


class TeamFacts(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    target_count: int = Field(alias="targetCount")
    lock_count: int = Field(alias="lockCount")
    complete_count: int = Field(alias="completeCount")
    valid_end_time: str | None = Field(default=None, alias="validEndTime")


class ActivityFacts(BaseModel):
    status: str


class OrderReferences(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    team_id: str = Field(alias="teamId")
    activity_id: int = Field(alias="activityId")


class OrderFacts(BaseModel):
    """Normalized Python contract for the Java order-facts response data."""

    order: OrderFact
    team: TeamFacts
    activity: ActivityFacts
    references: OrderReferences

    def as_context_data(self) -> dict:
        return self.model_dump(mode="json")
