import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { PlayerState, PropItem, PropThrow } from "../protocol";
import "./taunts.css";

export function propEmoji(item: PropItem): string { return item === "egg" ? "🥚" : "🍅"; }

export function TauntPanel({ players, viewerId, connected, latest, error, onThrow }: {
  players: PlayerState[]; viewerId: string; connected: boolean; latest: PropThrow | null;
  error: string; onThrow: (targetPlayerId: string, item: PropItem) => boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [targetId, setTargetId] = useState("");
  const [readyAt, setReadyAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const dialog = useRef<HTMLDialogElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const available = players.filter(player => player.id !== viewerId);
  const target = available.find(player => player.id === targetId);
  const remaining = Math.max(0, Math.ceil((readyAt - now) / 1000));
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else if (dialog.current?.open) { dialog.current.close(); toggle.current?.focus({ preventScroll: true }); }
  }, [open]);
  useEffect(() => {
    if (readyAt <= Date.now()) return;
    const timer = window.setInterval(() => {
      const next = Date.now(); setNow(next);
      if (next >= readyAt) window.clearInterval(timer);
    }, 200);
    return () => window.clearInterval(timer);
  }, [readyAt]);
  useEffect(() => {
    if (latest?.actorId === viewerId) { setReadyAt(Date.now() + latest.cooldownMs); setNow(Date.now()); }
  }, [latest, viewerId]);
  function toss(item: PropItem) {
    if (!target || remaining || !connected) return;
    if (onThrow(target.id, item)) {
      setReadyAt(Date.now() + 4000); setNow(Date.now()); setOpen(false);
    }
  }
  return <>
    <button ref={toggle} className="taunt-toggle" aria-haspopup="dialog" aria-expanded={open} aria-controls="race-taunts" onClick={() => setOpen(true)}><span aria-hidden="true">🍅</span> {t("taunts.open")}</button>
    <dialog ref={dialog} id="race-taunts" className="taunt-dialog" aria-labelledby="taunt-title" onCancel={() => setOpen(false)} onClose={() => setOpen(false)} onClick={event => {
      if (event.target !== event.currentTarget) return;
      const rect=event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) setOpen(false);
    }}>
      <header><div><small>{t("taunts.subtitle")}</small><h2 id="taunt-title">{t("taunts.title")}</h2></div><button className="taunt-close" aria-label={t("common.close")} onClick={() => setOpen(false)}>×</button></header>
      <p>{t("taunts.pickTarget")}</p>
      <div className="taunt-targets" role="group" aria-label={t("taunts.pickTarget")}>{available.map(player => <button key={player.id} aria-pressed={player.id === targetId} onClick={() => setTargetId(player.id)}><strong>{player.name}</strong><small>{t("race.standingSpace", { position: player.position })}</small></button>)}</div>
      <div className="taunt-items">{(["egg", "tomato"] as const).map(item => <button key={item} disabled={!target || !connected || remaining > 0} onClick={() => toss(item)}><span aria-hidden="true">{propEmoji(item)}</span><strong>{t(`taunts.${item}`)}</strong></button>)}</div>
      <p className="taunt-hint" aria-live="polite">{!connected ? t("status.disconnected") : remaining ? t("taunts.cooldown", { seconds: remaining }) : target ? t("taunts.aiming", { name: target.name }) : t("taunts.pickHint")}</p>
      {error && <p className="taunt-error" role="alert">{error}</p>}
      {latest && <p className="taunt-latest">{propEmoji(latest.item)} {t("taunts.thrown", { actor: latest.actorName, target: latest.targetName, item: t(`taunts.${latest.item}`) })}</p>}
    </dialog>
  </>;
}
