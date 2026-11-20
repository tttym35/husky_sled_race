#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the Husky Sled Race asset library from the four AI source images.

Every runtime asset is derived from the sources in assets/review/2026_11_19
(or drawn procedurally) at its on-screen size, so nothing is stored larger than
it is drawn. Reuse is preferred over new bitmaps: mirrored sides, tinted white
FX, 9-slice UI and one team sprite per state.

Outputs
  assets_src/library/<group>/<name>.png  runtime-size cut-outs
  assets_src/library/asset_library.json  manifest: size, alpha, reuse, anchors
Run with the project .venv (Pillow):  python prepare_library.py
"""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from libkit import LANCZOS, mirror_tile, scale, trim

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
SRC = PROJECT / "assets/review/2026_11_19"
OUT = PROJECT / "assets_src/library"

SCREEN = 480
BG_SCALE = SCREEN / 1254  # source plates are 1254 px square
TEAM_WIDTH = 257  # on-screen dog team width (tails included)
FONT_BOLD = str(Path.home() / "Library/Fonts/SourceHanSansCN-Bold.ttf")
FONT_MED = str(Path.home() / "Library/Fonts/SourceHanSansCN-Medium.ttf")
AMBER = (255, 184, 92)

# Same segment table as components/app_game/sled_track.c (length m, turn deg).
SEGMENTS = [
    (96, 0),
    (64, 60),
    (48, 0),
    (56, -45),
    (80, 90),
    (72, 0),
    (48, 45),
    (40, 0),
    (64, 0),
    (112, 120),
    (40, -30),
    (96, 120),
    (64, 0),
]

manifest = []


def save(group, name, im, alpha, reuse="", **extra):
    """alpha: opaque | binary | smooth (matches the engine atlas alpha_mode)."""
    path = OUT / group / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    if alpha == "opaque":
        im = im.convert("RGB")
    im.save(path)
    bpp = 2 if alpha == "opaque" else 3
    entry = {
        "name": name,
        "group": group,
        "file": str(path.relative_to(OUT)),
        "width": im.width,
        "height": im.height,
        "alpha": alpha,
        "bytes_rgb565": im.width * im.height * bpp,
    }
    if reuse:
        entry["reuse"] = reuse
    entry.update(extra)
    manifest.append(entry)
    return im


def alias(group, name, target, note):
    manifest.append({"name": name, "group": group, "alias_of": target, "bytes_rgb565": 0, "reuse": note})


def font(size, bold=True):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_MED, size)


def mask_from(im, keep):
    """Build an L mask from a per-pixel predicate keep(r, g, b, x, y)."""
    px = im.load()
    m = Image.new("L", im.size, 0)
    mp = m.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = px[x, y][:3]
            if keep(r, g, b, x, y):
                mp[x, y] = 255
    return m


def largest_components(mask, min_area):
    """Drop connected islands smaller than min_area (4-connectivity)."""
    from collections import deque

    w, h = mask.size
    src = mask.load()
    out = Image.new("L", mask.size, 0)
    dst = out.load()
    seen = bytearray(w * h)
    for sy in range(h):
        for sx in range(w):
            if not src[sx, sy] or seen[sy * w + sx]:
                continue
            q, pts = deque([(sx, sy)]), []
            seen[sy * w + sx] = 1
            while q:
                x, y = q.popleft()
                pts.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and src[nx, ny] and not seen[ny * w + nx]:
                        seen[ny * w + nx] = 1
                        q.append((nx, ny))
            if len(pts) >= min_area:
                for x, y in pts:
                    dst[x, y] = 255
    return out


# --------------------------------------------------------------------------- env
def build_environment(bg):
    # Sky + far forest down to the trail's vanishing point. The runtime tiles
    # [panorama | mirrored panorama] for a seamless 960 px scroll.
    pano = scale(bg.crop((0, 0, 1254, 610)), BG_SCALE)
    save(
        "env",
        "sky_panorama",
        pano,
        "opaque",
        reuse="draw twice: normal + horizontally flipped copy = seamless 960 px loop",
        horizon_y=pano.height,
    )

    ground = mirror_tile(bg.crop((40, 990, 296, 1246)).resize((64, 64), LANCZOS))
    save(
        "env",
        "snow_ground",
        ground,
        "opaque",
        reuse="2x2 mirror tile, wraps both ways; trail spans + deep-snow verge (tint darker)",
    )

    def sky_key(r, g, b, x, y):
        return (b - r > 28 and b > 150) or (y < 560 and r > g + 10 and b > g)

    def treeline(box, name, note):
        crop = bg.crop(box)
        ground_y = 600 - box[1]
        fade_end = crop.height
        m = mask_from(crop, lambda r, g, b, x, y: y >= ground_y or not sky_key(r, g, b, x, y))
        m = m.filter(ImageFilter.MedianFilter(3))
        mp = m.load()
        for y in range(ground_y, fade_end):
            f = 1 - (y - ground_y) / (fade_end - ground_y)
            for x in range(crop.width):
                mp[x, y] = int(mp[x, y] * f)
        im = crop.convert("RGBA")
        im.putalpha(m)
        return save("env", name, scale(im, BG_SCALE), "smooth", reuse=note, pivot="bottom-centre on the verge")

    treeline((0, 0, 520, 740), "treeline_birch", "roadside billboard; flip for the other side; scale by depth")
    treeline(
        (760, 60, 1254, 740),
        "treeline_lamp",
        "roadside billboard with lamp; flip for the other side; add fx/lamp_glow at the lamp head",
    )

    # Snow mounds: real snow texture from the plate with a soft mound silhouette.
    snow = bg.crop((560, 700, 1000, 900)).convert("RGBA")
    for name, w, h in (("snow_mound_wide", 150, 46), ("snow_mound_small", 84, 34)):
        tex = snow.resize((w, h), LANCZOS)
        m = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(m)
        d.ellipse((-w * 0.1, h * 0.05, w * 1.1, h * 1.9), fill=255)
        m = m.filter(ImageFilter.GaussianBlur(2.5))
        shade = Image.new("L", (w, h), 0)  # brighter crest, bluer base
        sd = ImageDraw.Draw(shade)
        for y in range(h):
            sd.line((0, y, w, y), fill=int(40 * (1 - y / h)))
        tex = Image.composite(Image.new("RGBA", (w, h), (255, 255, 255, 255)), tex, shade)
        tex.putalpha(m)
        save("env", name, tex, "smooth", reuse="verge prop; flip for variety; scale by depth")

    backdrop = bg.resize((160, 160), LANCZOS).filter(ImageFilter.GaussianBlur(2))
    save(
        "env",
        "menu_backdrop",
        backdrop,
        "opaque",
        reuse="upscale x3 behind title, pause and result cards (already blurred)",
    )


# -------------------------------------------------------------------------- team
def build_team(cutout, gameplay):
    # Running: the clean transparent render. The blue towline is split off at the
    # ring so both team states share one towline sprite and one anchor.
    ring_y = 975
    rope_box = (560, ring_y + 6, 680, 1254)
    team = cutout.copy()
    team.paste((0, 0, 0, 0), rope_box)  # towline lives in its own sprite
    x0, y0, _, _ = team.getchannel("A").getbbox()
    team = trim(team)
    s = TEAM_WIDTH / team.width
    run = scale(team, s)
    ring = (round((615 - x0) * s), round((ring_y - y0) * s))
    save(
        "team",
        "team_run",
        run,
        "smooth",
        reuse="runtime bob (2-3 px at stride rate), lean = small rotation, "
        "heat = faster bob; one bitmap for the whole running state",
        anchor_ring=ring,
    )

    rope = trim(cutout.crop(rope_box))
    save(
        "team",
        "towline",
        scale(rope, s),
        "smooth",
        reuse="shared by every team state; stretch vertically to reach the sled bow",
        anchor_top="centre",
    )

    # Look-back: keyed out of the gameplay concept, where the leaders turn their
    # heads. Same team width and ring anchor as team_run.
    box = (280, 380, 980, 862)
    crop = gameplay.crop(box)

    def dog_key(r, g, b, x, y):
        if x < 130 and y > 430:  # powder spray, front-left
            return False
        if x > 630 and y < 140:  # lit snow bank, top-right
            return False
        if y < 60 and not 280 < x < 420:  # treeline behind the leaders
            return False
        return r - b > 2 or max(r, g, b) < 95 or (r > 150 and g < 90)

    m = mask_from(crop, dog_key).filter(ImageFilter.MedianFilter(5))
    m = m.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    m = largest_components(m, 900).filter(ImageFilter.GaussianBlur(0.8))
    look = crop.convert("RGBA")
    look.putalpha(m)
    look = trim(look)
    s2 = TEAM_WIDTH / look.width
    look = scale(look, s2)
    save(
        "team",
        "team_lookback",
        look,
        "smooth",
        reuse="DRAFT keyed from the gameplay concept (rough leaders, lower camera); replace "
        "with prompt team_lookback_v1. Shown ~1 s now and then; align ring anchor with team_run",
        anchor_ring=(round((632 - box[0]) * s2), look.height - 2),
    )

    alias(
        "team",
        "team_stop",
        "team_run",
        "placeholder: frozen team_run, no bob. Replace with one standing-team render "
        "(prompt team_stop_v1) at the same size and ring anchor",
    )


# -------------------------------------------------------------------------- sled
def build_sled(gameplay):
    box = (60, 1040, 1200, 1254)
    crop = gameplay.crop(box)
    cx, cy = 620 - box[0], 1330 - box[1]

    def in_band(x, y):
        o = ((x - cx) / 560) ** 2 + ((y - cy) / 262) ** 2
        i = ((x - cx) / 500) ** 2 + ((y - cy) / 225) ** 2
        return o <= 1.0 and i >= 1.0

    def keep(r, g, b, x, y):
        if x + box[0] > 1060 and y + box[1] < 1140:  # concept HUD minimap
            return False
        return in_band(x, y) or r - b > 18 or max(r, g, b) < 120

    m = mask_from(crop, keep).filter(ImageFilter.MedianFilter(5))
    m = largest_components(m, 400).filter(ImageFilter.GaussianBlur(0.7))
    bow = crop.convert("RGBA")
    bow.putalpha(m)
    save(
        "sled",
        "sled_bow",
        scale(trim(bow), BG_SCALE),
        "smooth",
        reuse="fixed at the bottom edge; shake 1-2 px with bumps; heat glow drawn on top",
        pivot="bottom-centre",
    )


# ---------------------------------------------------------------------------- fx
def radial(size, color, power=2.0, alpha=255):
    w, h = size
    im = Image.new("RGBA", size, color + (0,))
    px = im.load()
    for y in range(h):
        for x in range(w):
            dx, dy = (x - w / 2 + 0.5) / (w / 2), (y - h / 2 + 0.5) / (h / 2)
            t = max(0.0, 1 - math.hypot(dx, dy))
            px[x, y] = color + (int(alpha * t**power),)
    return im


def build_fx():
    import random

    rnd = random.Random(42)
    white = (255, 255, 255)
    note = "white: tint at runtime (cold blue in shade, amber near lamps)"

    puff = Image.new("RGBA", (40, 40), white + (0,))
    for _ in range(14):
        r = rnd.uniform(5, 11)
        blob = radial((int(r * 2), int(r * 2)), white, 1.6, rnd.randint(90, 170))
        puff.alpha_composite(blob, (int(20 - r + rnd.uniform(-8, 8)), int(20 - r + rnd.uniform(-8, 8))))
    save("fx", "snow_puff", puff, "smooth", reuse=note + "; scale 0.5-2x for kick-up and landing")

    spray = Image.new("RGBA", (72, 48), white + (0,))
    d = ImageDraw.Draw(spray)
    for _ in range(260):
        t = rnd.random()
        a = rnd.uniform(-1.1, 1.1) * (0.4 + t)
        x = 36 + math.sin(a) * 40 * t
        y = 46 - math.cos(a) * 44 * t
        r = rnd.choice((0.6, 0.8, 1.0, 1.4))
        d.ellipse((x - r, y - r, x + r, y + r), fill=white + (int(230 * (1 - t * 0.7)),))
    spray = spray.filter(ImageFilter.GaussianBlur(0.4))
    save("fx", "paw_spray", spray, "smooth", reuse=note + "; emitted under the team at stride rate")

    save("fx", "snowflake_soft", radial((10, 10), white, 1.2), "smooth", reuse=note)
    streak = Image.new("RGBA", (5, 28), white + (0,))
    sp = streak.load()
    for y in range(28):
        for x in range(5):
            sp[x, y] = white + (int(220 * (y / 27) * max(0, 1 - abs(x - 2) / 2.5)),)
    save(
        "fx",
        "snow_streak",
        streak,
        "smooth",
        reuse=note + "; rotate toward the vanishing point; count and length grow with heat",
    )
    save(
        "fx",
        "lamp_glow",
        radial((72, 72), (255, 196, 120), 2.2, 230),
        "smooth",
        reuse="warm halo on every lamp head; flicker by alpha/scale",
    )
    save(
        "fx",
        "light_pool",
        radial((120, 36), (255, 190, 120), 1.5, 120),
        "smooth",
        reuse="warm pool on the snow under lamps; scale by depth",
    )
    save(
        "fx",
        "shadow_soft",
        radial((96, 24), (30, 40, 90), 1.3, 150),
        "smooth",
        reuse="under team and props; stretch to fit",
    )

    frost = Image.new("L", (128, 128), 0)
    fd = ImageDraw.Draw(frost)
    for _ in range(90):  # branching ice needles grown from the corner
        x, y = rnd.uniform(0, 30), rnd.uniform(0, 30)
        ang = rnd.uniform(0.1, 1.45)
        for _ in range(rnd.randint(3, 7)):
            nx, ny = x + math.cos(ang) * rnd.uniform(6, 18), y + math.sin(ang) * rnd.uniform(6, 18)
            fd.line((x, y, nx, ny), fill=rnd.randint(120, 230), width=1)
            x, y, ang = nx, ny, ang + rnd.uniform(-0.6, 0.6)
    fog = Image.new("L", (128, 128), 0)
    gd = ImageDraw.Draw(fog)
    for r in range(128, 0, -4):
        gd.ellipse((-r, -r, r, r), fill=int(170 * (1 - r / 128) ** 1.5))
    frost = Image.eval(Image.merge("L", [frost]), lambda v: v)
    alpha = Image.composite(Image.new("L", frost.size, 255), fog, frost)
    alpha = Image.eval(alpha, lambda v: v)
    vign = radial((256, 256), (0, 0, 0), 1.0).getchannel("A").crop((0, 0, 128, 128))
    alpha = Image.eval(
        Image.composite(alpha, Image.new("L", alpha.size, 0), Image.eval(vign, lambda v: 255 - v)), lambda v: v
    )
    frost_im = Image.new("RGBA", (128, 128), (225, 238, 255, 0))
    frost_im.putalpha(alpha.filter(ImageFilter.GaussianBlur(0.5)))
    save(
        "fx",
        "frost_corner",
        frost_im,
        "smooth",
        reuse="blizzard tier only: draw in 4 corners with flips, alpha follows heat",
    )


# ---------------------------------------------------------------------------- ui
def hud_components(hud):
    a = hud.getchannel("A").point(lambda v: 255 if v > 150 else 0)
    a = largest_components(a.resize((627, 627)), 2000)
    boxes = []
    from collections import deque

    w, h = a.size
    px = a.load()
    seen = set()
    for y in range(h):
        for x in range(w):
            if px[x, y] and (x, y) not in seen:
                q, xs, ys = deque([(x, y)]), [], []
                seen.add((x, y))
                while q:
                    cx, cy = q.popleft()
                    xs.append(cx)
                    ys.append(cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h and px[nx, ny] and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            q.append((nx, ny))
                boxes.append((min(xs) * 2, min(ys) * 2, max(xs) * 2 + 2, max(ys) * 2 + 2))
    boxes.sort(key=lambda b: (b[1] // 200, b[0]))
    return boxes  # score pill, lap pill, minimap panel, pause


def text_sprite(text, size, bold=True, shadow=True):
    f = font(size, bold)
    left, top, right, bottom = f.getbbox(text)
    pad = 4
    im = Image.new("RGBA", (right - left + pad * 2, bottom - top + pad * 2), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((pad - left, pad - top + 1), text, font=f, fill=(10, 20, 45, 170))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(1.6)))
    ImageDraw.Draw(im).text((pad - left, pad - top), text, font=f, fill=(255, 255, 255, 255))
    return im


def track_points():
    pts, x, z, h = [], 0.0, 0.0, 0.0
    for length, turn in SEGMENTS:
        k = math.radians(turn) / length
        for _ in range(int(length)):
            pts.append((x, z))
            h += k
            x += math.sin(h)
            z += math.cos(h)
    n = len(pts)
    return [(px - x * i / n, pz - z * i / n) for i, (px, pz) in enumerate(pts)]


def build_ui(hud):
    score, lap, panel, pause = hud_components(hud)
    ui_scale = 30 / (score[3] - score[1])  # pills are 30 px tall on screen

    pill = hud.crop(score)
    # Cut the cap just left of the baked-in digits so the stretched middle
    # column is clean glass: first column with near-white text pixels, minus a gap.
    ppx = pill.load()
    text_x = next(
        x
        for x in range(pill.width)
        if any(
            min(ppx[x, y][:3]) > 235 and ppx[x, y][3] > 200 for y in range(pill.height * 3 // 10, pill.height * 7 // 10)
        )
    )
    cap_w = text_x - 16
    save(
        "ui",
        "pill_cap",
        scale(pill.crop((0, 0, cap_w, pill.height)), ui_scale),
        "smooth",
        reuse="left cap; right cap = flipped; middle = ui/pill_mid stretched",
    )
    save(
        "ui",
        "pill_mid",
        scale(pill.crop((cap_w, 0, cap_w + 8, pill.height)), ui_scale),
        "smooth",
        reuse="stretch horizontally; score, lap, timers, prompts",
    )

    pan = hud.crop(panel)
    c = int(pan.width * 0.16)
    save(
        "ui",
        "panel_corner",
        scale(pan.crop((0, 0, c, c)), ui_scale),
        "smooth",
        reuse="9-slice corner, flip for the other three",
    )
    save(
        "ui",
        "panel_edge",
        scale(pan.crop((c, 0, c + 8, c)), ui_scale),
        "smooth",
        reuse="9-slice top edge, stretch; rotate/flip for the other edges",
    )
    fill = pan.crop((pan.width // 2 - 8, c + 2, pan.width // 2 + 8, c + 18))
    save(
        "ui",
        "panel_fill",
        fill.resize((8, 8), LANCZOS),
        "smooth",
        reuse="9-slice centre, stretch; minimap, pause, result, mode cards",
    )
    save("ui", "btn_pause", scale(hud.crop(pause), ui_scale * 1.1), "smooth")

    dot = hud.crop((430, 945, 500, 1015))
    ring = Image.new("L", dot.size, 0)  # keep the glowing dot, drop the panel glass
    ImageDraw.Draw(ring).ellipse((10, 10, 60, 60), fill=255)
    dot.putalpha(Image.composite(dot.getchannel("A"), ring, ring.filter(ImageFilter.GaussianBlur(4))))
    save("ui", "map_dot", scale(dot, ui_scale * 1.2), "smooth", reuse="minimap position; tint per player")

    pts = track_points()
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(zs) - min(zs))
    size = 64
    k = (size - 10) / span
    mx, mz = (max(xs) + min(xs)) / 2, (max(zs) + min(zs)) / 2
    path = [(size / 2 + (x - mx) * k, size / 2 - (z - mz) * k) for x, z in pts]
    line = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    ImageDraw.Draw(line).line(path + [path[0]], fill=(255, 255, 255, 255), width=2, joint="curve")
    glow = line.filter(ImageFilter.GaussianBlur(1.5))
    track = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    track.alpha_composite(glow)
    track.alpha_composite(line)
    save(
        "ui",
        "minimap_track",
        track,
        "smooth",
        reuse="generated from components/app_game/sled_track.c segments; regenerate if the track changes",
        track_to_px={"scale": k, "centre_m": [mx, mz]},
    )

    # Glyphs: one OFL font (Source Han Sans CN) for digits and Chinese.
    for tag, size in (("s", 22), ("l", 56)):
        for ch, nm in zip("0123456789:./%", [*"0123456789", "colon", "dot", "slash", "pct"]):
            save(
                "font",
                f"glyph_{tag}_{nm}",
                text_sprite(ch, size),
                "smooth",
                reuse=f"digit glyph, {size} px; white, tint at runtime",
            )
    labels = {
        "title_cn": ("哈士奇雪橇赛", 40),
        "title_en": ("HUSKY SLED RACE", 14),
        "tier_breeze": ("微风", 16),
        "tier_snow": ("风雪", 16),
        "tier_blizzard": ("暴风雪", 16),
        "lap": ("LAP", 12),
        "final_lap": ("最后一圈", 30),
        "go": ("GO!", 64),
        "finish": ("完赛", 28),
        "new_record": ("新纪录", 18),
        "score": ("分数", 14),
        "total_time": ("总时间", 16),
        "best_lap": ("最佳圈速", 16),
        "max_heat": ("最高热情", 16),
        "paused": ("暂停", 26),
        "mode_tilt": ("体感", 20),
        "mode_keys": ("按键", 20),
        "mode_tilt_sub": ("倾斜转向", 12),
        "mode_keys_sub": ("左右键转向", 12),
        "hint_start": ("左键切换  右键出发", 13),
        "hint_retry": ("右键 再跑一次", 14),
        "hint_resume": ("右键 继续  左键 退出", 13),
        "deep_snow": ("深雪!", 18),
    }
    for name, (text, size) in labels.items():
        save(
            "text",
            name,
            text_sprite(text, size, bold=size >= 16),
            "smooth",
            reuse="white; tint at runtime (amber for highlights)",
            text=text,
        )

    icon = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
    d = ImageDraw.Draw(icon)
    for i in range(3):
        a = math.pi * i / 3 + math.pi / 2
        dx, dy = math.cos(a) * 7.5, math.sin(a) * 7.5
        d.line((9 - dx, 9 - dy, 9 + dx, 9 + dy), fill=(255, 255, 255, 255), width=2)
    save("ui", "icon_snowflake", icon, "smooth", reuse="heat tier pips x3; tint dim/lit")

    tilt = Image.new("RGBA", (36, 36), (0, 0, 0, 0))
    d = ImageDraw.Draw(tilt)
    d.rounded_rectangle((11, 6, 25, 30), 3, outline=(255, 255, 255, 255), width=2)
    d.arc((2, 4, 34, 36), 200, 250, fill=(255, 255, 255, 255), width=2)
    d.arc((2, 4, 34, 36), 290, 340, fill=(255, 255, 255, 255), width=2)
    save("ui", "icon_tilt", tilt.rotate(-12, resample=Image.BICUBIC), "smooth", reuse="mode card")
    keys = Image.new("RGBA", (36, 36), (0, 0, 0, 0))
    d = ImageDraw.Draw(keys)
    for x0 in (3, 20):
        d.rounded_rectangle((x0, 10, x0 + 13, 26), 4, outline=(255, 255, 255, 255), width=2)
    save("ui", "icon_keys", keys, "smooth", reuse="mode card")

    grad = Image.new("RGBA", (8, 96))
    stops = [(0.0, (120, 190, 255)), (0.55, AMBER), (1.0, (255, 96, 120))]
    for y in range(96):
        t = 1 - y / 95
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t <= t1:
                f = (t - t0) / (t1 - t0)
                col = tuple(int(a + (b - a) * f) for a, b in zip(c0, c1))
                break
        for x in range(8):
            grad.putpixel((x, y), col + (255,))
    save(
        "ui",
        "heat_gradient",
        grad,
        "opaque",
        reuse="heat colour ramp (cold blue > amber > hot pink); sample a row or clip-stretch as a bar",
    )


def main():
    bg = Image.open(SRC / "snow_forest_background_v1.png").convert("RGB")
    cutout = Image.open(SRC / "six_huskies_cutout_v1.png").convert("RGBA")
    gameplay = Image.open(SRC / "joyful_sprint_gameplay_v1.png").convert("RGB")
    hud = Image.open(SRC / "minimal_hud_cutouts_v1.png").convert("RGBA")
    build_environment(bg)
    build_team(cutout, gameplay)
    build_sled(gameplay)
    build_fx()
    build_ui(hud)
    total = sum(e["bytes_rgb565"] for e in manifest)
    (OUT / "asset_library.json").write_text(
        json.dumps(
            {
                "schema": "husky-asset-library/v1",
                "screen": SCREEN,
                "sources": sorted(p.name for p in SRC.glob("*_v1.png")),
                "font": "Source Han Sans CN (SIL OFL 1.1)",
                "total_bytes_rgb565": total,
                "assets": manifest,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n"
    )
    print(f"{len(manifest)} assets, {total / 1024:.0f} KiB as RGB565(+A8)")


if __name__ == "__main__":
    main()
