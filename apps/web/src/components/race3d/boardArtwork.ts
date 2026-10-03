import i18n from "../../i18n";
import { festivalArtEnabled } from "../../artPack";
import { assetUrl } from "../../runtimeConfig";
import atlas from "./boardAtlas.json";
import festivalAtlas from "./festivalBoardAtlas.json";
import { drawFestivalSpecialTile } from "./festivalBoardIllustrations";
import { FINISH_BADGE_RECT, REFERENCE_BOARD, referenceRectForStep } from "./trackLayout";

export type TrackName = "Standard" | "WildWilds";
const INK = "#1d1e21";
const PAPER = "#f1f0e9";
const TILE = {
  pink: "#da68bb", yellow: "#fab51a", green: "#47a439",
  blue: "#659bd8", red: "#ef391f",
} as const;
const MILD_COLORS = [TILE.pink, "#fab61a", "#48a439", "#669cd9", TILE.red];
const WILD_LABEL_KEYS: Record<number, string | null> = {
  5: "board.trip", 17: "board.trip", 26: "board.trip",
};
const WILD_SYMBOLS: Record<number, string> = {
  1: "★ 1", 7: "+3", 11: "+1", 13: "★ 1", 16: "−4", 23: "+2", 24: "−2",
};
const MOVE_AMOUNTS: Record<number, number> = { 7: 3, 11: 1, 16: -4, 23: 2, 24: -2 };
const ARROW_COLORS: Record<number, string> = { 7: "#559944", 11: "#4d86c7", 16: "#428748", 23: "#5d93cc", 24: "#e64b35" };
const DIGIT_COLORS: Record<number, string> = { 7: "#f6d546", 11: "#c983bc", 16: "#d7a5ce", 23: "#62a15a", 24: "#80a5d8" };

function drawMoveArrow(context: CanvasRenderingContext2D, step: number, x: number, y: number, w: number, h: number) {
  const amount = MOVE_AMOUNTS[step];
  // Forward runs right on the top row and left on the bottom row.
  const direction = Math.sign(amount) * (step < 15 ? 1 : -1);
  const point = (px: number, py: number) => [x + (direction > 0 ? px : 1 - px) * w, y + py * h] as const;
  const outline = [[.06,.12],[.57,.12],[.57,.03],[.96,.5],[.57,.97],[.57,.88],[.06,.88]];
  context.save();
  context.beginPath();
  outline.forEach(([px, py], i) => { const p = point(px,py); if (i) context.lineTo(...p); else context.moveTo(...p); });
  context.closePath(); context.fillStyle = ARROW_COLORS[step]; context.strokeStyle = INK; context.lineWidth = 2.5; context.lineJoin = "round"; context.fill(); context.stroke();
  context.strokeStyle = "#fff5b550"; context.lineWidth = 1;
  for (const row of [.2, .24, .76, .8]) {
    context.beginPath(); context.moveTo(...point(.1,row)); context.lineTo(...point(.3,row)); context.stroke();
  }
  const center = point(.43,.53);
  context.textAlign = "center"; context.textBaseline = "middle";
  context.font = `900 ${Math.min(w * .5, h * .55)}px "Arial Black", sans-serif`;
  context.fillStyle = DIGIT_COLORS[step]; context.strokeStyle = INK; context.lineWidth = 2.5;
  context.strokeText(String(Math.abs(amount)), ...center); context.fillText(String(Math.abs(amount)), ...center);
  context.restore();
}

/** Canvas-filled labels follow the UI language, so the fallback board stays readable. */
function wildLabel(step: number): string {
  const key = WILD_LABEL_KEYS[step];
  return key ? i18n.t(key) : WILD_SYMBOLS[step] ?? "";
}
let atlasPromise: Promise<HTMLImageElement> | undefined;

export function loadBoardAtlas(): Promise<HTMLImageElement> {
  if (!atlasPromise) {
    const load = (festival: boolean) => new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new Image();
      image.dataset.boardAtlas = festival ? "festival" : "classic";
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("Board illustration could not be loaded"));
      image.src = assetUrl(festival ? "assets/art-pack/festival-print-atlas.png" : "assets/boards/print-atlas.webp");
    });
    atlasPromise = load(festivalArtEnabled).catch((error: unknown) => {
      if (festivalArtEnabled) return load(false);
      throw error;
    }).catch((error: unknown) => {
      atlasPromise = undefined;
      throw error;
    });
  }
  return atlasPromise;
}

function rounded(context: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  context.beginPath();
  context.roundRect(x, y, w, h, r);
}

export function drawBoardArtwork(context: CanvasRenderingContext2D, track: TrackName, image?: HTMLImageElement) {
  const { width, height } = REFERENCE_BOARD;
  const wild = track === "WildWilds";
  const stamp = (name: keyof typeof atlas, x: number, y: number, w: number, h: number) => {
    if (!image) return;
    const regions = image.dataset.boardAtlas === "festival" ? festivalAtlas : atlas;
    const region = (regions as Record<string, number[]>)[name];
    if (!region) return;
    const [sx, sy, sw, sh] = region;
    context.drawImage(image, sx, sy, sw, sh, x, y, w, h);
  };
  context.clearRect(0, 0, width, height);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = festivalArtEnabled ? "high" : "low";
  const rim = context.createLinearGradient(0, 0, 0, height);
  rim.addColorStop(0, "#46474a"); rim.addColorStop(.18, "#27282b"); rim.addColorStop(1, "#191a1d");
  context.fillStyle = festivalArtEnabled ? rim : INK;
  rounded(context, 0, 0, width, height, 47);
  context.fill();

  context.save();
  rounded(context, 20, 20, 1160, 320, 36);
  context.clip();
  for (let step = 0; step < 30; step += 1) {
    const { x, y, width: w, height: h } = referenceRectForStep(step);
    context.fillStyle = step === 0 ? MILD_COLORS[3] : MILD_COLORS[(step - 1) % MILD_COLORS.length];
    context.fillRect(x, y, w, h);
    context.strokeStyle = INK;
    context.lineWidth = 3;
    context.strokeRect(x, y, w, h);
    if (wild && festivalArtEnabled && drawFestivalSpecialTile(context, step, x + 3, y + 3, w - 6, h - 6)) {
      // Original-inspired stars, shoes, impact marks, and rope, rendered as paths.
    } else if (wild && image && `tile-${step}` in atlas && !festivalArtEnabled) {
      stamp(`tile-${step}` as keyof typeof atlas, x + 3, y + 3, w - 6, h - 6);
    } else if (wild && festivalArtEnabled && MOVE_AMOUNTS[step]) {
      drawMoveArrow(context, step, x + 4, y + 4, w - 8, h - 8);
    } else if (wild && wildLabel(step)) {
      // These marks were tiny crops from a perspective photo. Render the
      // same rule labels at native texture resolution, including localization.
      context.font = "900 23px sans-serif";
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillStyle = PAPER;
      context.strokeStyle = INK;
      context.lineWidth = 3;
      context.lineJoin = "round";
      context.strokeText(wildLabel(step), x + w / 2, y + h / 2, w - 10);
      context.fillText(wildLabel(step), x + w / 2, y + h / 2, w - 10);
    } else if (!wild && step > 0 && step % 5 === 0) {
      if (image && !festivalArtEnabled) {
        const name = `number-${step}` as keyof typeof atlas;
        const [, , sw, sh] = atlas[name];
        stamp(name, x + (w - sw * .46) / 2, y + (h - sh * .46) / 2, sw * .46, sh * .46);
        continue;
      }
      context.font = "900 32px sans-serif";
      context.fillStyle = festivalArtEnabled ? ["#81a8df", "#cf93c6", "#f7d746", "#67a15b", "#81a8df"][step / 5 - 1] : PAPER;
      context.strokeStyle = INK;
      context.lineWidth = 2;
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.strokeText(String(step), x + w / 2, y + h / 2);
      context.fillText(String(step), x + w / 2, y + h / 2);
    }
  }
  context.restore();
  context.textBaseline = "alphabetic";

  // White printed keylines, with black gutters just like the physical board.
  context.strokeStyle = PAPER;
  context.lineWidth = 3;
  rounded(context, 17, 17, 1166, 326, festivalArtEnabled ? 30 : 40);
  context.stroke();
  if (festivalArtEnabled) {
    context.strokeStyle = "#f1eee3";
    rounded(context, 110, 103, 990, 154, 15);
    context.stroke();
    context.beginPath();
    context.moveTo(252, 20); context.lineTo(252, 93);
    context.quadraticCurveTo(252, 103, 242, 103); context.lineTo(20, 103);
    context.stroke();
    context.strokeStyle = "#fff9e325"; context.lineWidth = 1.2;
    rounded(context, 4, 4, 1192, 352, 43); context.stroke();
    context.strokeStyle = "#08090b55"; context.lineWidth = 1;
    rounded(context, 10, 10, 1180, 340, 37); context.stroke();
  } else {
    context.beginPath();
    context.moveTo(252, 18);
    context.lineTo(252, 102);
    context.lineTo(20, 102);
    context.moveTo(252, 102);
    context.lineTo(1101, 102);
    context.lineTo(1101, 258);
    context.lineTo(20, 258);
    context.stroke();
  }

  stamp(wild ? "wild" : "mild", 116, 109, 980, 140);
  stamp("start", 76, 38, 122, 40);
  const finish = FINISH_BADGE_RECT;
  stamp("podium", finish.x, finish.y, finish.width, finish.height);
  if (!image) {
    context.fillStyle = PAPER;
    context.textAlign = "center";
    context.font = "900 65px Impact, sans-serif";
    context.fillText(wild ? "WILD WILDS" : "MILD MILE", 608, 205);
    context.font = "900 28px sans-serif";
    context.fillText(i18n.t("board.start"), 136, 70);
    context.fillText("1 / 2", 67, 190);
  }

  // The physical folding seam is subtle and never covers a tile label.
  context.fillStyle = "rgba(0,0,0,.13)";
  context.fillRect(599.5, 2, 1, 356);
  context.fillStyle = "rgba(255,255,255,.07)";
  context.fillRect(600.5, 2, .65, 356);
}

export function createBoardCanvas(track: TrackName, scale = festivalArtEnabled ? 3 : 2): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = Math.floor(REFERENCE_BOARD.width * scale);
  canvas.height = Math.floor(REFERENCE_BOARD.height * scale);
  const context = canvas.getContext("2d");
  if (context) {
    context.scale(scale, scale);
    drawBoardArtwork(context, track);
  }
  return canvas;
}
