import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { Group } from "three";
import type { PlayerState, PropThrow } from "../../protocol";
import { TauntEffects } from "./TauntEffects";
import { trackPose } from "./trackLayout";

const frames = vi.hoisted(() => [] as Array<(_state: unknown, delta: number) => void>);
vi.mock("@react-three/fiber", () => ({useFrame: (frame: typeof frames[number]) => frames.push(frame)}));
const players = [{id: "a", activeRacers: [{id: "banana", position: 7}]},
  {id: "b", activeRacers: [{id: "genius", position: 8}]}] as unknown as PlayerState[];
const event: PropThrow = {type: "PROP_THROWN", id: "hit", actorId: "a", actorName: "A", targetPlayerId: "b", targetName: "B", item: "egg", cooldownMs: 4000};
let view: ReactTestRenderer;
const nodes = new Map<string, Group>();
afterEach(() => { act(() => view.unmount()); frames.length = 0; nodes.clear(); });
function mount(reducedMotion = false, participants = players) {
  const hit = vi.fn();
  act(() => { view = create(<TauntEffects events={[event]} players={participants} finishLine={30} reducedMotion={reducedMotion} onImpact={hit} />, {
    createNodeMock: node => { const group = new Group(); if (node.props.name) nodes.set(node.props.name, group); return group; },
  }); });
  return hit;
}
const tick = (delta: number) => act(() => frames.forEach(frame => frame({}, delta)));

it("replaces the flying prop with the impact and reports one collision", () => {
  const hit = mount();
  tick(.849);
  expect(nodes.get("prop-flight-egg")?.visible).toBe(true);
  expect(nodes.get("prop-impact-egg")?.visible).toBe(false);
  expect(hit).not.toHaveBeenCalled();
  tick(.002);
  expect(nodes.get("prop-flight-egg")?.visible).toBe(false);
  expect(nodes.get("prop-impact-egg")?.visible).toBe(true);
  expect(hit).toHaveBeenCalledTimes(1);
  tick(.1); tick(.1);
  expect(hit).toHaveBeenCalledTimes(1);
  tick(1.2);
  expect(nodes.get("prop-impact-egg")?.visible).toBe(false);
});

it("reduced motion shows the impact immediately and still cues it once", () => {
  const hit = mount(true);
  tick(.016);
  expect(nodes.get("prop-flight-egg")?.visible).toBe(false);
  expect(nodes.get("prop-impact-egg")?.visible).toBe(true);
  tick(.1);
  expect(hit).toHaveBeenCalledTimes(1);
});

it("does not replay an expired impact when a hidden tab resumes", () => {
  const hit = mount();
  tick(4);
  expect(nodes.get("prop-flight-egg")?.visible).toBe(false);
  expect(nodes.get("prop-impact-egg")?.visible).toBe(false);
  expect(hit).not.toHaveBeenCalled();
});

it("aims at the lowered piece when the recipient is tripped", () => {
  const participants = structuredClone(players);
  participants[1].activeRacers[0].tripped = true;
  mount(false, participants);
  tick(.851);
  expect(nodes.get("prop-flight-egg")?.position.y).toBeCloseTo(.41);
  expect(nodes.get("prop-flight-egg")?.position.z).toBeCloseTo(trackPose(8).position.z - .45);
});

it("targets the player's active piece instead of its already finished racer", () => {
  const participants = structuredClone(players);
  participants[1].activeRacers[0].finished = true;
  participants[1].activeRacers.push({...participants[1].activeRacers[0], id: "coach", position: 10, finished: false});
  mount(false, participants);
  tick(.851);
  expect(nodes.get("prop-flight-egg")?.position.x).toBeCloseTo(trackPose(10).position.x);
});
