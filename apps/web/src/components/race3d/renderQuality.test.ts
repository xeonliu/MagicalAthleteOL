import { describe, expect, it } from "vitest";
import { boardTextureScale, racePixelRatio } from "./renderQuality";
import { REFERENCE_BOARD } from "./trackLayout";

describe("race artwork resolution", () => {
  it.each([512, 1024, 2048, 4096, 16384])("fits a %i-pixel GPU texture limit", (limit) => {
    const scale = boardTextureScale(limit);
    expect(REFERENCE_BOARD.width * scale).toBeLessThanOrEqual(limit);
    expect(REFERENCE_BOARD.height * scale).toBeLessThanOrEqual(limit);
    expect(scale).toBeLessThanOrEqual(3);
  });
  it("uses full retina resolution but caps the pixel cost on dense phones", () => {
    expect(racePixelRatio(2)).toBe(2);
    expect(racePixelRatio(3.5)).toBe(2);
    expect(racePixelRatio(.75)).toBe(1);
  });
});
