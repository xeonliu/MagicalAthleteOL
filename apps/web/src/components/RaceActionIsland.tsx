import { useEffect, useState, type ReactNode } from "react";
import type { ActionMoment as Moment } from "../eventPresentation";
import { ActionMoment } from "./ActionMoment";
import "./race-action-island.css";

/** Keep one shell mounted so every action grows out of the roll control. */
export function RaceActionIsland({ moment, busy, status, children }: {
  moment?: Moment | null; busy: boolean; status: string; children: ReactNode;
}) {
  const [lastMoment, setLastMoment] = useState(moment);
  useEffect(() => {
    if (moment) { setLastMoment(moment); return; }
    const timer = window.setTimeout(() => setLastMoment(null), 600);
    return () => window.clearTimeout(timer);
  }, [moment]);
  const expanded = !!moment || busy;
  const displayedMoment = moment ?? (!busy ? lastMoment : null);
  return <div className={`table-dice-hud race-action-island${expanded ? " is-expanded" : ""}${moment ? " has-moment" : ""}`}>
    <div className="island-controls" aria-hidden={expanded}>
      <div><strong>{status}</strong>{!expanded && children}</div>
    </div>
    <div className="island-expansion" aria-hidden={!expanded}>
      <div className="island-content">
        {displayedMoment ? <ActionMoment moment={displayedMoment} /> : <div className="island-rolling" role="status">
          <span className={busy ? "island-die spinning" : "island-die"} aria-hidden="true">⚄</span>
          <strong>{status}</strong>
          <span className="island-pulse" aria-hidden="true"><i /><i /><i /></span>
        </div>}
      </div>
    </div>
  </div>;
}
