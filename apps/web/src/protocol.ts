export type GamePhase =
  | "LOBBY"
  | "DRAFT_ROLL"
  | "DRAFTING"
  | "RACE_ROLL"
  | "CHARACTER_SELECTION"
  | "RACING"
  | "RACE_RESULTS"
  | "FINISHED";

export interface AthleteCard {
  id: string;
  name: string;
  copiedAthlete?: { id: string; name: string } | null;
}

export interface ActiveRacer extends AthleteCard {
  position: number;
  points: number;
  finished: boolean;
  finishPosition: number | null;
  eliminated: boolean;
  tripped: boolean;
}

export interface PlayerState {
  id: string;
  name: string;
  position: number;
  connected: boolean;
  isBot: boolean;
  autoPlay?: boolean;
  score: number;
  selectionLocked: boolean;
  selectedAthlete: ActiveRacer | null;
  activeRacers: ActiveRacer[];
  team: AthleteCard[];
  usedAthleteIds: string[];
  rollValues: number[] | null;
}

export interface RaceResult {
  playerId: string;
  athlete: AthleteCard;
  finishPosition: number | null;
  points: number;
  position: number | null;
  eliminated: boolean;
}

export interface DecisionOption { id: string; label: string; ownerName?: string; position?: number; athlete?: AthleteCard }
export interface RollPreview {
  rollSerial: number;
  value: number;
  baseValue: number;
  finalValue: number;
  rollSessionId?: string;
  rollResultId?: string;
}
export interface PendingDecision {
  id: string;
  playerId: string;
  athleteId: string;
  athleteName: string;
  abilityName: string;
  prompt: string;
  choiceType: "BOOLEAN" | "RACER" | "TILE" | "DIE";
  options: DecisionOption[];
  effectPreview?: { athleteId?: string; athleteName: string; from: number; to: number };
  rollPreview?: RollPreview;
  deadlineAt?: string;
}

export interface RollParticipant {
  playerId: string;
  athleteId: string;
  athleteName?: string;
  value?: number;
}

export interface PendingRoll {
  id: string;
  kind: "MAIN_ROLL" | "ABILITY_ROLL";
  abilityName?: string | null;
  participants: RollParticipant[];
  values: number[];
  nextPlayerId: string;
  nextAthleteId: string;
  nextAthleteName: string;
  throwIndex: number;
  throwCount: number;
  deadlineAt?: string;
}

export interface GameState {
  phase: GamePhase;
  finishLine: number;
  players: PlayerState[];
  hand: AthleteCard[];
  activePlayerId: string | null;
  activeAthleteId?: string | null;
  winnerId: string | null;
  winnerIds: string[];
  raceNumber: number;
  trackName: "Standard" | "WildWilds";
  raceRewards: [number, number];
  doubleRacerVariant: boolean;
  autoDeal: boolean;
  cardsPerPlayer: number;
  selectionCount: number;
  draftPool: AthleteCard[];
  draftRound: number;
  draftRoundCount: number;
  rollCandidateIds: string[];
  raceResults: RaceResult[];
  previousWinners?: AthleteCard[];
  pendingDecision: PendingDecision | null;
  pendingRoll: PendingRoll | null;
  raceLog: GameEvent[];
  resolutionStatus: "IDLE" | "ANIMATING" | "WAITING_FOR_DECISION" | "WAITING_FOR_ROLL";
}

export interface RoomSnapshot {
  roomId: string;
  revision: number;
  game: GameState;
  viewerRole?: "player" | "spectator";
  spectators?: { id: string; name: string; connected: boolean }[];
}

export interface DiceRollResult {
  id: string;
  playerId?: string;
  athleteId?: string;
  values: number[];
  baseValue?: number;
  finalValue?: number;
  rollSerial?: number;
  noDice?: boolean;
  kind?: "MAIN_ROLL" | "ABILITY_ROLL" | "ROLL_OFF";
  participants?: RollParticipant[];
  abilityName?: string | null;
  rollSessionId?: string;
  throwIndex?: number;
  throwCount?: number;
}

export type PropItem = "egg" | "tomato";
export interface PropThrow {
  type: "PROP_THROWN";
  id: string;
  actorId: string;
  actorName: string;
  targetPlayerId: string;
  targetName: string;
  item: PropItem;
  cooldownMs: number;
}

export type ServerMessage =
  | PropThrow
  | { type: "ROOM_LEFT" }
  | { type: "KICKED" }
  | (RoomSnapshot & { type: "WELCOME"; playerId: string; reconnectToken: string })
  | (RoomSnapshot & { type: "STATE_UPDATED"; actionId?: string; events: GameEvent[]; rollResults: DiceRollResult[] })
  | (RoomSnapshot & { type: "ROLL_STARTED"; actionId: string; playerId: string })
  | { type: "ACTION_ACK"; actionId: string; revision: number }
  | { type: "ERROR"; code: string; message: string; actionId?: string };

export type GameEvent = {
  type: string;
  playerName?: string;
  reason?: string;
  playerId?: string;
  playerIds?: string[];
  athleteId?: string;
  athleteIds?: string[];
  values?: number[];
  value?: number;
  baseValue?: number;
  finalValue?: number;
  rollSerial?: number;
  noDice?: boolean;
  finishPosition?: number;
  raceNumber?: number;
  from?: number;
  to?: number;
  movementKind?: "FORWARD" | "BACKWARD" | "WARP" | "SWAP" | "PUSH";
  source?: string;
  sourcePlayerId?: string;
  sourceAthleteId?: string;
  sourceAthleteName?: string;
  triggerPlayerId?: string;
  triggerAthleteId?: string;
  triggerAthleteName?: string;
  abilityName?: string;
  athleteName?: string;
  optionLabel?: string;
  movementDistance?: number;
  decisionId?: string;
  optionId?: string;
  automatic?: boolean;
  bot?: boolean;
  sequence?: number;
  kind?: "MAIN_ROLL" | "ABILITY_ROLL" | "ROLL_OFF";
  rollSessionId?: string;
  rollResultId?: string;
  throwIndex?: number;
  throwCount?: number;
  participants?: RollParticipant[];
  winnerPlayerId?: string;
  winnerAthleteId?: string;
};

export type ClientIntent =
  | { type: "LEAVE_ROOM"; actionId: string }
  | { type: "KICK_PLAYER"; actionId: string; targetPlayerId: string }
  | { type: "ADD_BOT"; actionId: string }
  | { type: "JOIN_ROOM"; roomId: string; playerName: string; playerId?: string; reconnectToken?: string; role?: "player" | "spectator" }
  | { type: "START_GAME"; actionId: string }
  | { type: "SET_VARIANT"; actionId: string; doubleRacer: boolean }
  | { type: "SET_AUTO_DEAL"; actionId: string; autoDeal: boolean }
  | { type: "SET_AUTO_PLAY"; actionId: string; enabled: boolean }
  | { type: "THROW_PROP"; actionId: string; targetPlayerId: string; item: PropItem }
  | { type: "ROLL_START"; actionId: string }
  | { type: "DRAFT_ATHLETE"; actionId: string; athleteId: string }
  | { type: "SELECT_RACERS"; actionId: string; athleteIds: string[] }
  | { type: "ROLL_DICE"; actionId: string }
  | { type: "RESOLVE_DECISION"; actionId: string; decisionId: string; optionId: string }
  | { type: "ADVANCE_RACE"; actionId: string };
