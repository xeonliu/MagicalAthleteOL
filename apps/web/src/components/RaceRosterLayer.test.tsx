import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { createPortal } from "react-dom";
import { RaceRosterLayer } from "./RaceRosterLayer";

vi.mock("react-dom", () => ({ createPortal: vi.fn(node => node) }));
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });
it("opens at the document root and supports Escape and outside-click dismissal", () => {
  const addEventListener = vi.fn(), removeEventListener = vi.fn(), onClose = vi.fn();
  const body = {};
  vi.stubGlobal("HTMLElement", class {});
  vi.stubGlobal("document", { body, activeElement: null, addEventListener, removeEventListener });
  let view: ReturnType<typeof create>;
  act(() => { view = create(<RaceRosterLayer open onClose={onClose}><p>Skills</p></RaceRosterLayer>); });
  expect(vi.mocked(createPortal).mock.calls[0][1]).toBe(body);
  expect(view!.root.findByProps({role: "dialog"}).findByType("p").children).toEqual(["Skills"]);
  const keydown = addEventListener.mock.calls.find(([name]) => name === "keydown")![1];
  act(() => keydown({key: "Escape"}));
  expect(onClose).toHaveBeenCalledTimes(1);
  const backdrop = view!.root.findByProps({className: "race-roster-layer"});
  act(() => backdrop.props.onClick({target: body, currentTarget: body}));
  expect(onClose).toHaveBeenCalledTimes(2);
  act(() => backdrop.props.onClick({target: {}, currentTarget: body}));
  expect(onClose).toHaveBeenCalledTimes(2);
  act(() => view!.unmount());
  expect(removeEventListener).toHaveBeenCalledWith("keydown", keydown);
});
