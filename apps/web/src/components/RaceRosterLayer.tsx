import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import "./race-roster-layer.css";

export function RaceRosterLayer({ open, inline = false, onClose, children }: { inline?: boolean; open: boolean; onClose: () => void; children: ReactNode }) {
  const { t } = useTranslation();
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open || inline) return;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.focus({ preventScroll: true });
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") close.current();
    };
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("keydown", escape); trigger?.focus({ preventScroll: true }); };
  }, [open, inline]);
  if (inline) return <>{children}</>;
  if (!open) return <div hidden>{children}</div>;
  return createPortal(<div className="race-roster-layer" onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={panel} className="race-roster-panel" role="dialog" aria-label={t("race.cardsTitle")} tabIndex={-1}>
      <button className="race-roster-close" onClick={onClose} aria-label={t("race.hideCards")}>×</button>
      {children}
    </div>
  </div>, document.body);
}
