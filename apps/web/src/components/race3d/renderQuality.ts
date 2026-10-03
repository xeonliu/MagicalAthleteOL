import { REFERENCE_BOARD } from "./trackLayout";

/** Keep the print texture sharp without exceeding the device's GPU limit. */
export function boardTextureScale(maxTextureSize: number): number {
  return Math.min(3, Math.max(1, maxTextureSize) / REFERENCE_BOARD.width);
}

/** Retina clarity without an unbounded pixel cost on high-density phones. */
export function racePixelRatio(devicePixelRatio: number): number {
  return Math.min(2, Math.max(1, devicePixelRatio));
}
