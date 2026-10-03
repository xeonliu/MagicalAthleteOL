from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from magsim.core.events import (
    AbilityTriggeredEvent,
    EventTriggerMode,
    MoveCmdEvent,
    MoveData,
    PassingEvent,
    Phase,
    PostMoveEvent,
    PostTripEvent,
    PostWarpEvent,
    PreMoveEvent,
    PreWarpEvent,
    SimultaneousMoveCmdEvent,
    SimultaneousWarpCmdEvent,
    TripCmdEvent,
    WarpCmdEvent,
    WarpData,
)
from magsim.core.mixins import (
    DestinationCalculatorMixin,
    MovementValidatorMixin,
)
from magsim.core.state import is_active
from magsim.engine.flow import check_finish

if TYPE_CHECKING:
    from collections.abc import Sequence

    from magsim.core.types import Source
    from magsim.engine.game_engine import GameEngine


def _publish_pre_move(engine: GameEngine, evt: MoveCmdEvent):
    if (racer := engine.get_active_racer(evt.target_racer_idx)) is None:
        return
    engine.dispatch_immediately(
        PreMoveEvent(
            target_racer_idx=evt.target_racer_idx,
            start_tile=racer.position,
            distance=evt.distance,
            source=evt.source,
            phase=evt.phase,
            responsible_racer_idx=evt.responsible_racer_idx,
        ),
    )


def _resolve_move_path(
    engine: GameEngine,
    evt: MoveCmdEvent,
) -> tuple[int, list[AbilityTriggeredEvent]]:
    if (racer := engine.get_active_racer(evt.target_racer_idx)) is None:
        raise ValueError("Cannot resolve move path for inactive racer")
    start = racer.position

    # --- 1. CALCULATE PHYSICS DESTINATION (Leaptoad) ---
    phys_end = start + evt.distance

    movement_event_triggered_events: list[AbilityTriggeredEvent] = []
    for mod in racer.modifiers:
        if isinstance(mod, DestinationCalculatorMixin):
            phys_end, triggered_events = mod.calculate_destination(
                engine,
                racer.idx,
                start,
                evt.distance,
                move_cmd_event=evt,
            )
            movement_event_triggered_events.extend(triggered_events)
            break

    # --- 2. VALIDATE MOVE (Stickler) ---
    for mod in racer.modifiers:
        if isinstance(mod, MovementValidatorMixin) and not mod.validate_move(
            engine,
            racer.idx,
            start,
            phys_end,
        ):
            engine.log_info(f"Move vetoed by {mod.name}")
            if mod.owner_idx is None:
                msg = f"MovementValidatorMixin should always have valid owner_idx but found None for {mod.name}"
                raise ValueError(msg)
            return start, [
                AbilityTriggeredEvent(
                    mod.owner_idx,
                    mod.name,
                    phase=evt.phase,
                    target_racer_idx=evt.target_racer_idx,
                ),
            ]  # Cancel move

    # --- 3. RESOLVE BOARD INTERACTIONS (Huge Baby) ---
    # Pass the event object itself to the board logic
    # Note: If phys_end == start (e.g. dist=0 or vetoed), resolve_position might still trigger
    # things if Huge Baby is ON start... but normally it handles "approach".

    final_end = engine.state.board.resolve_position(
        phys_end,
        evt.target_racer_idx,
        engine,
        event=evt,
    )

    # --- 4. SAFETY CLAMP ---
    if final_end < 0:
        engine.log_info(
            f"Attempted to move {racer.repr} to {final_end}. Instead moving to starting tile (0).",
        )
        final_end = 0

    # if racer didn't move, movement related abilities were not triggered
    triggered = (
        final_end != start
    ) or engine.state.rules.count_0_moves_for_ability_triggered
    if not triggered:
        movement_event_triggered_events = []

    return final_end, movement_event_triggered_events


def _process_passing_and_logs(
    engine: GameEngine,
    evt: MoveCmdEvent,
    start_tile: int,
    end_tile: int,
):
    racer = engine.get_racer(evt.target_racer_idx)
    move_prefix = "Main Move" if evt.is_main else "Move"
    engine.log_info(
        f"{move_prefix}: {racer.repr} {start_tile}->{end_tile} ({evt.source})",
    )

    if evt.distance != 0:
        step = 1 if evt.distance > 0 else -1
        current = start_tile + step
        while current != end_tile:
            if 0 <= current < engine.state.board.length:
                victims = engine.get_racers_at_position(
                    tile_idx=current,
                    except_racer_idx=evt.target_racer_idx,
                )
                for v in victims:
                    engine.push_event(
                        PassingEvent(
                            responsible_racer_idx=evt.target_racer_idx,
                            target_racer_idx=v.idx,
                            phase=evt.phase,
                            source=evt.source,
                            tile_idx=current,
                        ),
                    )
            current += step
            # Safety break
            if (step > 0 and current > end_tile) or (step < 0 and current < end_tile):
                break


def _finalize_committed_move(
    engine: GameEngine,
    evt: MoveCmdEvent,
    start_tile: int,
    end_tile: int,
):
    racer = engine.get_racer(evt.target_racer_idx)
    # 1. Telemetry (ALWAYS)
    post_move_event = PostMoveEvent(
        target_racer_idx=evt.target_racer_idx,
        start_tile=start_tile,
        end_tile=end_tile,
        trigger_racer_idx=evt.trigger_racer_idx,
        source=evt.source,
        phase=evt.phase,
        responsible_racer_idx=evt.responsible_racer_idx,
    )
    if engine.on_event_processed:
        engine.on_event_processed(engine, post_move_event)

    # 2. Check Finish / Race End
    if check_finish(engine, racer) and not engine.state.race_active:
        return

    # 3. Subscribers (Abilities) - Only if race is active
    engine.publish_to_subscribers(post_move_event)

    # 4. Landing Effects - Only if racer is still on board (didn't finish)
    if not racer.finished:
        engine.state.board.trigger_on_land(
            end_tile,
            evt.target_racer_idx,
            evt.phase,
            engine,
        )


def handle_move_cmd(engine: GameEngine, evt: MoveCmdEvent):
    if (
        not is_active(racer := engine.get_racer(evt.target_racer_idx))
        or evt.distance == 0
    ):
        return

    start = racer.position

    # first handle anything that is pre-move
    _publish_pre_move(engine, evt)

    # resolve path for movement manipulators (Leaptoad, Suckerfish, Stickler)
    end, movement_event_triggered_events = _resolve_move_path(engine, evt)
    racer.position = end

    # first we push ability triggered events for all events that happened during movement
    # we already filtered abilities that did not happen because of 0 movement
    for mvt_evt in movement_event_triggered_events:
        engine.push_event(mvt_evt)

    # if we have 0 movement, we can stop resolving things here
    if end == start:
        return

    # then for any ability that moves the racer (if the racer moved)
    if evt.emit_ability_triggered == "after_resolution":
        triggered = (
            end != start
        ) or engine.state.rules.count_0_moves_for_ability_triggered
        if triggered:
            engine.push_event(AbilityTriggeredEvent.from_event(evt))

    # lastly we handle passing
    _process_passing_and_logs(engine, evt, start, end)

    # and handle landing (and landing abilities)
    _finalize_committed_move(engine, evt, start, end)


def handle_simultaneous_move_cmd(engine: GameEngine, evt: SimultaneousMoveCmdEvent):
    class PlannedMove(NamedTuple):
        move_cmd_event: MoveCmdEvent
        start: int
        end: int
        ability_triggered_events: list[AbilityTriggeredEvent]

    planned: list[PlannedMove] = []

    for move in evt.moves:
        if move.distance == 0:
            continue
        racer = engine.get_racer(move.moving_racer_idx)
        if not is_active(racer):
            continue

        # Create transient event FIRST
        sub_evt = MoveCmdEvent(
            target_racer_idx=move.moving_racer_idx,
            distance=move.distance,
            source=evt.source,
            phase=evt.phase,
            emit_ability_triggered="never",
            responsible_racer_idx=evt.responsible_racer_idx,
        )

        start = racer.position
        _publish_pre_move(engine, sub_evt)

        end, movement_event_triggered_events = _resolve_move_path(engine, sub_evt)

        planned.append(
            PlannedMove(sub_evt, start, end, movement_event_triggered_events),
        )

    if not planned:
        return

    # first we send all ability triggered events
    # (we already removed events that were not triggered due to 0 movement before)
    for planned_move_command in planned:
        for ability_triggered_event in planned_move_command.ability_triggered_events:
            engine.push_event(ability_triggered_event)

    filtered_planned = [
        planned_move_cmd
        for planned_move_cmd in planned
        if planned_move_cmd.start != planned_move_cmd.end
    ]

    if evt.emit_ability_triggered == "after_resolution":
        engine.push_event(AbilityTriggeredEvent.from_event(evt))

    for sub_evt, start, end, _ in filtered_planned:
        _process_passing_and_logs(engine, sub_evt, start, end)

    for sub_evt, _, end, _ in filtered_planned:
        engine.get_racer(sub_evt.target_racer_idx).position = end

    for sub_evt, start, end, _ in filtered_planned:
        _finalize_committed_move(engine, sub_evt, start, end)


######
# WARPING
######


def _resolve_warp_destination(
    engine: GameEngine,
    *,
    event: WarpCmdEvent,
) -> int:
    resolved = engine.state.board.resolve_position(
        event.target_tile,
        event.target_racer_idx,
        engine,
        event=event,
    )
    if resolved < 0:
        engine.log_info(
            f"Attempted to warp to {resolved}. Instead moving to starting tile (0).",
        )
        resolved = 0
    return resolved


def _finalize_committed_warp(
    engine: GameEngine,
    event: WarpCmdEvent,
    *,
    start_tile: int,
    end_tile: int,
):
    racer = engine.get_racer(event.target_racer_idx)
    racer.position = end_tile
    engine.log_info(f"Warp: {racer.repr} -> {end_tile} ({event.source})")

    # 1. Telemetry (ALWAYS)
    post_warp_event = PostWarpEvent(
        target_racer_idx=event.target_racer_idx,
        start_tile=start_tile,
        end_tile=end_tile,
        source=event.source,
        phase=event.phase,
        responsible_racer_idx=event.responsible_racer_idx,
    )
    if engine.on_event_processed:
        engine.on_event_processed(engine, post_warp_event)

    # 2. Check Finish / Race End
    if check_finish(engine, racer) and not engine.state.race_active:
        return

    # 3. Subscribers
    engine.publish_to_subscribers(post_warp_event)

    # 4. Landing Effects
    if not racer.finished:
        engine.state.board.trigger_on_land(
            end_tile,
            event.target_racer_idx,
            event.phase,
            engine,
        )


def handle_warp_cmd(engine: GameEngine, evt: WarpCmdEvent):
    racer = engine.get_racer(evt.target_racer_idx)
    if not is_active(racer):
        return

    start = racer.position

    # Warping to the same tile is not movement
    if start == evt.target_tile:
        return

    # 1. Departure hook
    engine.dispatch_immediately(
        PreWarpEvent(
            target_racer_idx=evt.target_racer_idx,
            start_tile=start,
            target_tile=evt.target_tile,
            source=evt.source,
            phase=evt.phase,
            responsible_racer_idx=evt.responsible_racer_idx,
        ),
    )

    # 2. Resolve spatial modifiers on the target
    resolved = _resolve_warp_destination(
        engine,
        event=evt,
    )

    if resolved == start:
        return

    if evt.emit_ability_triggered == "after_resolution":
        engine.push_event(
            event=AbilityTriggeredEvent.from_event(evt),
        )

    _finalize_committed_warp(
        engine,
        event=evt,
        start_tile=start,
        end_tile=resolved,
    )


def handle_simultaneous_warp_cmd(engine: GameEngine, evt: SimultaneousWarpCmdEvent):
    # 0. Preparation: Gather valid warps
    # We store the plan as: (original_warp_event, start_tile, resolved_end_tile)
    # We create temporary "single" WarpCmdEvents to reuse your existing helpers easily.
    planned_warps: list[tuple[WarpCmdEvent, int, int]] = []

    for warp in evt.warps:
        racer = engine.get_racer(warp.warping_racer_idx)
        if not is_active(racer):
            continue

        start = racer.position
        if start == warp.target_tile:
            continue

        # Create a transient single event to pass to helpers/hooks
        # (This avoids duplicating logic for PreWarpEvent creation etc.)
        single_warp_evt = WarpCmdEvent(
            target_racer_idx=warp.warping_racer_idx,
            target_tile=warp.target_tile,
            source=evt.source,
            phase=evt.phase,
            emit_ability_triggered="never",  # We handle the batch trigger separately
            responsible_racer_idx=evt.responsible_racer_idx,
        )

        # 1. Departure hook (PreWarpEvent)
        engine.dispatch_immediately(
            PreWarpEvent(
                target_racer_idx=warp.warping_racer_idx,
                start_tile=start,
                target_tile=warp.target_tile,
                source=evt.source,
                phase=evt.phase,
                responsible_racer_idx=evt.responsible_racer_idx,
            ),
        )

        # 2. Resolve destination
        resolved = _resolve_warp_destination(engine, event=single_warp_evt)

        # If resolution results in no movement (e.g. bounce back to start), skip
        if resolved == start:
            continue

        planned_warps.append((single_warp_evt, start, resolved))

    if not planned_warps:
        return

    # Trigger the ability itself once for the whole batch (if configured)
    if evt.emit_ability_triggered == "after_resolution":
        engine.push_event(AbilityTriggeredEvent.from_event(evt))

    # 3. ATOMIC COMMIT: Update all positions simultaneously
    for single_evt, _, resolved in planned_warps:
        racer = engine.get_racer(single_evt.target_racer_idx)
        racer.position = resolved

    # 4. Finalize: Run landing hooks and arrival events
    # Now that the board state is "finalized" for everyone, listeners will see the correct state.
    for single_evt, start, resolved in planned_warps:
        _finalize_committed_warp(
            engine,
            event=single_evt,
            start_tile=start,
            end_tile=resolved,
        )


def handle_trip_cmd(engine: GameEngine, evt: TripCmdEvent):
    racer = engine.get_racer(evt.target_racer_idx)
    if not racer.active:
        return

    racer.tripping_racers.append(evt.responsible_racer_idx)
    if racer.tripped:
        return

    racer.tripped = True
    engine.log_info(f"{evt.source}: {racer.repr} is now tripped.")

    if evt.emit_ability_triggered != "never":
        engine.push_event(AbilityTriggeredEvent.from_event(evt))

    # Use dispatch_immediate pattern for PostTripEvent too. Board features such as
    # TripTile trip a racer without a responsible racer, so this must not be gated
    # on the source racer: the event also drives the presentation layer.
    post_trip_event = PostTripEvent(
        responsible_racer_idx=evt.responsible_racer_idx,
        source=evt.source,
        target_racer_idx=evt.target_racer_idx,
        phase=evt.phase,
    )
    if engine.on_event_processed:
        engine.on_event_processed(engine, post_trip_event)

    # Publish to subscribers if needed (currently Trip doesn't have listeners, but consistent)
    engine.publish_to_subscribers(post_trip_event)


####
# Helpers
####


def push_move(
    engine: GameEngine,
    distance: int,
    phase: Phase,
    *,
    moved_racer_idx: int,
    source: Source,
    responsible_racer_idx: int | None,
    emit_ability_triggered: EventTriggerMode = "never",
    is_main_move: bool = False,
    trigger_racer_idx: int | None = None,
    scooch_reactors: set[int] | None = None,
):
    engine.push_event(
        MoveCmdEvent(
            target_racer_idx=moved_racer_idx,
            distance=distance,
            source=source,
            phase=phase,
            emit_ability_triggered=emit_ability_triggered,
            responsible_racer_idx=responsible_racer_idx,
            is_main=is_main_move,
            trigger_racer_idx=trigger_racer_idx,
            scooch_reactors=scooch_reactors if scooch_reactors is not None else set(),
        ),
    )


def push_simultaneous_move(
    engine: GameEngine,
    moves: Sequence[MoveData],
    phase: Phase,
    *,
    source: Source,
    responsible_racer_idx: int | None,
    emit_ability_triggered: EventTriggerMode = "after_resolution",
):
    engine.push_event(
        SimultaneousMoveCmdEvent(
            moves=moves,
            source=source,
            phase=phase,
            responsible_racer_idx=responsible_racer_idx,
            emit_ability_triggered=emit_ability_triggered,
        ),
    )


def push_warp(
    engine: GameEngine,
    target: int,
    phase: Phase,
    *,
    warped_racer_idx: int,
    source: Source,
    responsible_racer_idx: int | None,
    emit_ability_triggered: EventTriggerMode = "never",
):
    engine.push_event(
        WarpCmdEvent(
            target_racer_idx=warped_racer_idx,
            target_tile=target,
            source=source,
            phase=phase,
            emit_ability_triggered=emit_ability_triggered,
            responsible_racer_idx=responsible_racer_idx,
        ),
    )


def push_simultaneous_warp(
    engine: GameEngine,
    warps: list[WarpData],  # List of (racer_idx, target_tile)
    phase: Phase,
    *,
    source: Source,
    responsible_racer_idx: int | None,
    emit_ability_triggered: EventTriggerMode = "after_resolution",
):
    engine.push_event(
        SimultaneousWarpCmdEvent(
            warps=warps,
            source=source,
            phase=phase,
            emit_ability_triggered=emit_ability_triggered,
            responsible_racer_idx=responsible_racer_idx,
        ),
    )


def push_trip(
    engine: GameEngine,
    phase: Phase,
    *,
    tripped_racer_idx: int,
    source: Source,
    responsible_racer_idx: int | None,
    emit_ability_triggered: EventTriggerMode = "after_resolution",
):
    engine.push_event(
        TripCmdEvent(
            target_racer_idx=tripped_racer_idx,
            source=source,
            phase=phase,
            emit_ability_triggered=emit_ability_triggered,
            responsible_racer_idx=responsible_racer_idx,
        ),
    )
