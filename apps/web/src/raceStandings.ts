import type { ActiveRacer, PlayerState } from "./protocol";

export interface RaceStanding {
  player: PlayerState;
  playerIndex: number;
  racer: ActiveRacer;
  rank: number | null;
}

const category = (racer: ActiveRacer) => racer.eliminated ? 2 : racer.finished ? 0 : 1;

/** Finish order takes precedence; unfinished racers tie at the same space. */
export function raceStandings(players: PlayerState[]): RaceStanding[] {
  const standings = players.flatMap((player, playerIndex) => player.activeRacers.map((racer) => ({
    player, playerIndex, racer, rank: null as number | null,
  })));
  standings.sort((a, b) => category(a.racer) - category(b.racer)
    || (a.racer.finished && b.racer.finished
      ? (a.racer.finishPosition ?? Number.MAX_SAFE_INTEGER) - (b.racer.finishPosition ?? Number.MAX_SAFE_INTEGER)
      : b.racer.position - a.racer.position));
  standings.forEach((entry, index) => {
    if (entry.racer.eliminated) return;
    const previous = standings[index - 1];
    entry.rank = entry.racer.finished ? entry.racer.finishPosition ?? index + 1
      : previous && !previous.racer.finished && previous.racer.position === entry.racer.position
        ? previous.rank : index + 1;
  });
  return standings;
}
