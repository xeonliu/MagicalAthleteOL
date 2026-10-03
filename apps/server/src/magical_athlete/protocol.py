from typing import Annotated, Literal

from pydantic import BaseModel, Field


class JoinRoomIntent(BaseModel):
    type: Literal["JOIN_ROOM"]
    room_id: str = Field(alias="roomId", min_length=4, max_length=8)
    player_name: str = Field(alias="playerName", min_length=1, max_length=24)
    player_id: str | None = Field(default=None, alias="playerId")
    reconnect_token: str | None = Field(default=None, alias="reconnectToken")
    role: Literal["player", "spectator"] = "player"


class LeaveRoomIntent(BaseModel):
    type: Literal["LEAVE_ROOM"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)


class KickPlayerIntent(BaseModel):
    type: Literal["KICK_PLAYER"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)
    target_player_id: str = Field(alias="targetPlayerId", min_length=1, max_length=64)


class AddBotIntent(BaseModel):
    type: Literal["ADD_BOT"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)


class StartGameIntent(BaseModel):
    type: Literal["START_GAME"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)


class SetVariantIntent(BaseModel):
    type: Literal["SET_VARIANT"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)
    double_racer: bool = Field(alias="doubleRacer")


class SetAutoDealIntent(BaseModel):
    type: Literal["SET_AUTO_DEAL"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)
    auto_deal: bool = Field(alias="autoDeal")


class SetAutoPlayIntent(BaseModel):
    type: Literal["SET_AUTO_PLAY"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)
    enabled: bool


class ThrowPropIntent(BaseModel):
    type: Literal["THROW_PROP"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)
    target_player_id: str = Field(alias="targetPlayerId", min_length=1, max_length=64)
    item: Literal["egg", "tomato"]


class RollDiceIntent(BaseModel):
    type: Literal["ROLL_DICE"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)


class RollStartIntent(BaseModel):
    type: Literal["ROLL_START"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)


class DraftAthleteIntent(BaseModel):
    type: Literal["DRAFT_ATHLETE"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)
    athlete_id: str = Field(alias="athleteId", min_length=1, max_length=64)


class SelectRacersIntent(BaseModel):
    type: Literal["SELECT_RACERS"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)
    athlete_ids: tuple[str, ...] = Field(alias="athleteIds", min_length=1, max_length=2)


class AdvanceRaceIntent(BaseModel):
    type: Literal["ADVANCE_RACE"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)


class ResolveDecisionIntent(BaseModel):
    type: Literal["RESOLVE_DECISION"]
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)
    decision_id: str = Field(alias="decisionId", min_length=1, max_length=64)
    option_id: str = Field(alias="optionId", min_length=1, max_length=64)


ClientIntent = Annotated[
    JoinRoomIntent
    | LeaveRoomIntent
    | KickPlayerIntent
    | AddBotIntent
    | StartGameIntent
    | SetVariantIntent
    | SetAutoDealIntent
    | SetAutoPlayIntent
    | ThrowPropIntent
    | RollStartIntent
    | DraftAthleteIntent
    | SelectRacersIntent
    | RollDiceIntent
    | AdvanceRaceIntent
    | ResolveDecisionIntent,
    Field(discriminator="type"),
]


class ErrorMessage(BaseModel):
    type: Literal["ERROR"] = "ERROR"
    code: str
    message: str
    action_id: str | None = Field(default=None, alias="actionId")

    model_config = {"populate_by_name": True}
