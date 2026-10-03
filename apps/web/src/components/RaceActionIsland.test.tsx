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

it("prioritizes interactive decisions over playback and retains their descriptions", () => {
  vi.useFakeTimers();
  vi.stubGlobal("window", { setTimeout, clearTimeout });
  const choose = vi.fn();
  const moment = { source: { name: "Dice", owner: "" }, target: { name: "Runner", owner: "" }, cause: "Roll", effect: "+3" };
  const decision = <section role="dialog"><p>Choose how far to move.</p><button onClick={choose}>Move three spaces</button></section>;
  let view: ReturnType<typeof create>;
  act(() => { view = create(<RaceActionIsland moment={moment} busy status="Playing" decision={decision}><button>Roll</button></RaceActionIsland>); });
  expect(view!.root.findAllByType(ActionMoment)).toHaveLength(0);
  expect(view!.root.findByType("p").children).toEqual(["Choose how far to move."]);
  act(() => view!.root.findByType("button").props.onClick());
  expect(choose).toHaveBeenCalledOnce();
  act(() => view!.update(<RaceActionIsland moment={moment} busy status="Playing"><button>Roll</button></RaceActionIsland>));
  expect(view!.root.findAllByProps({ role: "dialog" })).toHaveLength(0);
  expect(view!.root.findByType(ActionMoment).props.moment).toBe(moment);
  act(() => view!.unmount());
});

it("caps the desktop island inside the button gap as the stage shrinks", () => {
  vi.useFakeTimers();
  vi.stubGlobal("window", { setTimeout, clearTimeout, addEventListener: vi.fn(), removeEventListener: vi.fn() });
  let remeasure = () => {};
  const disconnect = vi.fn();
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: () => void) { remeasure = callback; }
    observe() {}
    disconnect = disconnect;
  });
  let rightEdge = 1000;
  const leftButton = { getBoundingClientRect: () => ({ right: 220 }) };
  const rightButtons = { getBoundingClientRect: () => ({ left: rightEdge }) };
  const stage = { getBoundingClientRect: () => ({ left: 0, width: 1200 }), querySelector: (selector: string) => selector === ".race-details-toggle" ? leftButton : rightButtons };
  const properties = new Map<string, string>();
  const shell = { closest: () => stage, style: { setProperty: (name: string, value: string) => properties.set(name, value) } };
  let view: ReturnType<typeof create>;
  act(() => { view = create(<RaceActionIsland busy={false} status="Ready"><button>Roll</button></RaceActionIsland>, {
    createNodeMock: element => element.props.className?.includes("table-dice-hud") ? shell : null,
  }); });
  const assertClearance = () => {
    const width = parseFloat(properties.get("--island-available-width")!);
    const center = parseFloat(properties.get("--island-center")!);
    expect(center - width / 2).toBeGreaterThanOrEqual(236);
    expect(center + width / 2).toBeLessThanOrEqual(rightEdge - 16);
  };
  assertClearance();
  rightEdge = 680;
  act(() => remeasure());
  assertClearance();
  act(() => view!.unmount());
  expect(disconnect).toHaveBeenCalledOnce();
});
