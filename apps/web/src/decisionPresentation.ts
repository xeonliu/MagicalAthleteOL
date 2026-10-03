import type { TFunction } from "i18next";

import i18n from "./i18n";
import { abilityOwner, abilityTitle, athleteText, racerLabel } from "./i18n/athletes";
import type { GameEvent, PendingDecision } from "./protocol";

function athleteNameOf(t: TFunction, decision: PendingDecision): string {
  return athleteText(t, { id: decision.athleteId, name: decision.athleteName }).name;
}

export function decisionTitle(decision: PendingDecision, t: TFunction = i18n.t): string {
  if (abilityOwner(decision.abilityName)) return abilityTitle(t, decision.abilityName);
  return t("race:decision.titleFallback", { athlete: athleteNameOf(t, decision) });
}

export type DecisionOutcome = { optionId: string | null; automatic: boolean; playerId: string; managed?: boolean };

export type DecisionDialogState = { decision: PendingDecision; outcome: DecisionOutcome | null };

// Manual submissions close immediately; automated choices replay for their owner too.
export function resolvedDecisionDialog(
  current: DecisionDialogState | null,
  events: GameEvent[],
  viewerId: string,
): DecisionDialogState | null {
  if (!current) return null;
  const outcome = decisionResolution(current.decision, events);
  if (current.decision.playerId === viewerId && !outcome?.managed && !outcome?.automatic) return null;
  return outcome ? { decision: current.decision, outcome } : null;
}

export function decisionResolution(
  decision: PendingDecision | null | undefined,
  events: GameEvent[],
): DecisionOutcome | null {
  if (!decision) return null;
  const resolved = events.find((event) =>
    (event.type === "DECISION_RESOLVED" || event.type === "DECISION_TIMED_OUT")
    && event.decisionId === decision.id);
  if (!resolved) return null;
  return {
    optionId: resolved.optionId || null,
    automatic: Boolean(resolved.automatic) || resolved.type === "DECISION_TIMED_OUT",
    playerId: resolved.playerId ?? decision.playerId,
    ...(resolved.bot ? { managed: true } : {}),
  };
}

export function abilityTitleText(abilityName?: string, t: TFunction = i18n.t): string {
  return abilityTitle(t, abilityName);
}

export function decisionOptionLabel(label: string, t: TFunction = i18n.t): string {
  if (label === "skip") return t("race:decision.skip");
  if (label === "use") return t("race:decision.use");
  return racerLabel(t, label);
}

export function decisionPrompt(decision: PendingDecision, t: TFunction = i18n.t): string {
  if (decision.abilityName === "SuckerfishRide" && decision.effectPreview) {
    const preview = decision.effectPreview;
    return t("race:decision.suckerfishFollow", {
      name: athleteText(t, { id: preview.athleteId ?? "", name: preview.athleteName }).name,
      from: preview.from,
      to: preview.to,
    });
  }
  const promptKey = `race:decision.prompt.${decision.abilityName}`;
  if (decision.abilityName && i18n.exists(promptKey)) return t(promptKey);
  if (decision.choiceType === "DIE") return t("race:decision.chooseDie");
  if (decision.choiceType === "TILE") return t("race:decision.chooseTile");
  if (decision.abilityName === "TwinCopy" || decision.abilityName === "EggCopy") {
    return t("race:decision.chooseCopy");
  }
  if (decision.choiceType === "RACER") return t("race:decision.chooseRacer");
  if (decision.choiceType === "BOOLEAN") {
    return t("race:decision.useAbility", { ability: decisionTitle(decision, t) });
  }
  return t("race:decision.chooseAction");
}
