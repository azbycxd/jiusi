from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


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


class CandidateTeamFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    team_id: StrictStr = Field(alias="teamId")
    target_count: StrictInt = Field(alias="targetCount", ge=0)
    complete_count: StrictInt = Field(alias="completeCount", ge=0)
    lock_count: StrictInt = Field(alias="lockCount", ge=0)
    valid_end_time: StrictStr | None = Field(default=None, alias="validEndTime")


class TeamStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    all_team_count: StrictInt = Field(alias="allTeamCount", ge=0)
    all_team_complete_count: StrictInt = Field(alias="allTeamCompleteCount", ge=0)
    all_team_user_count: StrictInt = Field(alias="allTeamUserCount", ge=0)


class JoinableTeamFacts(BaseModel):
    """Normalized, whitelist-only Python contract for Java joinable-team facts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    activity_id: StrictInt = Field(alias="activityId", gt=0)
    candidate_teams: list[CandidateTeamFacts] = Field(alias="candidateTeams")
    statistics: TeamStatistics

    def as_context_data(self) -> dict:
        return self.model_dump(mode="json")
