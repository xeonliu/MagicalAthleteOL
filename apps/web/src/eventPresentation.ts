import type { TFunction } from "i18next";

import i18n from "./i18n";
import { athleteText } from "./i18n/athletes";
import { abilityTitleText, decisionOptionLabel } from "./decisionPresentation";
import type { GameEvent, PlayerState, RoomSnapshot } from "./protocol";

export type Participant = { playerId?: string; athleteId?: string; name: string; owner: string };
export type ActionMoment = { source: Participant; target: Participant; cause: string; effect: string; scoreAmount?: number; from?: number; to?: number };

// The wire name is the English card face, so it only stands in when the catalog
// has no entry for the racer id.
function racerName(
  t: TFunction,
  players: PlayerState[],
  playerId?: string,
  athleteId?: string,
  wireName?: string,
): string {
  const owner = players.find((p) => p.id === playerId);
  const card = owner?.activeRacers.find((r) => r.id === athleteId) ?? owner?.team.find((r) => r.id === athleteId);
  const fallback = wireName || t("race:participant.racer");
  if (card) return athleteText(t, card).name;
  return athleteId ? athleteText(t, { id: athleteId, name: fallback }).name : fallback;
}

function participant(
  t: TFunction,
  players: PlayerState[],
  playerId?: string,
  athleteId?: string,
  wireName?: string,
): Participant {
  const owner = players.find((p) => p.id === playerId);
  return {
    playerId,
    athleteId,
    name: racerName(t, players, playerId, athleteId, wireName),
    owner: owner?.name ?? "",
  };
}

export function isRedundantAbilityEvent(event: GameEvent, events: GameEvent[]): boolean {
  return event.type === "ABILITY_TRIGGERED" && events.some((effect) =>
    ["RACER_MOVED", "RACER_WARPED", "RACER_TRIPPED"].includes(effect.type)
    && (effect.source === event.abilityName || event.abilityName === "SuckerfishTarget" && effect.source === "SuckerfishRide")
    && effect.sourcePlayerId === event.sourcePlayerId && effect.sourceAthleteId === event.sourceAthleteId
    && (!event.athleteId || effect.athleteId === event.athleteId && effect.playerId === event.playerId));
}

// One complete sentence per recorded event, so the feed never needs to drop detail.
// `events` holds the siblings from the same update so repeated ability notices collapse.
export function eventText(event: GameEvent, players: PlayerState[], events: GameEvent[] = [], t: TFunction = i18n.t): string {
  if (event.type === "ABILITY_TRIGGERED" && isRedundantAbilityEvent(event, events)) return "";
  const player = players.find((item) => item.id === event.playerId);
  const who = player?.name ?? t("race:participant.player");
  if (event.type === "START_DICE_ROLLED") return t("race:event.startDiceRolled", { who, values: event.values?.join(" / ") });
  if (event.type === "ROLL_OFF_TIED") return t("race:event.rollOffTied");
  if (event.type === "ATHLETE_DRAFTED") return t("race:event.athleteDrafted", { who });
  if (event.type === "TEAM_DEALT") return t("race:event.teamDealt", { who, cards: event.athleteIds?.length ?? 0 });
  if (event.type === "RACERS_LOCKED") return t("race:event.racersLocked", { who });
  if (event.type === "DICE_ROLLED") {
    // Overridden moves (Legs' jog) carry a distance but no die face.
    return event.noDice ? "" : t("race:event.diceRolled", { who, value: event.value });
  }
  if (event.type === "DIE_ROLLED") return t("race:event.dieRolled", { who, index: (event.throwIndex ?? 0) + 1, value: event.value });
  if (event.type === "ABILITY_DICE_ROLLED") return t("race:event.abilityDiceRolled", { who, value: event.value });
  if (event.type === "ABILITY_ROLL_RESOLVED") {
    const winner = players.find((item) => item.id === event.winnerPlayerId);
    return t("race:event.abilityRollResolved", { winner: winner?.name ?? t("race:participant.player") });
  }
  const moment = actionMoment(event, players, t);
  if (moment) {
    return t("race:moment.line", {
      cause: moment.cause, owner: moment.target.owner, name: moment.target.name, effect: moment.effect,
    });
  }
  if (event.type === "ROLL_OFF_WON") return t("race:event.rollOffWon", { who });
  if (event.type === "DECISION_REQUIRED") {
    const athlete = racerName(t, players, event.playerId, event.athleteId);
    return t("race:event.decisionRequired", { who, athlete, ability: abilityTitleText(event.abilityName, t) });
  }
  if (event.type === "DECISION_RESOLVED") {
    const chosen = event.optionLabel ? decisionOptionLabel(event.optionLabel, t) : "";
    return t("race:event.decisionResolved", {
      who,
      ability: abilityTitleText(event.abilityName, t),
      chosen: chosen || t("race:event.decisionResolvedDefault"),
    });
  }
  if (event.type === "DECISION_TIMED_OUT") {
    return t("race:event.decisionTimedOut", { who, ability: abilityTitleText(event.abilityName, t) });
  }
  if (event.type === "TRIP_RECOVERED") {
    return t("race:event.tripRecovered", { who, athlete: racerName(t, players, event.playerId, event.athleteId) });
  }
  if (event.type === "RACER_ELIMINATED") {
    return t("race:event.racerEliminated", { who, athlete: racerName(t, players, event.playerId, event.athleteId) });
  }
  if (event.type === "RACER_FINISHED") {
    return t("race:event.racerFinished", {
      who, athlete: racerName(t, players, event.playerId, event.athleteId), position: event.finishPosition,
    });
  }
  if (event.type === "RACE_FINISHED") return t("race:event.raceFinished", { number: event.raceNumber });
  if (event.type === "PLAYER_JOINED") return t("race:event.playerJoined", { who });
  if (event.type === "PLAYER_LEFT") {
    return event.reason === "KICKED"
      ? t("race:event.playerKicked", { name: event.playerName ?? t("race:participant.player") })
      : t("race:event.playerLeft", { name: event.playerName ?? t("race:participant.player") });
  }
  if (event.type === "PLAYER_DISCONNECTED") return t("race:event.playerDisconnected", { who });
  return "";
}

export function actionMoment(
  event: GameEvent,
  players: PlayerState[],
  t: TFunction = i18n.t,
): ActionMoment | null {
  if (!["ABILITY_TRIGGERED", "RACER_MOVED", "RACER_WARPED", "RACER_TRIPPED"].includes(event.type)) return null;
  const source = participant(t, players, event.sourcePlayerId, event.sourceAthleteId, event.sourceAthleteName);
  const target = participant(t, players, event.playerId ?? event.sourcePlayerId, event.athleteId ?? event.sourceAthleteId);
  const self = source.playerId === target.playerId && source.athleteId === target.athleteId;
  const key = event.abilityName ?? event.source;
  const followed = event.triggerAthleteId
    ? participant(t, players, event.triggerPlayerId, event.triggerAthleteId, event.triggerAthleteName)
    : null;
  const causes: Record<string, string> = {
    CentaurTrample: t("race:moment.cause.CentaurTrample", { source: source.name, target: target.name }),
    BananaTrip: t("race:moment.cause.BananaTrip", { source: source.name, target: target.name }),
    BabaYagaTrip: t("race:moment.cause.BabaYagaTrip", { source: source.name, target: target.name }),
    CoachBoost: self
      ? t("race:moment.cause.CoachBoostSelf", { source: source.name })
      : t("race:moment.cause.CoachBoost", { source: source.name, target: target.name }),
    LongLegs: t("race:moment.cause.LongLegs", { target: target.name }),
    HugeBabyBlocker: t("race:moment.cause.HugeBabyBlocker", { source: source.name, target: target.name }),
    HugeBabyPush: t("race:moment.cause.HugeBabyPush", { source: source.name, target: target.name }),
    LackeyLoyalty: t("race:moment.cause.LackeyLoyalty"),
    InchwormCreep: t("race:moment.cause.InchwormCreep"),
    ScoochStep: t("race:moment.cause.ScoochStep"),
    SisyphusCurse: t("race:moment.cause.SisyphusCurse", { source: source.name }),
    RocketScientistBoost: t("race:moment.cause.RocketScientistBoost", { source: source.name }),
    HareHubris: t("race:moment.cause.HareHubris", { source: source.name }),
    HareSpeed: t("race:moment.cause.HareSpeed", { source: source.name }),
    LovableLoserBonus: t("race:moment.cause.LovableLoserBonus", { source: source.name }),
    LeaptoadJump: t("race:moment.cause.LeaptoadJump", { source: source.name }),
    HypnotistWarp: t("race:moment.cause.HypnotistWarp", { source: source.name, target: target.name }),
    FlipFlopSwap: t("race:moment.cause.FlipFlopSwap", { source: source.name }),
    GunkSlimeModifier: t("race:moment.cause.GunkSlimeModifier", { source: source.name, target: target.name }),
    HecklerHeckle: t("race:moment.cause.HecklerHeckle"),
    CheerleaderSupport: t("race:moment.cause.CheerleaderSupport", { source: source.name }),
    PartyPull: t("race:moment.cause.PartyPull", { source: source.name }),
    PartySelfBoost: t("race:moment.cause.PartySelfBoost", { source: source.name }),
    SuckerfishTarget: followed
      ? t("race:moment.cause.SuckerfishTargetFollow", { target: target.name, followed: followed.name })
      : t("race:moment.cause.SuckerfishTargetLocked", { source: source.name }),
    MoveDeltaTile: t("race:moment.cause.MoveDeltaTile", { target: target.name, from: event.from }),
    TripTile: t("race:moment.cause.TripTile", { target: target.name }),
    SuckerfishRide: followed
      ? t("race:moment.cause.SuckerfishRideFollow", { followed: followed.name, target: target.name })
      : t("race:moment.cause.SuckerfishRideIdle", { source: source.name }),
    ThirdWheelJoin: t("race:moment.cause.ThirdWheelJoin", { source: source.name }),
    SkipperTurn: t("race:moment.cause.SkipperTurn"),
    DuelistDuel: t("race:moment.cause.DuelistDuel", { target: target.name }),
  };
  const isNormal = key === "System" || !key;
  if (isNormal || !source.athleteId) {
    source.athleteId = undefined;
    source.playerId = undefined;
    source.name = isNormal ? t("race:source.dice")
      : key === "Board" || key?.endsWith("Tile") ? t("race:source.tile") : t("race:source.ability");
    source.owner = "";
  }
  const distance = typeof event.from === "number" && typeof event.to === "number" ? event.to - event.from : undefined;
  let effect = t("race:moment.effect.triggered");
  if (event.type === "RACER_TRIPPED") effect = t("race:moment.effect.tripped");
  else if (distance !== undefined) effect = event.type === "RACER_WARPED"
    ? event.movementKind === "SWAP" ? t("race:moment.effect.swapped") : t("race:moment.effect.warped", { to: event.to })
    : distance === 0 ? t("race:moment.effect.unchanged")
      : distance > 0 ? t("race:moment.effect.forward", { count: distance })
        : t("race:moment.effect.backward", { count: Math.abs(distance) });
  else if (key === "SuckerfishTarget") effect = t("race:moment.effect.suckerfishTarget");
  else if (key === "DuelistDuel") effect = t("race:moment.effect.duelistDuel");
  else if (key === "LongLegs") effect = t("race:moment.effect.longLegsJog");
  else if (key === "HareHubris") effect = t("race:moment.effect.hareHubris");
  else if (key === "HareSpeed") effect = t("race:moment.effect.hareSpeed");
  else if (key === "LovableLoserBonus") effect = t("race:moment.effect.lovableLoserBonus");
  else if (key === "LeaptoadJump") effect = t("race:moment.effect.leaptoadJump");
  else if (key === "GunkSlimeModifier") effect = t("race:moment.effect.gunkSlime");
  else if (key === "SkipperTurn") effect = t("race:moment.effect.skipperTurn");
  else if (key === "CoachBoost") effect = t("race:moment.effect.coachBoost");
  else if (key === "HugeBabyBlocker") effect = t("race:moment.effect.hugeBabyBlocker");
  else if (event.movementDistance) {
    effect = t("race:moment.effect.movementAdjust", {
      value: `${event.movementDistance > 0 ? "+" : ""}${event.movementDistance}`,
    });
  }
  const cause = causes[key ?? ""] ?? (isNormal
    ? t("race:moment.causeFallback.system")
    : t("race:moment.causeFallback.ability", { source: source.name, target: target.name }));
  return {
    source: key?.startsWith("Suckerfish") && followed ? followed : source,
    target,
    cause,
    effect,
    from: event.from,
    to: event.to,
  };
}

// Keep the completed round visible even though the server has already cleared its dice.
export function rollOffPresentation(
  before: RoomSnapshot,
  after: RoomSnapshot,
  events: GameEvent[],
  t: TFunction = i18n.t,
) {
  const display = structuredClone(before);
  for (const event of events) {
    const player = display.game.players.find((p) => p.id === event.playerId);
    if (event.type === "START_DICE_ROLLED" && player) player.rollValues = event.values ?? null;
  }
  const winner = events.find((e) => e.type === "ROLL_OFF_WON");
  const tie = events.find((e) => e.type === "ROLL_OFF_TIED");
  const name = (id?: string) => after.game.players.find((p) => p.id === id)?.name ?? t("race:participant.player");
  const outcome = winner
    ? t(before.game.phase === "DRAFT_ROLL" ? "race:rollOff.draft" : "race:rollOff.race", { name: name(winner.playerId) })
    : tie
      ? t("race:rollOff.tie", { names: tie.playerIds?.map(name).join(t("race:listSeparator")) })
      : "";
  return { display, outcome, winnerId: winner?.playerId };
}

// Landing feedback comes from the existing movement endpoint, never intermediate steps.
export function landingScoreMoment(event: GameEvent, trackName: string, players: PlayerState[], t: TFunction = i18n.t): ActionMoment | null {
  if (trackName !== "WildWilds" || !["RACER_MOVED", "RACER_WARPED"].includes(event.type)
    || (event.to !== 1 && event.to !== 13) || event.from === event.to) return null;
  const racer = players.find(p => p.id === event.playerId)?.activeRacers.find(r => r.id === event.athleteId);
  if (!racer || racer.finished || racer.eliminated) return null;
  const target = participant(t, players, event.playerId, event.athleteId);
  return {
    source: { name: t("race:source.tile"), owner: "" }, target,
    cause: t("race:moment.cause.VictoryPointTile", { target: target.name }),
    effect: t("race:moment.effect.scored", { count: 1 }), scoreAmount: 1,
  };
}
