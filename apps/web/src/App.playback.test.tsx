import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import type { GameState, PendingDecision, ServerMessage } from "./protocol";
import type { RaceTableSceneProps } from "./components/race3d/RaceTableScene";
import { AthleteSkill } from "./components/AthleteSkill";
import { RaceLeaderboard } from "./components/RaceLeaderboard";
import { TauntPanel } from "./components/TauntPanel";

const connection = vi.hoisted(() => ({ receive: (_message: ServerMessage) => {}, send: vi.fn(), join: vi.fn() }));
vi.mock("./gameClient", () => ({
  GameClient: class {
    connect(_intent: unknown, receive: typeof connection.receive, status: (value: string) => void) {
      connection.join(_intent);
      connection.receive = receive;
      status("connected");
    }
    send = connection.send;
    close() {}
  },
  loadSession: () => null, saveSession: vi.fn(), clearSession: vi.fn(),
  roomFromPath: () => "TEST", actionId: () => "local-roll",
}));
vi.mock("./useBackgroundMusic", () => ({ useBackgroundMusic: () => null }));
vi.mock("./gameAudio", () => ({
  playCharacterScoreSound: vi.fn(), playMoveSound: vi.fn(), playFireworkSound: vi.fn(), unlockGameAudio: vi.fn(),
  playTripSound: vi.fn(), playPropImpactSound: vi.fn(),
}));
vi.mock("./components/race3d/RaceTableScene", () => ({ RaceTableScene: (_props: RaceTableSceneProps) => null }));

let App: typeof import("./App").default;
let Scene: typeof import("./components/race3d/RaceTableScene").RaceTableScene;
let view: ReactTestRenderer;
const decision: PendingDecision = {
  id: "d1", playerId: "bot", athleteId: "legs", athleteName: "Legs", abilityName: "LongLegs",
  prompt: "Jog?", choiceType: "BOOLEAN", options: [{ id: "yes", label: "Yes" }, { id: "no", label: "No" }],
};
function game(overrides: Partial<GameState> = {}): GameState {
  return {
    phase: "RACING", finishLine: 30, activePlayerId: "human", activeAthleteId: "banana",
    players: ["human", "bot"].map((id) => ({
      id, name: id, connected: true, isBot: id === "bot", position: 0, score: 0,
      selectionLocked: true, selectedAthlete: null, team: [], usedAthleteIds: [], rollValues: null,
      activeRacers: (id === "human" ? ["banana", "skipper"] : ["legs", "coach"]).map((id) => ({
        id, name: id, position: 0, points: 0, finished: false, finishPosition: null, eliminated: false, tripped: false,
      })),
    })),
    hand: [], winnerId: null, winnerIds: [], raceNumber: 1, trackName: "Standard", raceRewards: [2, 1],
    doubleRacerVariant: true, autoDeal: false, cardsPerPlayer: 8, selectionCount: 2,
    draftPool: [], draftRound: 0, draftRoundCount: 0, rollCandidateIds: [], raceResults: [],
    pendingDecision: null, pendingRoll: null, raceLog: [], resolutionStatus: "WAITING_FOR_ROLL", ...overrides,
  };
}
const scene = () => view.root.findByType(Scene).props as RaceTableSceneProps;
const dialogs = () => view.root.findAllByProps({ role: "dialog" });

it("opens the next human Genius prediction before queued bot animations consume its deadline", async () => {
  const prediction: PendingDecision = {
    id: "predict-first", playerId: "human", athleteId: "genius", athleteName: "Genius",
    abilityName: "GeniusPrediction", prompt: "", choiceType: "DIE",
    options: [1, 2, 3, 4, 5, 6].map(value => ({id: String(value - 1), label: String(value)})),
  };
  await join(game({activeAthleteId: "genius", pendingDecision: prediction, resolutionStatus: "WAITING_FOR_DECISION"}));
  await act(async () => dialogs()[0].findAllByType("button")[4].props.onClick());
  await receive({type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: game(), rollResults: [],
    events: [{type: "DECISION_RESOLVED", decisionId: prediction.id, playerId: "human", optionId: "4"}]});
  await advance(1000);
  const nextPrediction = {...prediction, id: "predict-second", deadlineAt: new Date(Date.now() + 60000).toISOString()};
  for (let i = 0; i < 5; i++) {
    const next = game({activePlayerId: i === 4 ? "human" : "bot", activeAthleteId: i === 4 ? "genius" : "legs",
      pendingDecision: i === 4 ? nextPrediction : null, resolutionStatus: i === 4 ? "WAITING_FOR_DECISION" : "WAITING_FOR_ROLL"});
    next.players[1].activeRacers[0].position = (i + 1) * 4;
    next.raceLog = [{type: "DICE_ROLLED", playerId: "bot", value: 4, rollResultId: `bot-die-${i}`}];
    await receive({type: "STATE_UPDATED", roomId: "TEST", revision: i + 3, game: next,
      rollResults: [{id: `bot-die-${i}`, values: [4]}], events: [
        {type: "RACER_MOVED", playerId: "bot", athleteId: "legs", from: i * 4, to: (i + 1) * 4},
        ...(i === 4 ? [{type: "DECISION_REQUIRED", decisionId: nextPrediction.id, abilityName: "GeniusPrediction"}] : []),
      ]});
  }
  expect(dialogs()).toHaveLength(1);
  expect(dialogs()[0].findAllByType("button")).toHaveLength(6);
  expect(dialogs()[0].findAllByType("button").every(button => !button.props.disabled)).toBe(true);
  expect(scene().players[1].activeRacers[0].position).toBe(20);
  expect(scene().dice.targetValue).toBeNull();
  expect(scene().dice.restingValue).toBe(4);
  await act(async () => dialogs()[0].findAllByType("button")[1].props.onClick());
  expect(connection.send).toHaveBeenLastCalledWith(expect.objectContaining({type: "RESOLVE_DECISION", decisionId: nextPrediction.id, optionId: "1"}));
  const ready = game({activeAthleteId: "genius"});
  ready.players[1].activeRacers[0].position = 20;
  ready.raceLog = [{type: "DICE_ROLLED", playerId: "bot", value: 4}];
  await receive({type: "STATE_UPDATED", roomId: "TEST", revision: 8, game: ready, rollResults: [],
    events: [{type: "DECISION_RESOLVED", decisionId: nextPrediction.id, playerId: "human", optionId: "1"}]});
  await advance(65000);
  expect(dialogs()).toHaveLength(0);
  expect(scene().players[1].activeRacers[0].position).toBe(20);
  expect(scene().dice.enabled).toBe(true);
});
async function receive(message: ServerMessage) { await act(async () => connection.receive(message)); }

it("shows the rolled die and movement before a fresh Genius extra-turn prediction when there is no backlog", async () => {
  await join(game({activeAthleteId: "genius"}));
  const prediction: PendingDecision = {id: "extra-turn-prediction", playerId: "human", athleteId: "genius", athleteName: "Genius",
    abilityName: "GeniusPrediction", prompt: "", choiceType: "DIE",
    options: [1, 2, 3, 4, 5, 6].map(value => ({id: String(value - 1), label: String(value)}))};
  const next = game({activeAthleteId: "genius", pendingDecision: prediction, resolutionStatus: "WAITING_FOR_DECISION"});
  next.players[0].activeRacers[0].position = 6;
  await receive({type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: next,
    rollResults: [{id: "correct-genius-die", values: [6]}],
    events: [{type: "RACER_MOVED", playerId: "human", athleteId: "banana", from: 0, to: 6}]});
  expect(dialogs()).toHaveLength(0);
  expect(scene().dice.targetValue).toBe(6);
  await act(async () => scene().dice.onSettled());
  await advance(6000);
  expect(scene().players[0].activeRacers[0].position).toBe(6);
  expect(dialogs()).toHaveLength(1);
  expect(dialogs()[0].findAllByType("button").every(button => !button.props.disabled)).toBe(true);
});

it("restores a pending Genius prediction immediately when managed play is cancelled during playback", async () => {
  const managed = game({activeAthleteId: "genius"});
  managed.players[0].autoPlay = true;
  await join(managed);
  await receive({type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: managed,
    rollResults: [{id: "queued-bot-die", values: [6]}],
    events: [{type: "RACER_MOVED", playerId: "bot", athleteId: "legs", from: 0, to: 6}]});
  const prediction: PendingDecision = {id: "managed-prediction", playerId: "human", athleteId: "genius", athleteName: "Genius",
    abilityName: "GeniusPrediction", prompt: "", choiceType: "DIE",
    options: [1, 2, 3, 4, 5, 6].map(value => ({id: String(value - 1), label: String(value)}))};
  const waiting: GameState = {...managed, pendingDecision: prediction, resolutionStatus: "WAITING_FOR_DECISION"};
  await receive({type: "STATE_UPDATED", roomId: "TEST", revision: 3, game: waiting, rollResults: [],
    events: [{type: "DECISION_REQUIRED", decisionId: prediction.id, abilityName: "GeniusPrediction"}]});
  expect(dialogs()).toHaveLength(0);
  await act(async () => view.root.findByProps({className: "auto-play-toggle"}).props.onClick());
  expect(connection.send).toHaveBeenLastCalledWith(expect.objectContaining({type: "SET_AUTO_PLAY", enabled: false}));
  const manual = structuredClone(waiting);
  manual.players[0].autoPlay = false;
  await receive({type: "STATE_UPDATED", roomId: "TEST", revision: 4, game: manual, rollResults: [],
    events: [{type: "AUTO_PLAY_CHANGED", playerId: "human"}]});
  expect(dialogs()).toHaveLength(1);
  expect(dialogs()[0].findAllByType("button").every(button => !button.props.disabled)).toBe(true);
  await act(async () => dialogs()[0].findAllByType("button")[3].props.onClick());
  expect(connection.send).toHaveBeenLastCalledWith(expect.objectContaining({type: "RESOLVE_DECISION", decisionId: prediction.id, optionId: "3"}));
});
async function advance(ms: number) { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); }

it("stops old automatic dice playback when managed play is cancelled in the second race", async () => {
  const managed = game({raceNumber: 2, activeAthleteId: "genius"});
  managed.players[0].autoPlay = true;
  await join(managed);
  for (let i = 0; i < 3; i++) {
    const next = structuredClone(managed);
    next.players[0].activeRacers[0].position = (i + 1) * 4;
    next.raceLog = [{type: "DICE_ROLLED", playerId: "human", value: 4}];
    await receive({type: "STATE_UPDATED", roomId: "TEST", revision: i + 2, game: next,
      rollResults: [{id: `managed-die-${i}`, values: [4]}],
      events: [{type: "RACER_MOVED", playerId: "human", athleteId: "banana", from: i * 4, to: (i + 1) * 4}]});
  }
  expect(scene().dice.autoThrow).toBe(true);
  await act(async () => view.root.findByProps({className: "auto-play-toggle"}).props.onClick());
  const manual = structuredClone(managed);
  manual.players[0].autoPlay = false;
  manual.players[0].activeRacers[0].position = 12;
  manual.raceLog = [{type: "DICE_ROLLED", playerId: "human", value: 4}];
  await receive({type: "STATE_UPDATED", roomId: "TEST", revision: 5, game: manual, rollResults: [],
    events: [{type: "AUTO_PLAY_CHANGED", playerId: "human"}]});
  expect(scene().dice.autoThrow).toBe(false);
  expect(scene().dice.targetValue).toBeNull();
  expect(scene().dice.enabled).toBe(true);
  expect(scene().players[0].activeRacers[0].position).toBe(12);
  await advance(65000);
  expect(scene().players[0].activeRacers[0].position).toBe(12);
  expect(scene().dice.enabled).toBe(true);
  expect(connection.send).not.toHaveBeenCalledWith(expect.objectContaining({type: "ROLL_DICE"}));
});
async function join(state: GameState, spectator = false) {
  await act(async () => { view = create(<App />); });
  await act(async () => view.root.findAllByType("input")[0].props.onChange({ target: { value: "human" } }));
  await act(async () => view.root.findAllByType("button").find((button) => button.props.children === (spectator ? "旁观比赛" : "加入房间"))!.props.onClick());
  await receive({ type: "WELCOME", roomId: "TEST", revision: 1, playerId: spectator ? "watcher" : "human", reconnectToken: "token", game: state,
    viewerRole: spectator ? 'spectator' : 'player', spectators: spectator ? [{id: 'watcher', name: 'Watcher', connected: true}] : [] });
}

it("shows cosmetic throws immediately without changing pending dice playback", async () => {
  await join(game());
  await act(async () => scene().dice.onThrow("local-roll"));
  const before = scene();
  await receive({type:"PROP_THROWN", id:"prop-1", actorId:"bot", actorName:"Bot", targetPlayerId:"human", targetName:"Human", item:"egg", cooldownMs:4000});
  expect(scene().taunts?.[0].id).toBe("prop-1");
  expect(scene().players).toEqual(before.players);
  expect(scene().dice.enabled).toBe(before.dice.enabled);
  expect(scene().dice.targetValue).toBe(before.dice.targetValue);
  await receive({type:"ERROR", code:"TAUNT_COOLDOWN", message:"Cooldown", actionId:"taunt-failed"});
  expect(scene().dice.enabled).toBe(false);
  expect(scene().dice.resetKey).toBe(before.dice.resetKey);
  await advance(2300);
  expect(scene().taunts).toEqual([]);
});

it("allows spectator props while retaining read-only gameplay", async () => {
  await join(game(), true);
  await act(async () => view.root.findByType(TauntPanel).props.onThrow("human", "tomato"));
  expect(connection.send).toHaveBeenCalledWith(expect.objectContaining({type:"THROW_PROP", targetPlayerId:"human", item:"tomato", actionId:"taunt-local-roll"}));
  expect(scene().dice.enabled).toBe(false);
});

it("plays each prop cue at the visual collision, once per throw", async () => {
  const audio = await import("./gameAudio");
  await join(game());
  const event = {type: "PROP_THROWN" as const, id: "hit-1", actorId: "bot", actorName: "Bot", targetPlayerId: "human", targetName: "Human", item: "egg" as const, cooldownMs: 4000};
  await receive(event);
  await advance(700);
  expect(audio.playPropImpactSound).not.toHaveBeenCalled();
  act(() => scene().onPropImpact?.(event));
  expect(audio.playPropImpactSound).toHaveBeenCalledTimes(1);
  expect(audio.playPropImpactSound).toHaveBeenLastCalledWith("egg");
  await receive(event);
  act(() => scene().onPropImpact?.(event));
  expect(audio.playPropImpactSound).toHaveBeenCalledTimes(1);
  const tomato = {...event, id: "hit-2", item: "tomato" as const};
  await receive(tomato);
  act(() => scene().onPropImpact?.(tomato));
  expect(audio.playPropImpactSound).toHaveBeenLastCalledWith("tomato");
  expect(audio.playPropImpactSound).toHaveBeenCalledTimes(2);
  expect(scene().dice.enabled).toBe(true);
});

it("plays a trip cue at the trip event and stays silent when reconnecting", async () => {
  const audio = await import("./gameAudio");
  await join(game());
  const tripped = game();
  tripped.players[0].activeRacers[0].tripped = true;
  await receive({type:"STATE_UPDATED", roomId:"TEST", revision:2, game:tripped, rollResults:[], events:[{type:"RACER_TRIPPED", playerId:"human", athleteId:"banana"}]});
  await advance(1649);
  expect(audio.playTripSound).not.toHaveBeenCalled();
  await advance(2);
  expect(audio.playTripSound).toHaveBeenCalledTimes(1);
  await receive({type:"WELCOME", roomId:"TEST", revision:2, playerId:"human", reconnectToken:"token", game:tripped});
  expect(audio.playTripSound).toHaveBeenCalledTimes(1);
});

beforeAll(async () => {
  vi.stubGlobal("window", {
    location: { search: "", hash: "", protocol: "http:" },
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    setTimeout: (...args: Parameters<typeof setTimeout>) => setTimeout(...args),
    clearTimeout: (id: ReturnType<typeof setTimeout>) => clearTimeout(id),
    setInterval: (...args: Parameters<typeof setInterval>) => setInterval(...args),
    clearInterval: (id: ReturnType<typeof setInterval>) => clearInterval(id),
  });
  App = (await import("./App")).default;
  Scene = (await import("./components/race3d/RaceTableScene")).RaceTableScene;
});
beforeEach(() => { vi.useFakeTimers(); connection.send.mockClear(); connection.join.mockClear(); });
afterEach(() => { act(() => view?.unmount()); vi.useRealTimers(); });

it('joins as a spectator, watches movement, and can leave without rolling', async () => {
  await join(game(), true);
  expect(connection.join).toHaveBeenCalledWith(expect.objectContaining({role: 'spectator'}));
  expect(scene().dice.enabled).toBe(false);
  const moved = game();
  moved.players[0].activeRacers[0].position = 3;
  await receive({type: 'STATE_UPDATED', roomId: 'TEST', revision: 2, viewerRole: 'spectator', game: moved, rollResults: [],
    events: [{type: 'RACER_MOVED', playerId: 'human', athleteId: 'banana', from: 0, to: 3}]});
  await advance(5000);
  expect(scene().players[0].activeRacers[0].position).toBe(3);
  expect(scene().dice.enabled).toBe(false);
  await act(async () => view.root.findAllByType('button').find(button => button.props.children === '退出旁观')!.props.onClick());
  expect(connection.send).toHaveBeenCalledWith(expect.objectContaining({type: 'LEAVE_ROOM'}));
  expect(connection.send).not.toHaveBeenCalledWith(expect.objectContaining({type: 'ROLL_DICE'}));
});

it('does not show a spectator private selection controls', async () => {
  await join(game({phase: 'CHARACTER_SELECTION'}), true);
  expect(view.root.findAllByProps({className: 'selection-confirm'})).toHaveLength(0);
  expect(view.root.findAllByType('h2').some(node => node.children.includes('等待玩家选择角色'))).toBe(true);
});

it('lets a human enable and cancel managed play while disabling manual dice', async () => {
  await join(game());
  const toggle = () => view.root.findByProps({className: 'auto-play-toggle'});
  expect(scene().dice.enabled).toBe(true);
  await act(async () => toggle().props.onClick());
  expect(connection.send).toHaveBeenLastCalledWith(expect.objectContaining({type: 'SET_AUTO_PLAY', enabled: true}));
  const managed = game();
  managed.players[0].autoPlay = true;
  await receive({type: 'STATE_UPDATED', roomId: 'TEST', revision: 2, game: managed, rollResults: [],
    events: [{type: 'AUTO_PLAY_CHANGED', playerId: 'human'}]});
  expect(toggle().props['aria-pressed']).toBe(true);
  expect(scene().dice.enabled).toBe(false);
  await act(async () => toggle().props.onClick());
  expect(connection.send).toHaveBeenLastCalledWith(expect.objectContaining({type: 'SET_AUTO_PLAY', enabled: false}));
  await receive({type: 'STATE_UPDATED', roomId: 'TEST', revision: 3, game: game(), rollResults: [], events: []});
  expect(toggle().props['aria-pressed']).toBe(false);
  expect(scene().dice.enabled).toBe(true);
});

it('does not offer managed play to spectators and keeps cancel available during a skill choice', async () => {
  await join(game(), true);
  expect(view.root.findAllByProps({className: 'auto-play-toggle'})).toHaveLength(0);
  act(() => view.unmount());
  const state = game({pendingDecision: {...decision, playerId: 'human'}, resolutionStatus: 'WAITING_FOR_DECISION'});
  state.players[0].autoPlay = true;
  await join(state);
  expect(view.root.findByProps({className: 'auto-play-toggle'}).props.disabled).toBe(false);
  expect(dialogs()[0].findByProps({className: 'decision-options'}).findAllByType('button').every(button => button.props.disabled)).toBe(true);
  expect(dialogs()[0].findByProps({className: 'command secondary decision-cancel-auto'}).props.disabled).toBe(false);
});

it.each([
  {abilityName: "GeniusPrediction", choiceType: "DIE" as const, options: [1, 2, 3, 4, 5, 6].map(value => ({id: String(value - 1), label: String(value)}))},
  {abilityName: "LongLegs", choiceType: "BOOLEAN" as const, options: [{id: "0", label: "skip"}, {id: "1", label: "use"}]},
  {abilityName: "EggCopy", choiceType: "RACER" as const, options: [{id: "0", label: "Coach", athlete: {id: "coach", name: "Coach"}}, {id: "1", label: "Genius", athlete: {id: "genius", name: "Genius"}}]},
  {abilityName: "FlipFlopSwap", choiceType: "RACER" as const, options: [{id: "0", label: "Coach"}, {id: "skip", label: "skip"}]},
])("shows candidates, highlights the managed $abilityName result, then moves", async example => {
  const choice: PendingDecision = {...decision, ...example, id: "managed-choice", playerId: "human"};
  const managed = game({pendingDecision: choice, resolutionStatus: "WAITING_FOR_DECISION"});
  managed.players[0].autoPlay = true;
  await join(managed);
  const candidates = () => dialogs()[0].findByProps({className: "decision-options"}).findAllByType("button");
  expect(candidates()).toHaveLength(example.options.length);
  expect(candidates().every(button => button.props.disabled)).toBe(true);
  expect(dialogs()[0].findAllByType("strong").some(node => node.children.includes("自动选择中"))).toBe(true);
  const next = game();
  next.players[0].autoPlay = true;
  next.players[0].activeRacers[0].position = 5;
  await receive({type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: next, rollResults: [], events: [
    {type: "DECISION_RESOLVED", decisionId: choice.id, playerId: "human", optionId: example.options[1].id, bot: true},
    {type: "RACER_MOVED", playerId: "human", athleteId: "banana", from: 0, to: 5},
  ]});
  await advance(649);
  expect(candidates().every(button => !button.props.className.includes("decision-chosen"))).toBe(true);
  await advance(1);
  expect(candidates()[1].props.className).toContain("decision-chosen");
  expect(dialogs()[0].findAllByType("small").some(node => node.children.join("").includes("自动选择了"))).toBe(true);
  expect(scene().players[0].activeRacers[0].position).toBe(0);
  await advance(1200);
  expect(dialogs()).toHaveLength(0);
  await advance(5000);
  expect(scene().players[0].activeRacers[0].position).toBe(5);
  expect(connection.send).not.toHaveBeenCalledWith(expect.objectContaining({type: "RESOLVE_DECISION"}));
});

it("can cancel managed play directly from the skill dialog and restore its manual choices", async () => {
  const choice: PendingDecision = {...decision, id: "managed-genius", playerId: "human", abilityName: "GeniusPrediction"};
  const managed = game({pendingDecision: choice, resolutionStatus: "WAITING_FOR_DECISION"});
  managed.players[0].autoPlay = true;
  await join(managed);
  await act(async () => dialogs()[0].findByProps({className: "command secondary decision-cancel-auto"}).props.onClick());
  expect(connection.send).toHaveBeenLastCalledWith(expect.objectContaining({type: "SET_AUTO_PLAY", enabled: false}));
  const manual = structuredClone(managed);
  manual.players[0].autoPlay = false;
  await receive({type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: manual, rollResults: [],
    events: [{type: "AUTO_PLAY_CHANGED", playerId: "human"}]});
  expect(dialogs()[0].findByProps({className: "decision-options"}).findAllByType("button").every(button => !button.props.disabled)).toBe(true);
  expect(dialogs()[0].findAllByProps({className: "command secondary decision-cancel-auto"})).toHaveLength(0);
});

it("shows copy candidate skills and the Twin's copied skill during the race", async () => {
  const twinDecision = { ...decision, athleteId: "twin", athleteName: "Twin", abilityName: "TwinCopy", choiceType: "RACER" as const,
    options: [{ id: "0", label: "Legs", athlete: { id: "legs", name: "Legs" } }] };
  await join(game({ pendingDecision: twinDecision, resolutionStatus: "WAITING_FOR_DECISION" }));
  expect(dialogs()[0].findByType(AthleteSkill).props.athlete.id).toBe("legs");
  expect(dialogs()[0].findAllByType("strong").some((node) => node.children.includes("慢跑"))).toBe(true);
  const racing = game();
  racing.players[0].activeRacers[0] = { ...racing.players[0].activeRacers[0], id: "twin", name: "Twin", copiedAthlete: { id: "legs", name: "Legs" } };
  await receive({ type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: racing, rollResults: [], events: [] });
  await advance(5000);
  expect(view.root.findByProps({ className: "copied-from" }).children.join("")).toContain("已复制：长腿");
});

it("updates standings alongside movement playback", async () => {
  await join(game());
  const moved = game();
  moved.players[1].activeRacers[0].position = 5;
  await receive({ type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: moved, rollResults: [], events: [
    { type: "RACER_MOVED", playerId: "bot", athleteId: "legs", from: 0, to: 5 },
  ] });
  await advance(300);
  const leaderboard = view.root.findByType(RaceLeaderboard);
  expect(leaderboard.props.players).toEqual(scene().players);
  await advance(5000);
  expect(view.root.findByType(RaceLeaderboard).props.players[1].activeRacers[0].position).toBe(5);
});

it("finishes landing movement before showing a Duelist choice", async () => {
  await join(game());
  const duel = { ...decision, id: 'duel', athleteId: 'duelist', athleteName: 'Duelist', abilityName: 'DuelistDuel' };
  const landed = game({ pendingDecision: duel, resolutionStatus: 'WAITING_FOR_DECISION' });
  landed.players[0].activeRacers[0].position = 3;
  await receive({ type: 'STATE_UPDATED', roomId: 'TEST', revision: 2, game: landed, rollResults: [], events: [
    { type: 'RACER_MOVED', playerId: 'human', athleteId: 'banana', from: 0, to: 3 },
    { type: 'DECISION_REQUIRED', decisionId: 'duel', abilityName: 'DuelistDuel' },
  ] });
  expect(dialogs()).toHaveLength(0);
  await advance(2000);
  expect(dialogs()).toHaveLength(0);
  await advance(3000);
  expect(scene().players[0].activeRacers[0].position).toBe(3);
  expect(dialogs()).toHaveLength(1);
  expect(dialogs()[0].findByProps({ id: 'decision-title' }).children.join('')).toContain('决斗');
});

it("highlights the same waiting dialog before movement, then closes it", async () => {
  await join(game({ pendingDecision: decision, resolutionStatus: "WAITING_FOR_DECISION" }));
  const original = dialogs()[0];
  await receive({ type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: game(), rollResults: [], events: [
    { type: "DECISION_RESOLVED", decisionId: "d1", playerId: "bot", optionId: "yes" },
    { type: "RACER_MOVED", playerId: "bot", athleteId: "legs", from: 0, to: 5 },
  ] });
  expect(dialogs()).toHaveLength(1);
  expect(dialogs()[0]).toBe(original);
  expect(original.findAllByType("button")[0].props.className).toContain("decision-chosen");
  expect(scene().players[1].activeRacers[0].position).toBe(0);
  await advance(1200);
  expect(dialogs()).toHaveLength(0);
});

it("does not reopen the choosing player's dialog after submission", async () => {
  await join(game({ pendingDecision: { ...decision, playerId: "human" }, resolutionStatus: "WAITING_FOR_DECISION" }));
  await act(async () => dialogs()[0].findAllByType("button")[0].props.onClick());
  expect(connection.send).toHaveBeenCalledWith(expect.objectContaining({ type: "RESOLVE_DECISION", optionId: "yes" }));
  expect(dialogs()).toHaveLength(0);
  await receive({ type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: game(), rollResults: [], events: [
    { type: "DECISION_RESOLVED", decisionId: "d1", playerId: "human", optionId: "yes" },
  ] });
  expect(dialogs()).toHaveLength(0);
  await advance(5000);
  expect(dialogs()).toHaveLength(0);
});

it("queues Bot starts and results behind human movement and focuses the actual second racer", async () => {
  await join(game());
  const botTurn = game({ activePlayerId: "bot", activeAthleteId: "coach" });
  await receive({ type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: botTurn, rollResults: [], events: [
    { type: "RACER_MOVED", playerId: "human", athleteId: "banana", from: 0, to: 3 },
  ] });
  await receive({ type: "ROLL_STARTED", roomId: "TEST", revision: 2, game: botTurn, actionId: "bot-roll", playerId: "bot" });
  expect(scene().dice.autoThrow).toBe(false);
  expect(scene().focus?.athleteId).toBe("banana");
  await receive({ type: "STATE_UPDATED", roomId: "TEST", revision: 3, game: game(), actionId: "bot-roll",
    rollResults: [{ id: "r1", values: [4] }], events: [] });
  expect(scene().dice.targetValue).toBeNull();
  expect(scene().focus?.athleteId).toBe("banana");
  await advance(5000);
  expect(scene().dice.targetValue).toBe(4);
  expect(scene().dice.autoThrow).toBe(true);
  expect(scene().focus).toEqual({ playerId: "bot", athleteId: "coach", close: true });
  expect(scene().turnKey).toBe("playback-3-0");
});

it("keeps a queued Bot throw automatic even while the local throw is settling", async () => {
  await join(game());
  await act(async () => scene().dice.onThrow("local-roll"));
  const botTurn = game({ activePlayerId: "bot", activeAthleteId: "legs" });
  await receive({ type: "STATE_UPDATED", roomId: "TEST", revision: 2, game: botTurn, actionId: "local-roll",
    rollResults: [{ id: "r1", values: [2] }], events: [] });
  expect(scene().dice.autoThrow).toBe(false);
  await receive({ type: "ROLL_STARTED", roomId: "TEST", revision: 2, game: botTurn, actionId: "bot-roll", playerId: "bot" });
  await receive({ type: "STATE_UPDATED", roomId: "TEST", revision: 3, game: game(), actionId: "bot-roll",
    rollResults: [{ id: "r2", values: [6] }], events: [] });
  expect(scene().dice.targetValue).toBe(2);
  await act(async () => scene().dice.onSettled());
  await advance(700);
  expect(scene().dice.restingValue).toBe(2);
  expect(scene().dice.targetValue).toBe(6);
  expect(scene().dice.autoThrow).toBe(true);
  expect(scene().focus?.athleteId).toBe("legs");
});
