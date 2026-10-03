import React, { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import { useTranslation } from "react-i18next";

import { RaceTableScene } from "./components/race3d/RaceTableScene";
import { RaceRewards } from "./components/RaceRewards";
import { ActionMoment } from "./components/ActionMoment";
import { landingScoreMoment, type ActionMoment as Moment } from "./eventPresentation";
import { playCharacterScoreSound, playMoveSound, unlockGameAudio } from "./gameAudio";
import { RaceTrack } from "./components/RaceTrack";
import type { PlayerState } from "./protocol";
import "./i18n";
import "./styles.css";
import "./art-pack.css";
import { applyArtPack } from "./artPack";

applyArtPack();

const athlete = (id: string, position: number, state: Partial<{ tripped: boolean; finished: boolean; finishPosition: number; eliminated: boolean }> = {}) => ({
  id, name: id, position, points: 0,
  finished: state.finished ?? false, finishPosition: state.finishPosition ?? null,
  eliminated: state.eliminated ?? false, tripped: state.tripped ?? false,
});
const ids = ["genius", "banana", "centaur", "baba_yaga", "magician", "hare"];
const players = ids.map((id, index): PlayerState => ({
  id: `p${index}`, name: `Player ${index + 1}`, position: index < 3 ? 8 : 0, connected: true, isBot: false, score: 0,
  selectionLocked: true, selectedAthlete: athlete(id, index < 3 ? 8 : index * 5, index === 1 ? { tripped: true } : index === 4 ? { finished: true, finishPosition: 1 } : index === 5 ? { eliminated: true } : {}),
  activeRacers: [athlete(id, index < 3 ? 8 : index * 5, index === 1 ? { tripped: true } : index === 4 ? { finished: true, finishPosition: 1 } : index === 5 ? { eliminated: true } : {})],
  team: [], usedAthleteIds: [], rollValues: null,
}));
function BoardPreview() {
  const { t } = useTranslation();
  const [trackName, setTrackName] = useState<"Standard" | "WildWilds">(
    new URLSearchParams(window.location.search).get("track") === "mild" ? "Standard" : "WildWilds",
  );
  const [demoPlayers, setDemoPlayers] = useState(players);
  const [focus, setFocus] = useState<{ athleteId: string; close: boolean } | null>(null);
  const [showRacers, setShowRacers] = useState(true);
  const [view, setView] = useState("3d");
  const [raceNumber, setRaceNumber] = useState(4);
  const [moment, setMoment] = useState<Moment | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);
  const rewards: [number, number][] = [[3, 1], [4, 2], [4, 2], [5, 3]];
  function demoScore() {
    unlockGameAudio();
    timers.current.forEach(window.clearTimeout);
    setDemoBusy(true);
    setMoment(null);
    setTrackName("WildWilds");
    setShowRacers(true);
    setFocus({ athleteId: "genius", close: true });
    const before = demoPlayers.map((player, index) => index ? player : { ...player,
      activeRacers: player.activeRacers.map(racer => ({ ...racer, position: 12, points: 0 })) });
    setDemoPlayers(before);
    timers.current = [window.setTimeout(() => {
      const landed = before.map((player, index) => index ? player : { ...player,
        activeRacers: player.activeRacers.map(racer => ({ ...racer, position: 13 })) });
      setDemoPlayers(landed);
      playMoveSound();
      timers.current.push(window.setTimeout(() => {
        setMoment(landingScoreMoment({ type: "RACER_MOVED", playerId: "p0", athleteId: "genius", from: 12, to: 13 }, "WildWilds", landed, t));
        setDemoPlayers(landed.map((player, index) => index ? player : { ...player,
          activeRacers: player.activeRacers.map(racer => ({ ...racer, points: 1 })) }));
        playCharacterScoreSound();
        timers.current.push(window.setTimeout(() => { setMoment(null); setDemoBusy(false); }, 2300));
      }, 340));
    }, 700)];
  }
  const trackTitle = trackName === "Standard" ? "Mild Mile" : "Wild Wilds";
  const visiblePlayers = showRacers ? demoPlayers : [];

  return <main className={`table ${view === "3d" ? "immersive-race" : ""}`}><section className="stage race-stage">
  <div className="race-heading"><div><p className="kicker">{t("preview.title")}</p><h2>{trackTitle}</h2></div><RaceRewards rewards={rewards[raceNumber - 1]} /></div>
  <div className="board-preview-controls">
    <label>{t("preview.rewards")} <select value={raceNumber} onChange={event => setRaceNumber(Number(event.target.value))}>
      {rewards.map(([gold, silver], index) => <option key={index} value={index + 1}>{t("preview.raceRewards", { race: index + 1, gold, silver })}</option>)}
    </select></label>
    <button className="command primary" disabled={demoBusy} onClick={demoScore}>{t("preview.demoScore")}</button>
    <div className="variant-control" aria-label={t("preview.selectTrack")}>
      <button className={trackName === "Standard" ? "active" : ""} aria-pressed={trackName === "Standard"}
        disabled={demoBusy} onClick={() => setTrackName("Standard")}>Mild Mile</button>
      <button className={trackName === "WildWilds" ? "active" : ""} aria-pressed={trackName === "WildWilds"}
        disabled={demoBusy} onClick={() => setTrackName("WildWilds")}>Wild Wilds</button>
    </div>
    <div className="variant-control" aria-label={t("preview.view")}>
      <button className={view === "3d" ? "active" : ""} aria-pressed={view === "3d"} onClick={() => setView("3d")}>{t("preview.perspective")}</button>
      <button className={view === "2d" ? "active" : ""} aria-pressed={view === "2d"} onClick={() => setView("2d")}>{t("preview.topDown")}</button>
    </div>
    <button className="command secondary" aria-pressed={showRacers}
      disabled={demoBusy} onClick={() => setShowRacers(!showRacers)}>{showRacers ? t("preview.hidePieces") : t("preview.showPieces")}</button>
    <button className="command secondary" disabled={demoBusy} onClick={() => {
      setFocus({ athleteId: "genius", close: true });
      setDemoPlayers((current) => current.map((player, index) => index ? player : { ...player,
        activeRacers: player.activeRacers.map((racer) => ({ ...racer, position: (racer.position + 1) % 30 })) }));
    }}>{t("preview.demoMove")}</button>
    <button className="command secondary" disabled={demoBusy} onClick={() => setFocus({ athleteId: "banana", close: true })}>{t("preview.abilityCloseUp")}</button>
  </div>
  {view === "2d" && moment && <ActionMoment moment={moment} />}
  {view === "2d" ? <div className="track-wrap"><RaceTrack moment={moment} players={visiblePlayers} finishLine={30} trackName={trackName} /></div>
    : <RaceTableScene moment={moment} focus={focus} activePlayerId="p0" players={visiblePlayers} finishLine={30} trackName={trackName} dice={{
    enabled: false,
    targetValue: null,
    restingValue: 4,
    rollKey: "preview",
    autoThrow: false,
    resetKey: 0,
    activePlayerName: t("preview.player", { index: 1 }),
    onThrow: () => undefined,
    onSettled: () => undefined,
  }} />}
</section></main>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<BoardPreview />);
