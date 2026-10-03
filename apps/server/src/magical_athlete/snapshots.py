from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from datetime import datetime

from .game import GameState, Player

SCHEMA_VERSION = 4


class IncompatibleSnapshotError(ValueError):
    pass


@dataclass(slots=True)
class SnapshotPlayer:
    player: Player
    reconnect_token: str
    seen_action_ids: set[str]
    is_bot: bool = False
    auto_play: bool = False


@dataclass(slots=True)
class RoomSnapshot:
    room_id: str
    players: dict[str, SnapshotPlayer]
    game_state: GameState | None
    revision: int
    decision_deadline: datetime | None
    roll_deadline: datetime | None
    last_active_at: datetime
    bot_deadline: datetime | None = None
    spectators: dict[str, SnapshotPlayer] = field(default_factory=dict)


def encode_snapshot(snapshot: RoomSnapshot) -> bytes:
    return pickle.dumps({"schemaVersion": SCHEMA_VERSION, "snapshot": snapshot}, protocol=5)


def decode_snapshot(data: bytes) -> RoomSnapshot:
    payload = pickle.loads(data)  # noqa: S301 - storage contains server-generated data only.
    if not isinstance(payload, dict) or payload.get("schemaVersion") != SCHEMA_VERSION:
        version = payload.get("schemaVersion") if isinstance(payload, dict) else None
        raise IncompatibleSnapshotError(f"unsupported room snapshot schema: {version!r}")
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, RoomSnapshot):
        raise IncompatibleSnapshotError("invalid room snapshot payload")
    if snapshot.game_state is not None and not hasattr(snapshot.game_state, "race_winner_ids"):
        # Older rooms retain at most the latest race's results; preserve every
        # real winner still available instead of inventing previous champions.
        winners = tuple(result["athlete"]["id"] for result in snapshot.game_state.race_results
                        if result["finishPosition"] == 1)
        object.__setattr__(snapshot.game_state, "race_winner_ids", winners)
    if not hasattr(snapshot, "spectators"):
        snapshot.spectators = {}
    for member in snapshot.players.values():
        if not hasattr(member, "auto_play"):
            member.auto_play = False
    # Pickle preserves instance triggers and subscriber tables from the old
    # deployment. Upgrade Genius without discarding an ongoing room.
    engine = snapshot.game_state.magsim_engine if snapshot.game_state is not None else None
    if engine is not None:
        from magsim.racers.genius import AbilityGenius

        migrated = False
        for racer in engine.state.racers:
            for ability in racer.active_abilities:
                if isinstance(ability, AbilityGenius) and ability.triggers != AbilityGenius.triggers:
                    ability.triggers = AbilityGenius.triggers
                    migrated = True
        if migrated:
            engine._rebuild_subscribers()
    return snapshot
