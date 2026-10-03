import type { TFunction } from "i18next";

import i18n from "./index";

/**
 * Wire ability identifiers come from the rules engine, so they never change with
 * language. Each one belongs to a racer, whose card face supplies the display name.
 */
const ABILITY_OWNER: Record<string, string> = {
  AlchemistAlchemy: "alchemist",
  BabaYagaTrip: "baba_yaga",
  BananaTrip: "banana",
  BlimpModifierManager: "blimp",
  CentaurTrample: "centaur",
  CheerleaderSupport: "cheerleader",
  CoachAura: "coach",
  CopyLead: "copycat",
  DicemongerDeal: "dicemonger",
  DicemongerRerollManager: "dicemonger",
  DuelistDuel: "duelist",
  EggCopy: "egg",
  FlipFlopSwap: "flip_flop",
  GeniusPrediction: "genius",
  GunkSlime: "gunk",
  HareHubris: "hare",
  HecklerHeckle: "heckler",
  HugeBabyPush: "huge_baby",
  HypnotistWarp: "hypnotist",
  InchwormCreep: "inchworm",
  LackeyLoyalty: "lackey",
  LeaptoadJumpManager: "leaptoad",
  LongLegs: "legs",
  LovableLoserBonus: "lovable_loser",
  MagicalReroll: "magician",
  MastermindPredict: "mastermind",
  MouthSwallow: "mouth",
  PartyBoostManager: "party_animal",
  PartyPull: "party_animal",
  RomanticMove: "romantic",
  RocketScientistBoost: "rocket_scientist",
  ScoochStep: "scoocher",
  SisyphusCurse: "sisyphus",
  SkipperTurn: "skipper",
  SticklerStrictFinishManager: "stickler",
  SuckerfishRide: "suckerfish",
  ThirdWheelJoin: "third_wheel",
  TwinCopy: "twin",
};

/** `BabaYaga` on the wire is `baba_yaga` in the athlete catalog. */
export function athleteIdFromWireName(wireName: string): string | null {
  const id = wireName.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
  return i18n.exists(`athletes:${id}.name`) ? id : null;
}

export type AthleteWire = {
  id: string;
  /** English card face from the server, used only when the id is unknown. */
  name?: string;
};

export type AthleteText = {
  name: string;
  abilityTitle: string;
  summary: string;
  details: string;
};

function translate(t: TFunction, key: string, fallback: string | undefined): string {
  if (!fallback) return t(key, { defaultValue: "" });
  return t(key, { defaultValue: fallback });
}

/**
 * Card text lives in the client bundle, keyed by the language-independent athlete
 * id. Server-supplied fields stay as the fallback for ids we do not know yet.
 */
export function athleteText(t: TFunction, athlete: AthleteWire): AthleteText {
  return {
    name: translate(t, `athletes:${athlete.id}.name`, athlete.name),
    abilityTitle: translate(t, `athletes:${athlete.id}.abilityTitle`, undefined),
    summary: translate(t, `athletes:${athlete.id}.summary`, undefined),
    details: translate(t, `athletes:${athlete.id}.details`, undefined),
  };
}

export function abilityOwner(abilityName?: string): string | null {
  if (!abilityName) return null;
  return ABILITY_OWNER[abilityName] ?? null;
}

export function abilityTitle(t: TFunction, abilityName?: string): string {
  if (!abilityName) return t("race:ability.unknown");
  const owner = abilityOwner(abilityName);
  if (owner) return t(`athletes:${owner}.abilityTitle`);
  return t(`race:ability.${abilityName}`, { defaultValue: abilityName });
}

/** Decision options carry racer names on the wire; the catalog supplies the label. */
export function racerLabel(t: TFunction, wireLabel: string): string {
  const id = athleteIdFromWireName(wireLabel);
  if (id) return t(`athletes:${id}.name`);
  if (wireLabel === "skip") return t("race:decision.skip");
  return wireLabel;
}
