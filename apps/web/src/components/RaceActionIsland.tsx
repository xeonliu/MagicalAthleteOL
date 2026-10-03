import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { ActionMoment as Moment } from "../eventPresentation";
import { ActionMoment } from "./ActionMoment";
import "./race-action-island.css";

/** Keep one shell mounted so every action grows out of the roll control. */
export function RaceActionIsland({ moment, busy, status, children, decision }: {
  decision?: ReactNode; moment?: Moment | null; busy: boolean; status: string; children: ReactNode;
}) {
  const shellRef = useRef<HTMLDivElement>(null);
  const [floating, setFloating] = useState(false);
  useEffect(() => {
    const query = window.matchMedia?.("(max-width: 700px), (max-height: 500px) and (max-width: 980px)");
    if (!query) return;
    const update = () => setFloating(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  useLayoutEffect(() => {
    const shell = shellRef.current;
    const stage = shell?.closest<HTMLElement>(".race-stage");
    if (!shell || !stage || floating) return;
    const leftButton = stage.querySelector<HTMLElement>(".race-details-toggle");
    const rightButtons = stage.querySelector<HTMLElement>(".camera-controls");
    const measure = () => {
      const bounds = stage.getBoundingClientRect();
      const left = leftButton ? leftButton.getBoundingClientRect().right - bounds.left + 16 : 12;
      const right = rightButtons ? rightButtons.getBoundingClientRect().left - bounds.left - 16 : bounds.width - 12;
      shell.style.setProperty("--island-center", `${(left + right) / 2}px`);
      shell.style.setProperty("--island-available-width", `${Math.max(0, right - left)}px`);
    };
    measure();
    const observer = new ResizeObserver(measure);
    [stage, leftButton, rightButtons].forEach(node => { if (node) observer.observe(node); });
    window.addEventListener("resize", measure);
    return () => { observer.disconnect(); window.removeEventListener("resize", measure); };
  }, [floating]);
  const [lastMoment, setLastMoment] = useState(moment);
  useEffect(() => {
    if (moment) { setLastMoment(moment); return; }
    const timer = window.setTimeout(() => setLastMoment(null), 600);
    return () => window.clearTimeout(timer);
  }, [moment]);
  const contentRef = useRef<HTMLDivElement>(null);
  const hasDecision = !!decision;
  useEffect(() => {
    if (hasDecision) contentRef.current?.querySelector<HTMLElement>('[role="dialog"]')?.focus({ preventScroll: true });
  }, [hasDecision, floating]);
  const expanded = hasDecision || !!moment || busy;
  const displayedMoment = moment ?? (!busy ? lastMoment : null);
  const island = <div ref={shellRef} className={`table-dice-hud race-action-island${expanded ? " is-expanded" : ""}${moment ? " has-moment" : ""}${hasDecision ? " has-decision" : ""}`}>
    <div className="island-controls" aria-hidden={expanded}>
      <div><strong>{status}</strong>{!expanded && children}</div>
    </div>
    <div className="island-expansion" aria-hidden={!expanded}>
      <div className="island-content" ref={contentRef}>
        {decision || (displayedMoment ? <ActionMoment moment={displayedMoment} /> : <div className="island-rolling" role="status">
          <span className={busy ? "island-die spinning" : "island-die"} aria-hidden="true">⚄</span>
          <strong>{status}</strong>
          <span className="island-pulse" aria-hidden="true"><i /><i /><i /></span>
        </div>)}
      </div>
    </div>
  </div>;
  return floating ? createPortal(island, document.body) : island;
}
