import { useTranslation } from "react-i18next";

import { athleteText } from "../i18n/athletes";
import type { AthleteCard } from "../protocol";

export function AthleteSkill({ athlete, copied = false }: {
  athlete: AthleteCard; copied?: boolean;
}) {
  const { t } = useTranslation();
  const card = athleteText(t, athlete);
  return <span className={`athlete-skill-details ${copied ? "copied-ability" : ""}`}>
    {copied && <strong>{t("racer.copiedFrom", { name: card.name })}</strong>}
    <strong>{card.abilityTitle}</strong>
    <span>{card.summary}</span>
    {card.details && <span className="athlete-skill-notes">{card.details}</span>}
  </span>;
}
