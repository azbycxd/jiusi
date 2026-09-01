from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


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


class ActivityDetails(BaseModel):
    """Validated activity-level facts returned by the Java activity endpoint."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    activity_id: StrictInt = Field(alias="activityId", gt=0)
    status: StrictStr
    start_time: StrictStr = Field(alias="startTime")
    end_time: StrictStr = Field(alias="endTime")
    tag_scope: StrictStr = Field(alias="tagScope")
    user_take_limit: StrictInt | None = Field(alias="userTakeLimit")
    evaluated_at: StrictStr = Field(alias="evaluatedAt")
    within_valid_time: StrictBool = Field(alias="withinValidTime")


class ActivityFactsResponse(BaseModel):
    """Normalized Python contract for Java activity facts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    activity: ActivityDetails

    def as_context_data(self) -> dict:
        return self.model_dump(mode="json")


class UserEligibilityFacts(BaseModel):
    """Validated current-user participation facts for one activity."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    activity_id: StrictInt = Field(alias="activityId", gt=0)
    tag_rule_configured: StrictBool = Field(alias="tagRuleConfigured")
    tag_crowd_data_available: StrictBool = Field(alias="tagCrowdDataAvailable")
    tag_gate_passed: StrictBool = Field(alias="tagGatePassed")
    tag_visibility_allowed: StrictBool = Field(alias="tagVisibilityAllowed")
    tag_participation_allowed: StrictBool = Field(alias="tagParticipationAllowed")
    user_take_count: StrictInt = Field(alias="userTakeCount", ge=0)
    user_take_limit: StrictInt | None = Field(alias="userTakeLimit")
    participation_limit_reached: StrictBool = Field(alias="participationLimitReached")
    market_downgraded: StrictBool = Field(alias="marketDowngraded")
    user_within_release_range: StrictBool = Field(alias="userWithinReleaseRange")

    def as_context_data(self) -> dict:
        return self.model_dump(mode="json")
