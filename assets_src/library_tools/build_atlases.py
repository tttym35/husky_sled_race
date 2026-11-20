#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pack assets_src/library into engine atlas sources plus a C layout header.

Engine packer rules this relies on (tools/pack_game_assets.py):
  * every frame is one square grid cell;
  * non-opaque cells are thumbnailed to (output_cell - 4) and centred, so a
    source cell of exactly output_cell - 4 is copied 1:1 at offset (2, 2).
So each sprite is placed in a (C - 4) source cell and the header records where
its pixels land inside the packed C cell. Outputs are committed: the IDF Python
that runs asset hooks has no Pillow, so this is a developer-host script.
"""

import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ASSETS_SRC = HERE.parent
LIB = ASSETS_SRC / "library"
HEADER = ASSETS_SRC.parent / "components/app_game_runtime/private/husky_art.h"
META = {a["name"]: a for a in json.loads((LIB / "asset_library.json").read_text())["assets"]}


def load(name):
    im = Image.open(LIB / META[name]["file"]).convert("RGBA")
    if name.startswith("treeline_"):
        # The crop's top edge cuts through the canopy; fade it so mid-distance
        # billboards do not show a flat line against the sky.
        a = im.getchannel("A")
        px = a.load()
        ramp = im.height // 4
        for y in range(ramp):
            for x in range(im.width):
                px[x, y] = px[x, y] * y // ramp
        im.putalpha(a)
    return dither(im) if name in DITHERED else im


rects = []  # (frame name, x, y, w, h) inside the packed cell

# Pinned engine blend565() leaks red-channel bits into blue for 8-bit alpha, so
# translucent pixels show blue/yellow noise. Ship binary alpha only (no blend,
# also faster on device) and turn soft glows into ordered-dither stipple.
BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
DITHERED = {
    "lamp_glow",
    "light_pool",
    "shadow_soft",
    "snow_puff",
    "treeline_birch",
    "treeline_lamp",
    "snow_mound_wide",
    "snow_mound_small",
}


def dither(im):
    a = im.getchannel("A")
    px = a.load()
    for y in range(a.height):
        for x in range(a.width):
            px[x, y] = 255 if px[x, y] > (BAYER4[y % 4][x % 4] + 0.5) * 16 else 0
    out = im.copy()
    out.putalpha(a)
    return out


def pack(atlas, cell, columns, alpha, items):
    """items: list of (frame_name, image, align) with align 'bottom' or 'centre'."""
    inner = cell if alpha == "opaque" else cell - 4
    off = 0 if alpha == "opaque" else 2
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new("RGBA", (inner * columns, inner * rows), (0, 0, 0, 0))
    frames = []
    for i, (name, im, align) in enumerate(items):
        room = inner - 2  # 1 px clear border: the packer strips light pixels touching the sheet edge
        if im.width > room or im.height > room:
            f = min(room / im.width, room / im.height)
            im = im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))), Image.LANCZOS)
        x = (inner - im.width) // 2
        y = inner - im.height - 1 if align == "bottom" else (inner - im.height) // 2
        sheet.alpha_composite(im, ((i % columns) * inner + x, (i // columns) * inner + y))
        frames.append({"name": name})
        rects.append((name, off + x, off + y, im.width, im.height))
    sheet.save(ASSETS_SRC / f"{atlas}_source.png")
    (ASSETS_SRC / f"{atlas}.json").write_text(
        json.dumps(
            {
                "image": f"{atlas}_source.png",
                "columns": columns,
                "rows": rows,
                "output_cell": cell,
                "alpha_mode": alpha,
                "frames": frames,
            },
            indent=1,
        )
        + "\n"
    )
    return {"config": f"{atlas}.json", "source": f"{atlas}_source.png", "output": f"{atlas}.atlas"}


def main():
    atlases = []

    pano = load("sky_panorama").resize((480, 240), Image.LANCZOS)
    atlases.append(
        pack(
            "husky_sky",
            240,
            2,
            "opaque",
            [("sky_l", pano.crop((0, 0, 240, 240)), "centre"), ("sky_r", pano.crop((240, 0, 480, 240)), "centre")],
        )
    )

    atlases.append(
        pack(
            "husky_large",
            260,
            2,
            "binary",
            [
                ("treeline_birch", load("treeline_birch"), "bottom"),
                ("treeline_lamp", load("treeline_lamp"), "bottom"),
                ("team_run", load("team_run"), "bottom"),
                ("team_lookback", load("team_lookback"), "bottom"),
            ],
        )
    )

    small = [
        "lamp_glow",
        "light_pool",
        "shadow_soft",
        "paw_spray",
        "snow_puff",
        "towline",
        "snow_mound_wide",
        "snow_mound_small",
    ]
    atlases.append(pack("husky_small", 100, 4, "binary", [(n, load(n), "centre") for n in small]))

    bow = load("sled_bow")
    slice_w = 84
    count = (bow.width + slice_w - 1) // slice_w
    padded = Image.new("RGBA", (slice_w * count, bow.height), (0, 0, 0, 0))
    padded.alpha_composite(bow, ((padded.width - bow.width) // 2, 0))
    atlases.append(
        pack(
            "husky_bow",
            90,
            count,
            "binary",
            [
                (f"bow_{i}", padded.crop((i * slice_w, 0, (i + 1) * slice_w, bow.height)), "bottom")
                for i in range(count)
            ],
        )
    )

    (ASSETS_SRC / "game_assets.json").write_text(
        json.dumps({"schema": "mosaico-game-assets/v1", "limit_bytes": 4 * 1024 * 1024, "atlases": atlases}, indent=1)
        + "\n"
    )

    team = META["team_run"]
    look = META["team_lookback"]
    lamp_frac = ((1037 - 760) / (1254 - 760), (425 - 60) / (740 - 60))  # in the source crop
    lines = [
        "// SPDX-License-Identifier: Apache-2.0",
        "// Generated by assets_src/library_tools/build_atlases.py; do not edit.",
        "#pragma once",
        "",
        "/* Pixel rect of each sprite inside its packed atlas cell. */",
        "typedef struct { const char *name; short x, y, w, h; } husky_art_rect_t;",
        "",
        "static const husky_art_rect_t HUSKY_ART_RECTS[] = {",
    ]
    lines += [f'    {{"{n}", {x}, {y}, {w}, {h}}},' for n, x, y, w, h in rects]
    lines += [
        "};",
        "",
        f"#define HUSKY_ART_RECT_COUNT {len(rects)}U",
        f"#define HUSKY_BOW_SLICES {count}",
        f"#define HUSKY_BOW_SLICE_W {slice_w}",
        "/* Towline ring inside the team sprites, as a fraction of the sprite size. */",
        f"#define HUSKY_TEAM_RUN_RING_FX {team['anchor_ring'][0] / team['width']:.3f}f",
        f"#define HUSKY_TEAM_RUN_RING_FY {team['anchor_ring'][1] / team['height']:.3f}f",
        f"#define HUSKY_TEAM_LOOK_RING_FX {look['anchor_ring'][0] / look['width']:.3f}f",
        f"#define HUSKY_TEAM_LOOK_RING_FY {look['anchor_ring'][1] / look['height']:.3f}f",
        "/* Lamp head inside treeline_lamp, as a fraction of the sprite size. */",
        f"#define HUSKY_LAMP_HEAD_FX {lamp_frac[0]:.3f}f",
        f"#define HUSKY_LAMP_HEAD_FY {lamp_frac[1]:.3f}f",
        "",
    ]
    HEADER.write_text("\n".join(lines))
    print("atlases:", [a["output"] for a in atlases], "rects:", len(rects))


if __name__ == "__main__":
    main()
