#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose review screens using ONLY assets_src/library parts.

This checks that the library is complete and that the reuse rules (flips,
tints, 9-slice, depth scaling) hold up. The pseudo-3D trail here is a rough
stand-in for the runtime renderer, not the renderer itself.
Usage: python make_library_review.py <out_dir>
"""

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from libkit import LANCZOS, checker

LIB = Path(__file__).resolve().parent.parent / "library"
W = H = 480
META = json.loads((LIB / "asset_library.json").read_text())
BY_NAME = {a["name"]: a for a in META["assets"]}


def A(name):
    entry = BY_NAME[name]
    if "alias_of" in entry:
        entry = BY_NAME[entry["alias_of"]]
    return Image.open(LIB / entry["file"]).convert("RGBA")


def flip(im):
    return im.transpose(Image.FLIP_LEFT_RIGHT)


def tint(im, color, alpha=1.0):
    out = Image.new("RGBA", im.size, color + (0,))
    out.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    r, g, b, a = im.split()
    base = Image.merge("RGBA", (r, g, b, a))
    mult = Image.new("RGBA", im.size, color + (255,))
    from PIL import ImageChops

    colored = ImageChops.multiply(base, mult)
    colored.putalpha(out.getchannel("A"))
    return colored


def sz(im, f):
    return im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))), LANCZOS)


def put(canvas, im, x, y, anchor="mm"):
    ox = {"l": 0, "m": im.width // 2, "r": im.width}[anchor[0]]
    oy = {"t": 0, "m": im.height // 2, "b": im.height}[anchor[1]]
    canvas.alpha_composite(im, (int(x - ox), int(y - oy)))


def pill(canvas, x, y, width):
    cap, mid = A("pill_cap"), A("pill_mid")
    canvas.alpha_composite(cap, (x, y))
    canvas.alpha_composite(mid.resize((width - 2 * cap.width, mid.height)), (x + cap.width, y))
    canvas.alpha_composite(flip(cap), (x + width - cap.width, y))
    return cap.height


def panel(canvas, box):
    x0, y0, x1, y1 = box
    c, e, f = A("panel_corner"), A("panel_edge"), A("panel_fill")
    n = c.width
    canvas.alpha_composite(f.resize((x1 - x0 - 2 * n, y1 - y0 - 2 * n)), (x0 + n, y0 + n))
    top = e.resize((x1 - x0 - 2 * n, n))
    canvas.alpha_composite(top, (x0 + n, y0))
    canvas.alpha_composite(top.transpose(Image.FLIP_TOP_BOTTOM), (x0 + n, y1 - n))
    side = e.rotate(90, expand=True).resize((n, y1 - y0 - 2 * n))
    canvas.alpha_composite(side, (x0, y0 + n))
    canvas.alpha_composite(flip(side), (x1 - n, y0 + n))
    canvas.alpha_composite(c, (x0, y0))
    canvas.alpha_composite(flip(c), (x1 - n, y0))
    canvas.alpha_composite(c.transpose(Image.FLIP_TOP_BOTTOM), (x0, y1 - n))
    canvas.alpha_composite(flip(c).transpose(Image.FLIP_TOP_BOTTOM), (x1 - n, y1 - n))


def number(canvas, text, x, y, size="s", anchor="l", color=None):
    names = {":": "colon", ".": "dot", "/": "slash", "%": "pct"}
    glyphs = [A(f"glyph_{size}_{names.get(ch, ch)}") for ch in text]
    if color:
        glyphs = [tint(g, color) for g in glyphs]
    adv = [g.width - 7 for g in glyphs]  # sprites carry 4 px padding per side
    total = sum(adv)
    cx = x - {"l": 0, "m": total // 2, "r": total}[anchor]
    for g, a in zip(glyphs, adv):
        put(canvas, g, cx, y, "lm")
        cx += a


def scene(state="team_run", heat=0.7, curve=0.0):
    im = Image.new("RGBA", (W, H))
    pano = A("sky_panorama")
    horizon = pano.height - 20
    off = int(120 + curve * 200) % (pano.width * 2)
    strip = Image.new("RGBA", (pano.width * 3, pano.height))
    for k, p in enumerate((pano, flip(pano), pano)):  # wrap: A | flip(A) | A
        strip.paste(p, (k * pano.width, 0))
    im.paste(strip.crop((off, 20, off + W, 20 + horizon)), (0, 0))

    # Ground: tile rows with depth-scaled texture, darker verge outside the trail.
    tile = A("snow_ground").convert("RGB")
    gpx = tile.load()
    px = im.load()
    for y in range(horizon, H):
        z = (y - horizon + 1) / (H - horizon)
        half = 18 + 230 * z
        centre = W / 2 + curve * 160 * (1 - z) ** 2
        for x in range(W):
            u = int((x - centre) / (z + 0.05) * 0.35) % 128
            v = int(40 / (z + 0.02)) % 128
            r, g, b = gpx[u, v]
            dist = abs(x - centre) / half
            k = 1.0 if dist < 1 else 0.86
            for rut in (-0.32, 0.32):
                if abs(dist * (1 if x > centre else -1) - rut) < 0.035:
                    k *= 0.88
            px[x, y] = (int(r * k), int(g * k), int(b * k * 1.02), 255)

    # Roadside billboards back to front, mirrored on the far side.
    props = []
    for i, d in enumerate((0.92, 0.8, 0.68, 0.55, 0.42, 0.3, 0.18, 0.06)):
        z = 1 - d
        for side in (-1, 1):
            name = "treeline_lamp" if (i + (side > 0)) % 3 == 0 else "treeline_birch"
            props.append((z, side, name, i))
    props.sort()
    for z, side, name, i in props:
        y = horizon + (H - horizon) * z**1.6 * 0.6
        half = 18 + 230 * z**1.6 * 0.6
        centre = W / 2 + curve * 160 * (1 - z) ** 2
        f = 0.25 + 1.4 * z**1.6
        spr = A(name)
        spr = sz(spr if side < 0 else flip(spr), f)
        x = centre + side * (half * 1.25 + spr.width * 0.45)
        put(im, spr, x, y + 4, "mb")
        if name == "treeline_lamp" and f > 0.3:
            lx = x + (spr.width * 0.33 if side < 0 else -spr.width * 0.33)
            put(im, sz(A("lamp_glow"), f * 1.1), lx, y - spr.height * 0.86)
            put(im, sz(A("light_pool"), f * 1.3), lx, y)
        if i % 2 == 0 and z > 0.3:
            m = sz(A("snow_mound_wide"), f * 0.8)
            put(im, m if side < 0 else flip(m), centre + side * (half * 1.05), y + 6, "mb")

    team = A(state)
    entry = BY_NAME[state]
    entry = BY_NAME.get(entry.get("alias_of"), entry)
    rx, ry = entry["anchor_ring"]
    ring_y = 352  # the towline ring always sits here; both states align to it
    tx, ty = W / 2 - rx, ring_y - ry
    feet = ty + team.height
    put(im, sz(A("shadow_soft"), 2.6), W / 2, feet - 6)
    tl = A("towline")
    put(im, tl.resize((tl.width, H - ring_y - 50)), W / 2, ring_y, "mt")
    for sx in (-62, 62):
        put(im, tint(A("paw_spray"), (225, 235, 255), 0.8), W / 2 + sx, feet + 2, "mb")
    im.alpha_composite(team, (int(tx), int(ty)))
    put(im, A("sled_bow"), W / 2, H, "mb")

    import random

    rnd = random.Random(3)
    streak = A("snow_streak")
    for _ in range(int(30 + 120 * heat)):
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(150, 320)
        s = streak.resize((streak.width, int(streak.height * (0.5 + heat))))
        s = s.rotate(-math.degrees(a) - 90, expand=True, resample=Image.BICUBIC)
        put(im, s, W / 2 + math.cos(a) * r, horizon + math.sin(a) * r)
    if heat > 0.66:
        fr = A("frost_corner")
        a = (heat - 0.66) / 0.34
        fr.putalpha(fr.getchannel("A").point(lambda v: int(v * a)))
        put(im, fr, 0, 0, "lt")
        put(im, flip(fr), W, 0, "rt")
        put(im, fr.transpose(Image.FLIP_TOP_BOTTOM), 0, H, "lb")
        put(im, flip(fr).transpose(Image.FLIP_TOP_BOTTOM), W, H, "rb")
    return im


def hud(im, heat):
    pill(im, 14, 14, 104)
    number(im, "01280", 66, 29, anchor="m")
    pill(im, W - 104, 14, 90)
    put(im, A("lap"), W - 92, 29, "lm")
    number(im, "2/3", W - 62, 29)
    panel(im, (W - 92, H - 150, W - 14, H - 72))
    put(im, A("minimap_track"), W - 53, H - 111)
    info = BY_NAME["minimap_track"]["track_to_px"]  # dot sits on the real path
    k, (mx, mz) = info["scale"], info["centre_m"]
    from prepare_library import track_points

    x, z = track_points()[300]
    put(im, A("map_dot"), W - 53 + (x - mx) * k, H - 111 - (z - mz) * k)
    tier = min(2, int(heat * 3))
    for i in range(3):
        col = (255, 184, 92) if i <= tier else (180, 190, 210)
        put(im, tint(A("icon_snowflake"), col, 1 if i <= tier else 0.5), W / 2 - 22 + i * 22, 452)
    put(im, tint(A(["tier_breeze", "tier_snow", "tier_blizzard"][tier]), (255, 184, 92)), W / 2, 430)


def title():
    im = A("menu_backdrop").resize((W, H), LANCZOS)
    put(im, A("team_stop"), W / 2, 310, "mm")
    put(im, A("sled_bow"), W / 2, H, "mb")
    put(im, A("title_cn"), W / 2, 70)
    put(im, tint(A("title_en"), (255, 184, 92)), W / 2, 104)
    for i, (n, sub, ic) in enumerate(
        (("mode_tilt", "mode_tilt_sub", "icon_tilt"), ("mode_keys", "mode_keys_sub", "icon_keys"))
    ):
        x0 = 92 + i * 156
        panel(im, (x0, 316, x0 + 140, 406))
        put(im, A(ic) if i == 0 else tint(A(ic), (200, 210, 230)), x0 + 70, 338)
        put(im, A(n), x0 + 70, 366)
        put(im, A(sub), x0 + 70, 390)
    put(im, A("hint_start"), W / 2, 432)
    return im


def result():
    im = A("menu_backdrop").resize((W, H), LANCZOS)
    panel(im, (60, 60, 420, 420))
    put(im, A("finish"), W / 2, 100)
    number(im, "03840", W / 2, 160, "l", "m", (255, 184, 92))
    put(im, A("new_record"), W / 2, 206)
    rows = [("total_time", "2:41.6"), ("best_lap", "0:52.3"), ("max_heat", "96%")]
    for i, (k, v) in enumerate(rows):
        y = 250 + i * 40
        put(im, A(k), 92, y, "lm")
        number(im, v, 388, y, anchor="r")
    put(im, A("hint_retry"), W / 2, 388)
    return im


def pause(base):
    im = base.copy()
    dim = Image.new("RGBA", im.size, (10, 18, 40, 120))
    im.alpha_composite(dim)
    panel(im, (130, 170, 350, 310))
    put(im, A("btn_pause"), W / 2, 205)
    put(im, A("paused"), W / 2, 250)
    put(im, A("hint_resume"), W / 2, 288)
    return im


def contact_sheet():
    cols, cell, label_h = 8, 120, 26
    items = [a for a in META["assets"] if "alias_of" not in a and not a["name"].startswith("glyph_l")]
    rows = math.ceil(len(items) / cols)
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (245, 246, 250))
    bg = checker((cell - 8, cell - 8), (66, 84, 120), (54, 70, 104))
    f = ImageFont.truetype(str(Path.home() / "Library/Fonts/SourceHanSansCN-Medium.ttf"), 10)
    d = ImageDraw.Draw(sheet)
    for i, a in enumerate(items):
        x, y = (i % cols) * cell, (i // cols) * (cell + label_h)
        sheet.paste(bg, (x + 4, y + 4))
        im = Image.open(LIB / a["file"]).convert("RGBA")
        s = min((cell - 12) / im.width, (cell - 12) / im.height, 2.0)
        im = sz(im, s)
        tile = Image.new("RGBA", bg.size, (0, 0, 0, 0))
        tile.alpha_composite(im, ((tile.width - im.width) // 2, (tile.height - im.height) // 2))
        sheet.paste(tile, (x + 4, y + 4), tile)
        d.text((x + 4, y + cell), a["name"], font=f, fill=(30, 30, 40))
        d.text((x + 4, y + cell + 12), f"{a['width']}x{a['height']} {a['alpha']}", font=f, fill=(110, 110, 130))
    return sheet


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    run = scene("team_run", 0.72)
    hud(run, 0.72)
    look = scene("team_lookback", 0.4, curve=0.6)
    hud(look, 0.4)
    blizzard = scene("team_run", 1.0, curve=-0.5)
    hud(blizzard, 1.0)
    shots = {
        "screen_run.png": run,
        "screen_lookback_curve.png": look,
        "screen_blizzard.png": blizzard,
        "screen_title.png": title(),
        "screen_result.png": result(),
        "screen_pause.png": pause(run),
    }
    for name, im in shots.items():
        im.convert("RGB").save(out / name)
    overview = Image.new("RGB", (W * 3, H * 2), "white")
    for i, im in enumerate(shots.values()):
        overview.paste(im.convert("RGB"), ((i % 3) * W, (i // 3) * H))
    overview.save(out / "overview_screens.png")
    contact_sheet().save(out / "overview_assets.png")
    print("wrote", out)


if __name__ == "__main__":
    main()
