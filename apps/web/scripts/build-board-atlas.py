"""Extract printed illustrations, not table/pawns, from the checked-in references.

Run with Python 3 + Pillow + NumPy. The runtime rebuilds the grid and borders
from trackLayout.ts; this atlas contains only the original printed artwork.
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "apps/web/public/assets/boards"
OUTPUT.mkdir(parents=True, exist_ok=True)
photos = {name: Image.open(ROOT / f"docs/{name}.png").convert("RGB")
          for name in ("mildmile", "wildwilds")}
mild_left = Image.open(ROOT / "docs/mildmile-print-left.png").convert("RGB")
mild_right = Image.open(ROOT / "docs/mildmile-print-right.png").convert("RGB")
wild_print = Image.open(ROOT / "docs/wildwilds-print-board.png").convert("RGB")
atlas = Image.new("RGBA", (2048, 1024))
regions = {}


def extract(name, source, quad, destination, size, clean_black=False, transparent_blue=False,
            transparent_red=False):
    # Pillow QUAD order: top left, bottom left, bottom right, top right.
    patch = photos[source].transform(size, Image.Transform.QUAD, quad,
                                     Image.Resampling.BICUBIC).convert("RGBA")
    pixels = np.array(patch)
    if clean_black:
        dark = pixels[:, :, :3].max(axis=2) < 67
        pixels[dark, :3] = [29, 30, 33]
    if transparent_blue:
        blue = pixels[:, :, 2].astype(float) > pixels[:, :, 0] * 1.12
        pixels[blue, 3] = 0
    if transparent_red:
        red = ((pixels[:, :, 0].astype(float) > pixels[:, :, 1] * 1.4)
               & (pixels[:, :, 0].astype(float) > pixels[:, :, 2] * 1.6))
        pixels[red, 3] = 0
    atlas.paste(Image.fromarray(pixels), destination)
    regions[name] = [*destination, *size]


def crop_print(name, image, box, destination, transparent_red=False):
    patch = image.crop(box).convert("RGBA")
    pixels = np.array(patch)
    if transparent_red:
        red = ((pixels[:, :, 0].astype(float) > pixels[:, :, 1] * 1.4)
               & (pixels[:, :, 0].astype(float) > pixels[:, :, 2] * 1.6))
        pixels[red, 3] = 0
    atlas.paste(Image.fromarray(pixels), destination)
    regions[name] = [*destination, patch.width, patch.height]


mild_left_art = mild_left.crop((300, 345, 1868, 680))
mild_right_art = mild_right.crop((0, 345, 960, 680))
mild_art = Image.new("RGB", (mild_left_art.width + mild_right_art.width, mild_left_art.height))
mild_art.paste(mild_left_art, (0, 0))
mild_art.paste(mild_right_art, (mild_left_art.width, 0))
mild_art = mild_art.resize((1960, 280), Image.Resampling.LANCZOS).convert("RGBA")
atlas.paste(mild_art, (0, 0))
regions["mild"] = [0, 0, 1960, 280]

wild_art = wild_print.crop((165, 190, 1632, 378)).resize(
    (1960, 280), Image.Resampling.LANCZOS).convert("RGBA")
atlas.paste(wild_art, (0, 288))
regions["wild"] = [0, 288, 1960, 280]

podium = mild_left.crop((70, 350, 300, 680)).resize((164, 232), Image.Resampling.LANCZOS)
atlas.paste(podium.convert("RGBA"), (0, 580))
regions["podium"] = [0, 580, 164, 232]

start = mild_left.crop((176, 105, 610, 250)).resize((268, 88), Image.Resampling.LANCZOS)
atlas.paste(start.convert("RGBA"), (170, 580))
regions["start"] = [170, 580, 268, 88]

# Source rectangles include each printed tile's full border and lettering.
special = {
    1: (383, 40, 500, 159),
    5: (846, 40, 956, 159),
    7: (1073, 40, 1182, 159),
    11: (1531, 40, 1640, 159),
    13: (1644, 162, 1755, 280),
    16: (1531, 394, 1640, 509),
    17: (1302, 394, 1413, 509),
    23: (731, 394, 840, 509),
    24: (618, 394, 727, 509),
    26: (390, 394, 500, 509),
}
for index, (step, bounds) in enumerate(special.items()):
    tile = wild_print.crop(bounds).resize((144, 144), Image.Resampling.LANCZOS)
    destination = (460 + index * 150, 580)
    atlas.paste(tile.convert("RGBA"), destination)
    regions[f"tile-{step}"] = [*destination, 144, 144]

number_crops = {
    5: (mild_left, (1555, 124, 1638, 230)),
    10: (mild_right, (688, 124, 816, 230)),
    15: (mild_right, (1092, 744, 1222, 852)),
    20: (mild_right, (75, 744, 212, 852)),
    25: (mild_left, (924, 742, 1064, 852)),
}
for index, (step, (source, bounds)) in enumerate(number_crops.items()):
    crop_print(f"number-{step}", source, bounds, (460 + index * 150, 750), transparent_red=True)

atlas.save(OUTPUT / "print-atlas.webp", quality=94, method=6)
(ROOT / "apps/web/src/components/race3d/boardAtlas.json").write_text(
    json.dumps(regions, indent=2) + "\n")
print(f"Generated {OUTPUT / 'print-atlas.webp'}")
