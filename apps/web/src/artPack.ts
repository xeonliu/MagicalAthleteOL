/** A developer opt-in: classic artwork stays the default. */
export const festivalArtEnabled = import.meta.env.VITE_ART_PACK === "festival";

export function applyArtPack(): void {
  document.documentElement.classList.toggle("festival-art", festivalArtEnabled);
}
