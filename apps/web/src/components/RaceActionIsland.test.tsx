import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { RaceActionIsland } from "./RaceActionIsland";
import { ActionMoment } from "./ActionMoment";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
it("keeps the shell and event content during collapse, then restores the roll control", () => {
  vi.useFakeTimers();
  vi.stubGlobal("window", { setTimeout, clearTimeout });
  const moment = { source: { name: "Dice", owner: "" }, target: { name: "Runner", owner: "" }, cause: "Roll", effect: "+3" };
  const render = (active: boolean) => <RaceActionIsland moment={active ? moment : null} busy={false} status="Ready"><button>Roll</button></RaceActionIsland>;
  let view: ReturnType<typeof create>;
  act(() => { view = create(render(false)); });
  const shell = view!.root.findByProps({ className: "table-dice-hud race-action-island" });
  act(() => view!.update(render(true)));
  expect(view!.root.findAllByType("button")).toHaveLength(0);
  expect(view!.root.findByType(ActionMoment).props.moment).toBe(moment);
  act(() => view!.update(render(false)));
  expect(view!.root.findByProps({ className: "table-dice-hud race-action-island" })).toBe(shell);
  expect(view!.root.findAllByType(ActionMoment)).toHaveLength(1);
  expect(view!.root.findAllByType("button")).toHaveLength(1);
  act(() => { vi.advanceTimersByTime(600); });
  expect(view!.root.findAllByType(ActionMoment)).toHaveLength(0);
  act(() => view!.unmount());
});
