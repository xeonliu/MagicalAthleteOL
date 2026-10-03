# Festival art pack

The pack adds an illustrated festival backdrop, warmer card frames, restored board-center scenery, and sharp original-inspired tile illustrations. The 36 racer portraits, game rules, board coordinates, and colors identifying players remain unchanged.

## Developer opt-in

Classic artwork is the default, even after this PR is merged. Set `VITE_ART_PACK=festival` before starting Vite or making a production build to enable the pack. Omit it or set it to `classic` to retain the original textures, backgrounds, and renderer settings. Restart/rebuild after changing it. The mobile announcement and playful-prop PRs do not depend on this flag or this PR.

## Assets

- `apps/web/public/assets/art-pack/festival-background.webp`: 1672 × 941, approximately 511 KiB. Generated with the built-in imagegen tool for this project, then encoded as WebP without changing dimensions. Decorative scenery contains no playable track or rules. The same asset is used by the entry page, card screens, and 3D tabletop.
- Existing racer portraits and transparent tokens are retained at 235 × 235. Card text, frames, and ornamentation render at screen resolution; this pack does not claim to recover detail absent from the original portraits.
- `apps/web/public/assets/art-pack/festival-print-atlas.png`: 1774 × 887 RGBA, approximately 1615 KiB. Restored with the built-in imagegen tool from the original board atlas, then copied as a lossless PNG. Center titles, flowers, forest scenery, start mark, and podium keep the original board's cartoon style. This is an illustrated restoration, not a claim that the source photographs contain higher-resolution detail.
- Scoring stars and three distinct trip illustrations render as native canvas paths: nested stars, striped trousers, shoes, impact marks, and a curved rope. Trip labels remain localized text. Directional arrows and Mild Mile numbers also render at texture resolution, using the original palette and correct direction along each board row.
- The original `print-atlas.webp` remains the classic board texture and serves as a fallback if the optional restored atlas cannot load. The optional background and atlas are never requested with the pack disabled.

## Rendering

With the pack enabled, the board canvas uses up to 3× reference resolution (3600 × 1080), reduced to fit the GPU's maximum texture dimension. The scene renders at device pixel ratio up to 2 and uses anisotropic filtering up to the supported limit, capped at 16. These caps bound memory and fill-rate costs on phones. Rounded print outlines follow the board corners; a smoother bevel, restrained clearcoat, and a procedurally drawn paper-layer edge give the board thickness without moving its playing surface or physics collider. The board texture, paper-edge texture, and geometry are disposed when replaced or unmounted. Classic materials and renderer settings remain unchanged when disabled.

No backend or game-rule changes are required. `art-pack.css` is loaded after the layout styles and is scoped to `html.festival-art`; generated scenery is a background, leaving rules and interactive UI as real text. A flat base color remains available while the scenery loads.

## Updating the pack

Replace the decorative WebP and update this document's dimensions and byte size. Preserve asset paths so both the Vite build and Three.js loader work under `/MagicalAthleteOL/`. Update `festivalBoardAtlas.json` if restored atlas coordinates change. Do not bake localized card text, tile numbers, or rules into the background image.

The restored atlas was generated with `image_gen.imagegen` using the original board atlas as its reference and this brief: restore the original cartoon board-center titles and scenery with clean ink outlines and flat original colors; retain the atlas layout, start mark, and podium; use a transparent background; do not regenerate racer portraits. Stars, trip spaces, and numbered arrows are drawn in code instead of sampling the generated tile pictures.
