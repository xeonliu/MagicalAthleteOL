import { useTranslation } from "react-i18next";

import { athleteText } from "../i18n/athletes";
import type { PlayerState } from "../protocol";
import { raceStandings } from "../raceStandings";

const playerColors = ["red", "blue", "yellow", "green", "pink", "purple"];

export function RaceLeaderboard({ players, viewerId, activePlayerId, activeAthleteId }: {
  players: PlayerState[]; viewerId: string; activePlayerId: string | null; activeAthleteId?: string | null;
}) {
  const { t } = useTranslation();
  return <aside className="race-leaderboard" aria-label={t("race.standingsTitle")}>
    <h3>{t("race.standingsTitle")}</h3>
    <ol>{raceStandings(players).map(({ player, playerIndex, racer, rank }) => <li
      key={`${player.id}:${racer.id}`} className={player.id === activePlayerId && racer.id === activeAthleteId ? "active" : ""}>
      <strong className="standing-rank">{rank ?? "—"}</strong>
      <span className={`color-chip ${playerColors[playerIndex]}`} />
      <span className="standing-player"><strong>{player.name}{player.id === viewerId && <small> · {t("common.you")}</small>}</strong>
        <small>{athleteText(t, racer).name}</small></span>
      <span className="standing-position">{racer.eliminated ? t("racer.eliminated")
        : racer.finished ? t("racer.finished") : t("race.standingSpace", { position: racer.position })}
        {racer.tripped && !racer.finished && !racer.eliminated && <small>{t("racer.tripped")}</small>}</span>
    </li>)}</ol>
  </aside>;
}
