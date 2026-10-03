import { describe, expect, it } from "vitest";
import type { ActiveRacer, PlayerState } from "./protocol";
import { raceStandings } from "./raceStandings";

const racer = (id: string, position: number, overrides: Partial<ActiveRacer> = {}): ActiveRacer => ({
  id, name: id, position, finished: false, finishPosition: null, eliminated: false, tripped: false, points: 0, ...overrides,
});
const player = (id: string, racers: ActiveRacer[]) => ({ id, name: id, activeRacers: racers } as PlayerState);

describe("live race standings", () => {
  it("ranks both racers per player, shares ranks on the same space, and updates after movement", () => {
    const players = [player("a", [racer("twin", 8), racer("legs", 3)]), player("b", [racer("genius", 8), racer("coach", 5)])];
    expect(raceStandings(players).map(({ racer, rank }) => [racer.id, rank])).toEqual([
      ["twin", 1], ["genius", 1], ["coach", 3], ["legs", 4],
    ]);
    players[0].activeRacers[1].position = 10;
    expect(raceStandings(players).map(({ racer, rank }) => [racer.id, rank])).toEqual([
      ["legs", 1], ["twin", 2], ["genius", 2], ["coach", 4],
    ]);
    expect(players[0].activeRacers.map(({ id }) => id)).toEqual(["twin", "legs"]);
  });

  it("keeps official finish order and places eliminated racers after everyone else", () => {
    const players = [player("a", [racer("last", 30, { finished: true, finishPosition: 2 }), racer("out", 30, { eliminated: true })]),
      player("b", [racer("first", 29, { finished: true, finishPosition: 1 }), racer("moving", 28, { tripped: true })])];
    expect(raceStandings(players).map(({ racer, rank }) => [racer.id, rank])).toEqual([
      ["first", 1], ["last", 2], ["moving", 3], ["out", null],
    ]);
  });
});
