import { useTranslation } from "react-i18next";

import type { ActionMoment as Moment, Participant } from "../eventPresentation";
import { assetUrl } from "../runtimeConfig";

function Actor({ actor, label, diceText }: { actor: Participant; label: string; diceText: string }) {
  return <div className="moment-actor">
    <small>{label}</small>
    {actor.athleteId ? <img src={assetUrl(`assets/racer-tokens/${actor.athleteId}.webp`)} alt="" /> : <span className="moment-symbol" aria-hidden="true">{actor.name === diceText ? "⚄" : "◇"}</span>}
    <strong>{actor.name}</strong><small>{actor.owner}</small>
  </div>;
}

export function ActionMoment({ moment }: { moment: Moment }) {
  const { t } = useTranslation();
  const diceText = t("race:source.dice");
  return <aside className="action-moment" role="status" aria-live="polite">
    <p>{moment.cause}</p>
    <div className="moment-flow">
      <Actor actor={moment.source} label={t("momentFlow.source")} diceText={diceText} />
      <div className="moment-effect">{moment.scoreAmount !== undefined ? <img key={`${moment.target.playerId}-${moment.target.athleteId}`} className="score-star-award" src={assetUrl("assets/score-chips/star-1.webp")} alt="" /> : <span aria-hidden="true">⟶</span>}<strong>{moment.effect}</strong>
        {moment.from !== undefined && moment.to !== undefined && <div className="moment-positions"><b>{moment.from}</b><span>→</span><b>{moment.to}</b><small>{t("momentFlow.space")}</small></div>}
      </div>
      <Actor actor={moment.target} label={t("momentFlow.target")} diceText={diceText} />
    </div>
  </aside>;
}
