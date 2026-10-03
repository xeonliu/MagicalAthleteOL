import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { athleteText } from "../i18n/athletes";
import { AthleteSkill } from "./AthleteSkill";
import { createPortal } from "react-dom";
import type { AthleteCard } from "../protocol";

/** Rules stay readable outside scrolling card grids, including disabled cards. */
export function AthleteRules({ athlete, children }: { athlete: AthleteCard; children: ReactNode }) {
  const { t } = useTranslation();
  const card = athleteText(t, athlete);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 12, top: 12 });
  const anchor = useRef<HTMLDivElement>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout>>();
  const id = useId();
  const show = () => {
    clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const hideSoon = () => {
    clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setOpen(false), 150);
  };

  useEffect(() => () => clearTimeout(closeTimer.current), []);
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      if (!anchor.current || !tooltip.current) return;
      const card = anchor.current.getBoundingClientRect();
      const panel = tooltip.current.getBoundingClientRect();
      const left = Math.max(12, Math.min(card.left, window.innerWidth - panel.width - 12));
      const below = card.bottom + 8;
      const top = below + panel.height <= window.innerHeight - 12
        ? below : Math.max(12, card.top - panel.height - 8);
      setPosition({ left, top });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, athlete]);

  useEffect(() => {
    if (!open) return;
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!anchor.current?.contains(target) && !tooltip.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("keydown", dismiss);
    document.addEventListener("pointerdown", outside);
    return () => {
      document.removeEventListener("keydown", dismiss);
      document.removeEventListener("pointerdown", outside);
    };
  }, [open]);

  return <div ref={anchor} className="racer-card-with-rules"
    onPointerEnter={(event) => { if (event.pointerType !== "touch") show(); }}
    onPointerLeave={(event) => { if (event.pointerType !== "touch") hideSoon(); }}
    onFocus={(event) => { if (event.target.matches(":focus-visible")) show(); }} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) hideSoon(); }}>
    {children}
    <button type="button" className="racer-rules-button" aria-label={t("racer.rulesLabel", { name: card.name })}
      aria-describedby={open ? id : undefined} aria-expanded={open} onClick={show}>{t("racer.rules")}</button>
    {open && createPortal(<div id={id} ref={tooltip} role="tooltip" className="racer-rules-tooltip"
      style={position} onPointerEnter={show} onPointerLeave={hideSoon}>
      <strong>{card.name} · {card.abilityTitle}</strong>
      <p className="racer-rules-summary">{card.summary}</p>
      {card.details && <p>{card.details}</p>}
      {athlete.copiedAthlete && <AthleteSkill athlete={athlete.copiedAthlete} copied />}
    </div>, document.body)}
  </div>;
}
