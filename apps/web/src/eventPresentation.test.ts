import { describe, expect, it } from "vitest";
import type { PlayerState, RoomSnapshot } from "./protocol";
import { landingScoreMoment, actionMoment, eventText, rollOffPresentation } from "./eventPresentation";

const players = [
  { id: "p1", name: "小明", rollValues: [6, 2], activeRacers: [{ id: "centaur", name: "Centaur" }], team: [] },
  { id: "p2", name: "小红", rollValues: null, activeRacers: [{ id: "banana", name: "Banana" }], team: [] },
] as unknown as PlayerState[];
const before = { revision: 1, roomId: "TEST", game: { phase: "DRAFT_ROLL", players } } as RoomSnapshot;
const after = { ...before, revision: 2, game: { ...before.game, phase: "DRAFTING", players: players.map((p) => ({ ...p, rollValues: null })) } } as RoomSnapshot;

describe("roll-off presentation", () => {
  it("retains both dice results when the server advances and clears them", () => {
    const result = rollOffPresentation(before, after, [
      { type: "START_DICE_ROLLED", playerId: "p2", values: [6, 5] },
      { type: "ROLL_OFF_WON", playerId: "p2" },
    ]);
    expect(result.display.game.phase).toBe("DRAFT_ROLL");
    expect(result.display.game.players.map((p) => p.rollValues)).toEqual([[6, 2], [6, 5]]);
    expect(result.outcome).toBe("小红 获得首位招募权");
    expect(before.game.players[1].rollValues).toBeNull();
    expect(after.game.players[1].rollValues).toBeNull();
  });
  it("shows the tied round before exposing the new reroll", () => {
    const result = rollOffPresentation(before, before, [
      { type: "START_DICE_ROLLED", playerId: "p2", values: [6, 2] },
      { type: "ROLL_OFF_TIED", playerIds: ["p1", "p2"] },
    ]);
    expect(result.outcome).toBe("小明、小红 点数相同，需要重掷");
    expect(result.display.game.players[1].rollValues).toEqual([6, 2]);
  });
});

describe("action moments", () => {
  it("explains a kick using its actual source, victim and displacement", () => {
    const result = actionMoment({ type: "RACER_MOVED", playerId: "p2", athleteId: "banana",
      sourcePlayerId: "p1", sourceAthleteId: "centaur", source: "CentaurTrample", from: 1, to: 0 }, players)!;
    expect(result.cause).toBe("半人马经过香蕉");
    expect(result.effect).toBe("后退 1 格"); // Clamped at the start, not the generic skill's -2.
    expect(result.source.owner).toBe("小明");
    expect(result.target.owner).toBe("小红");
  });
  it("distinguishes passing the banana from the banana moving", () => {
    const result = actionMoment({ type: "RACER_TRIPPED", playerId: "p1", athleteId: "centaur",
      sourcePlayerId: "p2", sourceAthleteId: "banana", source: "BananaTrip" }, players)!;
    expect(result.cause).toBe("半人马经过香蕉");
    expect(result.effect).toBe("绊倒");
  });
  it("keeps the catalog name when the server sends its English card face", () => {
    const result = actionMoment({ type: "ABILITY_TRIGGERED", playerId: "p1", athleteId: "centaur",
      sourcePlayerId: "p2", sourceAthleteId: "banana", sourceAthleteName: "Banana",
      abilityName: "BananaTrip" }, players)!;
    expect(result.source.name).toBe("香蕉");
    expect(result.cause).toBe("半人马经过香蕉");
  });
  it("falls back to the wire name only for racers the catalog does not know", () => {
    const result = actionMoment({ type: "ABILITY_TRIGGERED", playerId: "p1", athleteId: "centaur",
      sourcePlayerId: "p2", sourceAthleteId: "newcomer", sourceAthleteName: "Newcomer",
      abilityName: "BananaTrip" }, players)!;
    expect(result.source.name).toBe("Newcomer");
  });
  it("uses player identity when two players have the same athlete", () => {
    const duplicated = [...players, { ...players[0], id: "p3", name: "小林" }];
    const result = actionMoment({ type: "ABILITY_TRIGGERED", playerId: "p3", athleteId: "centaur",
      sourcePlayerId: "p1", sourceAthleteId: "centaur", abilityName: "CoachBoost" }, duplicated)!;
    expect(result.source.owner).toBe("小明");
    expect(result.target.owner).toBe("小林");
  });
});

it("collapses targetless swap summaries but retains both real movements", async () => {
  const { isRedundantAbilityEvent } = await import("./eventPresentation");
  const source = { sourcePlayerId: "p1", sourceAthleteId: "flip_flop" };
  const movement = { type: "RACER_WARPED", ...source, playerId: "p2", athleteId: "banana", source: "FlipFlopSwap", from: 8, to: 2 };
  const summary = { type: "ABILITY_TRIGGERED", ...source, abilityName: "FlipFlopSwap" };
  expect(isRedundantAbilityEvent(summary, [movement, summary])).toBe(true);
  expect(isRedundantAbilityEvent(movement, [movement, summary])).toBe(false);
  expect(isRedundantAbilityEvent({ ...summary, sourcePlayerId: "p3" }, [movement])).toBe(false);
});

it("reports a copied Legs ability as a jog instead of a die choice", () => {
  const event = { type: "ABILITY_TRIGGERED", playerId: "p1", athleteId: "centaur", sourcePlayerId: "p1", sourceAthleteId: "centaur", abilityName: "LongLegs" };
  const moment = actionMoment(event, players)!;
  expect(moment.cause).toBe("半人马选择慢跑");
  expect(moment.effect).toBe("跳过掷骰，改为移动 5 格");
});

it("shows who the suckerfish actually followed, rather than pointing at itself", () => {
  const moment = actionMoment({ type: "RACER_MOVED", source: "SuckerfishRide",
    playerId: "p2", athleteId: "banana", sourcePlayerId: "p2", sourceAthleteId: "banana", sourceAthleteName: "吸盘鱼",
    triggerPlayerId: "p1", triggerAthleteId: "centaur", triggerAthleteName: "半人马", from: 4, to: 8,
  }, players)!;
  expect(moment.source.name).toBe("半人马");
  expect(moment.source.owner).toBe("小明");
  expect(moment.target.owner).toBe("小红");
  expect(moment.cause).toContain("半人马从同格离开");
  expect(moment.effect).toBe("前进 4 格");
});

describe("race feed sentences", () => {
  it("omits the die line for a main move that skipped rolling", () => {
    const line = eventText({ type: "DICE_ROLLED", playerId: "p1", athleteId: "centaur",
      value: 5, values: [], baseValue: 5, finalValue: 5, noDice: true }, players);
    expect(line).toBe("");
  });

  it("names the athlete that landed on a trip tile", () => {
    const line = eventText({ type: "RACER_TRIPPED", playerId: "p2", athleteId: "banana", source: "TripTile" }, players);
    expect(line).toBe("香蕉落在绊倒格 → 小红的香蕉：绊倒");
  });

  it("announces an automatic deal with the number of cards", () => {
    const line = eventText({ type: "TEAM_DEALT", playerId: "p1",
      athleteIds: ["centaur", "banana", "coach", "hare"] }, players);
    expect(line).toBe("小明 自动获得 4 名赛车手");
  });

  it("reports which option a player picked, in Chinese", () => {
    const line = eventText({ type: "DECISION_RESOLVED", playerId: "p2", athleteId: "banana",
      athleteName: "香蕉", abilityName: "BananaTrip", optionId: "1", optionLabel: "Banana" }, players);
    expect(line).toBe("小红 的「滑倒吧」选择：香蕉");
  });

  it("reports an automatic choice when the timer runs out", () => {
    const line = eventText({ type: "DECISION_TIMED_OUT", playerId: "p1", abilityName: "DuelistDuel" }, players);
    expect(line).toBe("小明 超时未选，「决斗」由系统自动决定");
  });

  it("announces pending choices and recovery from a trip", () => {
    expect(eventText({ type: "DECISION_REQUIRED", playerId: "p1", athleteId: "centaur",
      athleteName: "半人马", abilityName: "FlipFlopSwap" }, players))
      .toBe("小明 的半人马使用「人字互换」，等待选择");
    expect(eventText({ type: "TRIP_RECOVERED", playerId: "p1", athleteId: "centaur" }, players))
      .toBe("小明 的半人马从绊倒中恢复，跳过本次移动");
  });
});

it.each([1, 13])("presents a star award for landing on Wild Wilds space %i", (to) => {
  const moment = landingScoreMoment({ type: "RACER_MOVED", playerId: "p2", athleteId: "banana", from: 0, to }, "WildWilds", players)!;
  expect(moment.target.athleteId).toBe("banana");
  expect(moment.scoreAmount).toBe(1);
  expect(moment.effect).toBe("获得 1 分");
});

it("does not award points for passing, staying still, or the Standard board", () => {
  const move = { type: "RACER_MOVED", playerId: "p2", athleteId: "banana", from: 0, to: 2 };
  expect(landingScoreMoment(move, "WildWilds", players)).toBeNull();
  expect(landingScoreMoment({ ...move, from: 1, to: 1 }, "WildWilds", players)).toBeNull();
  expect(landingScoreMoment({ ...move, to: 1 }, "Standard", players)).toBeNull();
  expect(landingScoreMoment({ ...move, type: "RACER_WARPED", to: 13 }, "WildWilds", players)?.scoreAmount).toBe(1);
});
