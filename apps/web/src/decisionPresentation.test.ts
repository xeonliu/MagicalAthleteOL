import { expect, it } from "vitest";
import { decisionOptionLabel, decisionPrompt, decisionResolution, decisionTitle, resolvedDecisionDialog } from "./decisionPresentation";
import type { PendingDecision } from "./protocol";

it("localizes copied skill choices without changing numeric choices", () => {
  const decision = { abilityName: "TwinCopy", athleteName: "双胞胎", choiceType: "RACER" } as PendingDecision;
  expect(decisionTitle(decision)).toBe("双倍下注");
  expect(decisionPrompt(decision)).toBe("选择本次复制的角色能力");
  expect(decisionOptionLabel("Legs")).toBe("长腿");
  expect(decisionOptionLabel("6")).toBe("6");
});

it("distinguishes predicting a future roll, selecting a rolled die and jogging", () => {
  const prediction = { abilityName: "GeniusPrediction", choiceType: "DIE" } as PendingDecision;
  const selection = { abilityName: "OtherDieChoice", choiceType: "DIE" } as PendingDecision;
  const jog = { abilityName: "LongLegs", choiceType: "BOOLEAN", athleteName: "Legs" } as PendingDecision;
  expect(decisionPrompt(prediction)).toContain("预测");
  expect(decisionPrompt(selection)).toBe("选择本次使用的骰点");
  // Legs skips the die entirely instead of picking one.
  expect(decisionPrompt(jog)).toContain("移动 5 格");
});

it("explains the swap cost and optional decline", () => {
  const decision = { abilityName: "FlipFlopSwap", choiceType: "RACER" } as PendingDecision;
  expect(decisionPrompt(decision)).toContain("跳过本回合的正常移动");
  expect(decisionPrompt(decision)).toContain("不使用");
});

it("shows who the suckerfish will follow and its destination before movement commits", () => {
  const decision = { abilityName: "SuckerfishRide", choiceType: "BOOLEAN",
    effectPreview: { athleteName: "教练", from: 8, to: 3 } } as PendingDecision;
  expect(decisionPrompt(decision)).toBe("是否跟随教练，从第 8 格移动到第 3 格？");
});

it("reports the picked option for the existing waiting dialog", () => {
  const decision = { id: "d1", playerId: "p1", abilityName: "FlipFlopSwap" } as PendingDecision;
  expect(decisionResolution(decision, [
    { type: "DECISION_RESOLVED", decisionId: "d1", playerId: "p2", optionId: "2", automatic: false },
  ])).toEqual({ optionId: "2", automatic: false, playerId: "p2" });
  expect(decisionResolution(decision, [
    { type: "DECISION_TIMED_OUT", decisionId: "d1", playerId: "p1", optionId: "", automatic: true },
  ])).toEqual({ optionId: null, automatic: true, playerId: "p1" });
});

it("highlights the waiting dialog only for observers without reopening a closed choice", () => {
  const decision = { id: "d1", playerId: "p1" } as PendingDecision;
  const current = { decision, outcome: null };
  const events = [{ type: "DECISION_RESOLVED", decisionId: "d1", optionId: "2" }];
  expect(resolvedDecisionDialog(current, events, "p2")).toEqual({
    decision, outcome: { optionId: "2", playerId: "p1", automatic: false },
  });
  expect(resolvedDecisionDialog(current, events, "p1")).toBeNull();
  expect(resolvedDecisionDialog(null, events, "p2")).toBeNull();
  expect(resolvedDecisionDialog(current, [{ ...events[0], decisionId: "d2" }], "p2")).toBeNull();
});

it("ignores resolutions of another decision or an unrelated event", () => {
  const decision = { id: "d1", playerId: "p1", abilityName: "FlipFlopSwap" } as PendingDecision;
  expect(decisionResolution(decision, [{ type: "DECISION_RESOLVED", decisionId: "d2", optionId: "1" }])).toBeNull();
  expect(decisionResolution(decision, [{ type: "DIE_ROLLED", value: 3 }])).toBeNull();
  expect(decisionResolution(null, [{ type: "DECISION_RESOLVED", decisionId: "d1", optionId: "1" }])).toBeNull();
});

it("replays managed choices and timeouts for the deciding player", () => {
  const decision = {id: "d1", playerId: "p1"} as PendingDecision;
  const current = {decision, outcome: null};
  expect(resolvedDecisionDialog(current, [{type: "DECISION_RESOLVED", decisionId: "d1", optionId: "2", bot: true}], "p1"))
    .toEqual({decision, outcome: {optionId: "2", playerId: "p1", automatic: false, managed: true}});
  expect(resolvedDecisionDialog(current, [{type: "DECISION_TIMED_OUT", decisionId: "d1", optionId: "1"}], "p1"))
    .toEqual({decision, outcome: {optionId: "1", playerId: "p1", automatic: true}});
});
