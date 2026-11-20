#!/usr/bin/env python3
"""Deterministically pack reviewed raster art into RGB565 + alpha C assets."""

from collections import deque
from pathlib import Path
import random
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "components/app_game_runtime/private"
OUT.mkdir(parents=True, exist_ok=True)
assets = []


def add(name, im, size):
    im = im.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    assets.append((name, im))


bg = Image.open(ROOT.parent / "assets/review/2026_11_19/turns_v2/snow_base_straight_v2.png").convert("RGBA")
add("forest", bg, (480, 480))
# Mirror a real snow patch at its edges for a continuous projected ground tile.
snow = bg.crop((480, 850, 736, 1106)).resize((128, 128), Image.Resampling.LANCZOS)
tile = Image.new("RGBA", (256, 256))
tile.paste(snow, (0, 0))
tile.paste(ImageOps.mirror(snow), (128, 0))
tile.paste(ImageOps.flip(snow), (0, 128))
tile.paste(ImageOps.flip(ImageOps.mirror(snow)), (128, 128))
add("snow", tile, (256, 256))
run = Image.open(ROOT / "husky_run_sheet.png").convert("RGBA")
run_frames = []
for i in range(8):
    x, y = i % 4, i // 4
    im = run.crop((x * run.width // 4, y * run.height // 2, (x + 1) * run.width // 4, (y + 1) * run.height // 2))
    box = im.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
    im = im.crop(box)
    # Same registered canvas for every gait phase; preserve body proportions.
    im.thumbnail((90, 158), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (96, 164))
    canvas.alpha_composite(im, ((96 - im.width) // 2, 3))
    run_frames.append(canvas)
    add("run_" + str(i), canvas, (96, 164))

# Idle tail-wag frames: 7 sequential frames extracted directly from the
# user-supplied sprite strip idle_tail_reference.jpg (1024x342). Each dog is
# cut from its clean column slot inside the uniform pale band, matted via
# border flood-fill with color-projected edge decontamination, and registered
# onto a symmetrically wider 112x164 canvas so the full tail sweep fits while
# keeping head/body alignment identical to run_0..7. Played only while stopped.
IDLE_BAND_Y = (45, 295)
IDLE_SLICE_X = (0, 146, 294, 435, 583, 728, 869, 1024)
IDLE_CANVAS_SIZE = (112, 164)
IDLE_TARGET_HEIGHT = 158
IDLE_SRC_DOG_HEIGHT = 240
# Match run_7's head-center offset (+12.5 px right of canvas center).
IDLE_HEAD_CX = IDLE_CANVAS_SIZE[0] / 2 + 12.5


def _color_dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def _extract_idle_dog(ref, x0, x1):
    sub = ref.crop((x0, IDLE_BAND_Y[0], x1, IDLE_BAND_Y[1]))
    sw, sh = sub.size
    spx = sub.load()
    border = [spx[x, 0] for x in range(sw)] + [spx[x, sh - 1] for x in range(sw)]
    bg = tuple(round(sum(c[ch] for c in border) / len(border)) for ch in range(3))

    bg_mask = [[False] * sw for _ in range(sh)]
    queue = deque()
    for x in range(sw):
        for y in (0, sh - 1):
            if _color_dist(spx[x, y], bg) <= 20 and not bg_mask[y][x]:
                bg_mask[y][x] = True
                queue.append((x, y))
    for y in range(sh):
        for x in (0, sw - 1):
            if _color_dist(spx[x, y], bg) <= 20 and not bg_mask[y][x]:
                bg_mask[y][x] = True
                queue.append((x, y))
    while queue:
        cx, cy = queue.popleft()
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if 0 <= nx < sw and 0 <= ny < sh and not bg_mask[ny][nx] and _color_dist(spx[nx, ny], bg) <= 20:
                bg_mask[ny][nx] = True
                queue.append((nx, ny))

    dist_map = [[99] * sw for _ in range(sh)]
    dist_q = deque()
    for y in range(sh):
        for x in range(sw):
            if bg_mask[y][x]:
                dist_map[y][x] = 0
                dist_q.append((x, y))
    while dist_q:
        cx, cy = dist_q.popleft()
        d = dist_map[cy][cx]
        if d >= 3:
            continue
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if 0 <= nx < sw and 0 <= ny < sh and dist_map[ny][nx] > d + 1:
                dist_map[ny][nx] = d + 1
                dist_q.append((nx, ny))

    out = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    opx = out.load()
    for y in range(sh):
        for x in range(sw):
            if bg_mask[y][x]:
                continue
            r, g, b = spx[x, y]
            d_edge = dist_map[y][x]
            if d_edge <= 2:
                fg_samples = [
                    spx[x + dx, y + dy]
                    for dy in range(-2, 3)
                    for dx in range(-2, 3)
                    if 0 <= x + dx < sw and 0 <= y + dy < sh and dist_map[y + dy][x + dx] >= 3
                ]
                if fg_samples:
                    fg = tuple(sum(c[ch] for c in fg_samples) / len(fg_samples) for ch in range(3))
                    vx, vy, vz = fg[0] - bg[0], fg[1] - bg[1], fg[2] - bg[2]
                    denom = vx * vx + vy * vy + vz * vz
                    if denom > 200.0:
                        alpha_f = max(0.0, min(1.0, ((r - bg[0]) * vx + (g - bg[1]) * vy + (b - bg[2]) * vz) / denom))
                    else:
                        alpha_f = max(0.0, min(1.0, (_color_dist((r, g, b), bg) - 18.0) / 40.0))
                    if d_edge == 1:
                        alpha_f = min(alpha_f, 0.85)
                    if alpha_f < 0.08:
                        continue
                    if alpha_f < 0.98:
                        inv = max(alpha_f, 0.35)
                        dr = int(max(0, min(255, fg[0] * 0.65 + ((r - (1.0 - alpha_f) * bg[0]) / inv) * 0.35)))
                        dg = int(max(0, min(255, fg[1] * 0.65 + ((g - (1.0 - alpha_f) * bg[1]) / inv) * 0.35)))
                        db = int(max(0, min(255, fg[2] * 0.65 + ((b - (1.0 - alpha_f) * bg[2]) / inv) * 0.35)))
                        opx[x, y] = (dr, dg, db, int(round(alpha_f * 255)))
                    else:
                        opx[x, y] = (r, g, b, 255)
                else:
                    alpha_f = max(0.0, min(1.0, (_color_dist((r, g, b), bg) - 18.0) / 48.0))
                    if alpha_f >= 0.1:
                        opx[x, y] = (r, g, b, int(round(alpha_f * 255)))
            else:
                opx[x, y] = (r, g, b, 255)
    return out


def _darken_idle_edges(canvas):
    """Soften and darken bright matte fringes along the outer 1..3 px so idle
    tails match husky_run_sheet's darker antialiased edges on snow and fur."""
    w, h = canvas.size
    px = canvas.load()
    dist = [[99] * w for _ in range(h)]
    queue = deque()
    for y in range(h):
        for x in range(w):
            if px[x, y][3] < 40:
                dist[y][x] = 0
                queue.append((x, y))
    while queue:
        cx, cy = queue.popleft()
        d = dist[cy][cx]
        if d >= 4:
            continue
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if 0 <= nx < w and 0 <= ny < h and dist[ny][nx] > d + 1:
                dist[ny][nx] = d + 1
                queue.append((nx, ny))

    for y in range(h):
        for x in range(w):
            d = dist[y][x]
            if d == 0 or d > 3:
                continue
            r, g, b, a = px[x, y]
            luma = (r + g + b) / 3.0
            in_tail = x < 60 and 30 <= y <= 115
            if d == 1:
                # Match run_7 outer rim (~115 luma, ~96 alpha) and keep alpha well
                # below sled_view's ALPHA_SOLID (192) so edges blend without white halos.
                target_cap = 115.0 if in_tail else 135.0
                scale = 0.62 if in_tail else 0.74
                if luma > target_cap:
                    scale = min(scale, target_cap / max(luma, 1.0))
                nr, ng, nb = int(round(r * scale)), int(round(g * scale)), int(round(b * scale))
                na = min(a, 110 if in_tail else 140)
                px[x, y] = (nr, ng, nb, na)
            elif d == 2:
                target_cap = 132.0 if in_tail else 160.0
                scale = 0.76 if in_tail else 0.88
                if luma > target_cap:
                    scale = min(scale, (target_cap + (luma - target_cap) * 0.15) / max(luma, 1.0))
                nr, ng, nb = int(round(r * scale)), int(round(g * scale)), int(round(b * scale))
                px[x, y] = (nr, ng, nb, min(a, 180 if in_tail else a))
            elif d == 3 and in_tail and luma > 148.0:
                scale = (148.0 + (luma - 148.0) * 0.35) / luma
                px[x, y] = (int(round(r * scale)), int(round(g * scale)), int(round(b * scale)), a)
    return canvas


_idle_ref = Image.open(ROOT / "idle_tail_reference.jpg").convert("RGB")
for i in range(len(IDLE_SLICE_X) - 1):
    dog = _extract_idle_dog(_idle_ref, IDLE_SLICE_X[i], IDLE_SLICE_X[i + 1])
    box = dog.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
    dog = dog.crop(box)
    dpx = dog.load()
    ear_xs = [x for y in range(min(30, dog.height)) for x in range(dog.width) if dpx[x, y][3] > 128]
    head_cx = (min(ear_xs) + max(ear_xs)) / 2.0
    scale = IDLE_TARGET_HEIGHT / IDLE_SRC_DOG_HEIGHT
    nw, nh = max(1, round(dog.width * scale)), max(1, round(dog.height * scale))
    resized = dog.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", IDLE_CANVAS_SIZE, (0, 0, 0, 0))
    ox = round(IDLE_HEAD_CX - head_cx * scale)
    oy = 3 + round((IDLE_TARGET_HEIGHT - nh) / 2)
    canvas.alpha_composite(resized, (ox, oy))
    _darken_idle_edges(canvas)
    add("idle_" + str(i), canvas, IDLE_CANVAS_SIZE)
scene = Image.open(ROOT / "scenery_sheet.png").convert("RGBA")
for i, (name, maxsize) in enumerate(
    [("birch", (300, 600)), ("trees", (400, 600)), ("lamp", (64, 220)), ("sled", (480, 220))]
):
    x, y = i % 2, i // 2
    im = scene.crop(
        (x * scene.width // 2, y * scene.height // 2, (x + 1) * scene.width // 2, (y + 1) * scene.height // 2)
    )
    box = im.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
    im = im.crop(box)
    im.thumbnail(maxsize, Image.Resampling.LANCZOS)
    add(name, im, im.size)
cutouts = dict(assets)
fog = bg.convert("RGB").resize((480, 480), Image.Resampling.LANCZOS).getpixel((240, 232))
# Pre-filtered half/quarter copies (mip levels): smaller trees sample these, which
# avoids aliasing and keeps flash-cache traffic proportional to on-screen size.
for name in ("birch", "trees"):
    im = cutouts[name]
    half = im.resize((im.width // 2, im.height // 2), Image.Resampling.LANCZOS)
    # Mid-distance trees: bake a light haze so the renderer skips a per-pixel blend.
    hazed = Image.blend(half, Image.new("RGBA", half.size, fog + (255,)), 0.12)
    add(name + "_h", Image.composite(hazed, Image.new("RGBA", half.size), half.getchannel("A")), half.size)
    add(name + "_s", im, (im.width // 4, im.height // 4))

# Distant forest wall at the horizon, composed from the same tree cutouts and
# tinted toward the plate's horizon colour (aerial perspective). Column 480 sits
# on the vanishing point; a narrow gap leaves room for the trail.
rng = random.Random(20261120)
band = Image.new("RGBA", (960, 72))
for count, low, high, haze in [(150, 14, 30, 0.62), (110, 22, 46, 0.50), (90, 34, 66, 0.40), (40, 44, 70, 0.34)]:
    for _ in range(count):
        src = cutouts["birch" if rng.random() < 0.6 else "trees"]
        h = rng.randint(low, high)
        w = max(2, src.width * h // src.height)
        im = src.resize((w, h), Image.Resampling.LANCZOS)
        if rng.random() < 0.5:
            im = ImageOps.mirror(im)
        tint = Image.new("RGBA", im.size, fog + (255,))
        im = Image.composite(Image.blend(im, tint, haze), Image.new("RGBA", im.size), im.getchannel("A"))
        x = rng.randrange(0, 960)
        if abs(x - 480) < 14 + w // 2:
            continue
        band.alpha_composite(im, (x - w // 2, band.height - h - rng.randint(0, 3)))
add("far_forest", band, band.size)

# Real rope textures cut from the six-husky render: vertical strips, length along y,
# plus the metal ring/junction pieces where ropes meet.
team = Image.open(ROOT / "six_huskies_cutout.png").convert("RGBA")
add("rope_red", team.crop((606, 440, 630, 600)), (12, 80))
add("rope_blue", team.crop((592, 1000, 640, 1100)), (24, 50))
add("rope_joint", team.crop((588, 606, 652, 670)), (32, 32))
add("rope_ring", team.crop((580, 912, 660, 992)), (40, 40))
header = """// SPDX-License-Identifier: Apache-2.0
// Generated by assets_src/prepare_art.py. Do not edit by hand.
#pragma once
#include <stdint.h>
typedef struct {
    int width, height;
    const uint16_t *rgb;
    const uint8_t *alpha;
    const int16_t *span; /* per row: first, last column with alpha >= 24; NULL if opaque */
} sled_image_t;
const sled_image_t *sled_asset(const char *name);
"""
(OUT / "sled_assets.h").write_text(header)
with (OUT / "sled_assets.c").open("w") as f:
    f.write(
        '// SPDX-License-Identifier: Apache-2.0\n// Generated by assets_src/prepare_art.py.\n#include "sled_assets.h"\n#include <string.h>\n'
    )
    for name, im in assets:
        data = list(im.get_flattened_data())
        rgb = [((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3) for r, g, b, a in data]
        f.write("static const uint16_t " + name + "_rgb[] = {\n")
        for j in range(0, len(rgb), 24):
            f.write(",".join(str(v) for v in rgb[j : j + 24]) + ",\n")
        f.write("};\n")
        alpha = [a for r, g, b, a in data]
        if min(alpha) < 255:
            f.write("static const uint8_t " + name + "_alpha[] = {\n")
            for j in range(0, len(alpha), 48):
                f.write(",".join(str(a) for a in alpha[j : j + 48]) + ",\n")
            f.write("};\n")
            # Row spans let the renderer skip transparent margins of each row.
            spans = []
            for y in range(im.height):
                row = alpha[y * im.width : (y + 1) * im.width]
                cols = [x for x, a in enumerate(row) if a >= 24]
                spans += [cols[0], cols[-1]] if cols else [1, 0]
            f.write("static const int16_t " + name + "_span[] = {\n")
            for j in range(0, len(spans), 32):
                f.write(",".join(str(v) for v in spans[j : j + 32]) + ",\n")
            f.write("};\n")
        f.write(
            "static const sled_image_t "
            + name
            + " = {"
            + str(im.width)
            + ","
            + str(im.height)
            + ","
            + name
            + "_rgb,"
            + (name + "_alpha," + name + "_span" if min(alpha) < 255 else "0,0")
            + "};\n"
        )
    f.write("const sled_image_t *sled_asset(const char *name)\n{\n    if (!name) {\n        return 0;\n    }\n")
    for name, im in assets:
        f.write('    if (strcmp(name, "' + name + '") == 0) {\n        return &' + name + ";\n    }\n")
    f.write("    return 0;\n}\n")
print("Packed", len(assets), "images into RGB565 assets")

# Keep generated pixel blocks individually reviewable and below repository limits.
source = (OUT / "sled_assets.c").read_text()
generated = OUT / "generated"
generated.mkdir(exist_ok=True)
start = source.index("static const uint16_t")
lookup = source.index("const sled_image_t *sled_asset(")
blocks = source[start:lookup].split("static const uint16_t ")[1:]
includes = []
for block in blocks:
    name = block.split("_rgb[]", 1)[0]
    filename = "sled_" + name + ".inc"
    (generated / filename).write_text("// Generated pixel data.\nstatic const uint16_t " + block)
    includes.append('#include "generated/' + filename + '"\n')
(OUT / "sled_assets.c").write_text(source[:start] + "".join(includes) + source[lookup:])
