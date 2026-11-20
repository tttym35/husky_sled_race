#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render the v1 UI review set for Husky Sled Race.

Outputs 480x480 HUD mock-ups and transparent UI element PNGs. The background
plate is a crop of the reference video and is for internal layout review only;
it must never ship. Real plates come from the AI image prompts.

Usage: python make_ui_review.py <reference_frame.png> <out_dir>
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W = H = 480
NAVY = (14, 26, 56)
WHITE = (255, 255, 255)
AMBER = (255, 184, 92)
COLD = (120, 190, 255)
HOT = (255, 96, 120)

FONT_NUM = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"
FONT_UI = "/System/Library/Fonts/SFNSRounded.ttf"
FONT_CN = "/System/Library/Fonts/Hiragino Sans GB.ttc"

# Same segment table as components/app_game/sled_track.c (length, turn_deg).
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

HEAT_TIERS = ["微风", "风雪", "暴风雪"]


def font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


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


def heat_color(t):
    """Cold blue -> warm amber -> hot pink as heat rises."""
    stops = [(0.0, COLD), (0.55, AMBER), (1.0, HOT)]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(int(a + (b - a) * f) for a, b in zip(c0, c1))
    return HOT


def plate(frame_path):
    im = Image.open(frame_path).convert("RGB")
    w, _ = im.size
    top = int(w * 0.52)  # skip status bar, keep sky, lamps, trees and dogs
    im = im.crop((0, top, w, top + w)).resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.text((W - 6, H - 4), "REF PLATE, NOT FOR SHIP", font=font(FONT_UI, 9), fill=(255, 255, 255, 120), anchor="rd")
    return im.convert("RGBA")


def glass(base, box, radius, alpha=150):
    """Frosted navy capsule: blur what is underneath, tint, thin rim."""
    x0, y0, x1, y1 = box
    region = base.crop(box).filter(ImageFilter.GaussianBlur(6))
    tint = Image.new("RGBA", region.size, NAVY + (alpha,))
    region = Image.alpha_composite(region, tint)
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, x1 - x0 - 1, y1 - y0 - 1), radius, fill=255)
    base.paste(region, (x0, y0), mask)
    ImageDraw.Draw(base).rounded_rectangle(box, radius, outline=(255, 255, 255, 60), width=1)


def pill_text(base, box, label, value, value_size=22):
    glass(base, box, (box[3] - box[1]) // 2)
    d = ImageDraw.Draw(base)
    cy = (box[1] + box[3]) // 2
    x = box[0] + 12
    if label:
        d.text((x, cy), label, font=font(FONT_UI, 11), fill=(200, 215, 240), anchor="lm")
        x += d.textlength(label, font=font(FONT_UI, 11)) + 6
    d.text((x, cy + 1), value, font=font(FONT_NUM, value_size), fill=WHITE, anchor="lm")


def minimap(base, center, size, progress, glass_bg=True):
    pts = track_points()
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(zs) - min(zs))
    s = (size - 16) / span
    cx = (max(xs) + min(xs)) / 2
    cz = (max(zs) + min(zs)) / 2
    mapped = [(center[0] + (x - cx) * s, center[1] - (z - cz) * s) for x, z in pts]
    if glass_bg:
        r = size // 2 + 2
        glass(base, (center[0] - r, center[1] - r, center[0] + r, center[1] + r), r, 110)
    d = ImageDraw.Draw(base)
    d.line(mapped + [mapped[0]], fill=(255, 255, 255, 220), width=2, joint="curve")
    sx, sy = mapped[0]
    d.line((sx - 4, sy, sx + 4, sy), fill=WHITE, width=2)  # start line
    px, py = mapped[int(progress * (len(mapped) - 1))]
    d.ellipse((px - 7, py - 7, px + 7, py + 7), fill=AMBER + (70,))
    d.ellipse((px - 4, py - 4, px + 4, py + 4), fill=AMBER, outline=WHITE)


def snow_streaks(base, heat, seed=7):
    """Rough preview of the 'snow in your face' intensity, edges only."""
    import random

    rnd = random.Random(seed)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    vx, vy = W / 2, H * 0.42
    for _ in range(int(40 + 260 * heat)):
        a = rnd.uniform(0, 2 * math.pi)
        r0 = rnd.uniform(140, 330)
        x0, y0 = vx + math.cos(a) * r0, vy + math.sin(a) * r0
        ln = 6 + 34 * heat * rnd.random()
        x1, y1 = x0 + math.cos(a) * ln, y0 + math.sin(a) * ln
        d.line((x0, y0, x1, y1), fill=(255, 255, 255, rnd.randint(110, 230)), width=rnd.choice((1, 1, 2)))
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.6)))


def heat_bar_vertical(base, x, y0, y1, heat):
    glass(base, (x - 9, y0 - 8, x + 9, y1 + 8), 9, 120)
    d = ImageDraw.Draw(base)
    h = y1 - y0
    fill_top = int(y1 - h * heat)
    for y in range(fill_top, y1):
        t = (y1 - y) / h
        d.line((x - 4, y, x + 4, y), fill=heat_color(t))
    for i in (1, 2):  # tier ticks
        ty = int(y1 - h * i / 3)
        d.line((x - 8, ty, x + 8, ty), fill=(255, 255, 255, 140), width=1)
    tier = min(2, int(heat * 3))
    d.text(
        (x + 14, fill_top),
        HEAT_TIERS[tier],
        font=font(FONT_CN, 13),
        fill=heat_color(heat),
        anchor="lm",
        stroke_width=2,
        stroke_fill=NAVY,
    )


def heat_arc_top(base, heat):
    cx, cy, r = W // 2, 118, 92
    a0, a1 = 215, 325
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.arc((cx - r, cy - r, cx + r, cy + r), a0, a1, fill=(14, 26, 56, 150), width=12)
    steps = 60
    for i in range(int(steps * heat)):
        t = i / steps
        a = a0 + (a1 - a0) * t
        d.arc((cx - r, cy - r, cx + r, cy + r), a, a + (a1 - a0) / steps + 0.6, fill=heat_color(t) + (255,), width=8)
    glow = layer.filter(ImageFilter.GaussianBlur(4))
    base.alpha_composite(glow)
    base.alpha_composite(layer)
    d = ImageDraw.Draw(base)
    tier = min(2, int(heat * 3))
    d.text(
        (cx, 50),
        HEAT_TIERS[tier],
        font=font(FONT_CN, 14),
        fill=heat_color(heat),
        anchor="mm",
        stroke_width=2,
        stroke_fill=NAVY,
    )


def snowflake(d, x, y, r, color):
    for k in range(3):
        a = math.pi * k / 3
        dx, dy = math.cos(a) * r, math.sin(a) * r
        d.line((x - dx, y - dy, x + dx, y + dy), fill=color, width=2)


def sled_bow(base):
    """Runtime-drawn wooden handlebar stand-in (cream bow along the bottom)."""
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    box = (W // 2 - 250, 520 - 120, W // 2 + 250, 520 + 120)
    d.arc(box, 196, 344, fill=(40, 30, 30, 120), width=20)
    d.arc(box, 196, 344, fill=(222, 206, 176, 255), width=14)
    d.arc((box[0] + 4, box[1] + 3, box[2] - 4, box[3]), 205, 335, fill=(250, 240, 220, 200), width=3)
    base.alpha_composite(layer)


def heat_bow(base, heat):
    """Heat drawn on the sled bow itself: a warm glow line along the handlebar."""
    sled_bow(base)
    cx, cy, rx, ry = W // 2, 520, 250, 138
    a0, a1 = 200, 340
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    box = (cx - rx, cy - ry, cx + rx, cy + ry)
    d.arc(box, a0, a1, fill=(14, 26, 56, 140), width=10)
    steps = 80
    for i in range(int(steps * heat)):
        t = i / steps
        a = a0 + (a1 - a0) * t
        d.arc(box, a, a + (a1 - a0) / steps + 0.6, fill=heat_color(t) + (255,), width=6)
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(5)))
    base.alpha_composite(layer)
    d = ImageDraw.Draw(base)
    tier = min(2, int(heat * 3))
    for i in range(3):  # three snowflake pips for the tier
        snowflake(d, W // 2 - 24 + i * 24, 446, 7, heat_color(heat) if i <= tier else (255, 255, 255, 90))


def layout_a(frame, heat):
    """A: corner pills + left heat bar + minimap bottom-right."""
    im = plate(frame)
    snow_streaks(im, heat)
    sled_bow(im)
    pill_text(im, (14, 14, 118, 44), None, "01280")
    pill_text(im, (W - 100, 14, W - 14, 44), "LAP", "2/3")
    heat_bar_vertical(im, 26, 150, 340, heat)
    minimap(im, (W - 56, H - 64), 84, 0.38)
    return im


def layout_b(frame, heat):
    """B: top-centre heat arc with score inside, small lap + minimap."""
    im = plate(frame)
    snow_streaks(im, heat)
    sled_bow(im)
    heat_arc_top(im, heat)
    d = ImageDraw.Draw(im)
    d.text((W // 2, 84), "01280", font=font(FONT_NUM, 30), fill=WHITE, anchor="mm", stroke_width=2, stroke_fill=NAVY)
    pill_text(im, (14, 14, 96, 42), "LAP", "2/3", 20)
    minimap(im, (W - 50, 52), 72, 0.38)
    return im


def layout_c(frame, heat):
    """C: diegetic. Heat glows along the sled bow; top is score + lap only."""
    im = plate(frame)
    snow_streaks(im, heat)
    heat_bow(im, heat)
    d = ImageDraw.Draw(im)
    d.text((18, 16), "01280", font=font(FONT_NUM, 26), fill=WHITE, anchor="la", stroke_width=2, stroke_fill=NAVY)
    d.text((W - 18, 18), "LAP 2/3", font=font(FONT_NUM, 20), fill=WHITE, anchor="ra", stroke_width=2, stroke_fill=NAVY)
    minimap(im, (W - 44, 84), 60, 0.38, glass_bg=False)
    return im


def result_card(frame):
    im = plate(frame).filter(ImageFilter.GaussianBlur(5))
    glass(im, (60, 70, 420, 410), 22, 175)
    d = ImageDraw.Draw(im)
    d.text((W // 2, 108), "完赛", font=font(FONT_CN, 26), fill=WHITE, anchor="mm")
    d.text((W // 2, 168), "03840", font=font(FONT_NUM, 54), fill=AMBER, anchor="mm")
    d.text((W // 2, 202), "SCORE", font=font(FONT_UI, 11), fill=(200, 215, 240), anchor="mm")
    rows = [("总时间", "2:41.6"), ("最佳圈速", "0:52.3"), ("最高热情", "暴风雪 96%")]
    for i, (k, v) in enumerate(rows):
        y = 246 + i * 38
        d.text((96, y), k, font=font(FONT_CN, 16), fill=(200, 215, 240), anchor="lm")
        d.text((384, y), v, font=font(FONT_CN, 18), fill=WHITE, anchor="rm")
        d.line((96, y + 19, 384, y + 19), fill=(255, 255, 255, 40))
    d.text((W // 2, 380), "右键 再跑一次", font=font(FONT_CN, 14), fill=(255, 255, 255, 200), anchor="mm")
    return im


def title_screen(frame):
    im = plate(frame)
    shade = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(H):
        sd.line((0, y, W, y), fill=(10, 18, 40, int(170 * max(0, 1 - y / 260))))
    im.alpha_composite(shade)
    d = ImageDraw.Draw(im)
    d.text(
        (W // 2, 74), "哈士奇雪橇赛", font=font(FONT_CN, 40), fill=WHITE, anchor="mm", stroke_width=2, stroke_fill=NAVY
    )
    d.text((W // 2, 112), "HUSKY SLED RACE", font=font(FONT_UI, 14), fill=AMBER, anchor="mm")
    # control mode picker
    for i, (name, sub) in enumerate((("体感", "倾斜转向"), ("按键", "左右键转向"))):
        x0 = 92 + i * 156
        box = (x0, 330, x0 + 140, 396)
        glass(im, box, 14, 175 if i == 0 else 110)
        if i == 0:
            d.rounded_rectangle(box, 14, outline=AMBER, width=2)
        d.text((x0 + 70, 352), name, font=font(FONT_CN, 20), fill=WHITE, anchor="mm")
        d.text((x0 + 70, 378), sub, font=font(FONT_CN, 12), fill=(200, 215, 240), anchor="mm")
    d.text((W // 2, 428), "左键切换  右键出发", font=font(FONT_CN, 13), fill=(255, 255, 255, 210), anchor="mm")
    return im


def element_sheet():
    """Transparent HUD parts on a checker so the alpha is readable in review."""
    sheet = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bg = Image.new("RGBA", (W, H), (60, 90, 140, 255))
    pill_text(bg, (20, 20, 124, 50), None, "01280")
    pill_text(bg, (140, 20, 226, 50), "LAP", "2/3")
    minimap(bg, (300, 70), 96, 0.38)
    for i, h in enumerate((0.15, 0.5, 0.92)):
        heat_bar_vertical(bg, 40 + i * 70, 140, 300, h)
    d = ImageDraw.Draw(bg)
    for i, txt in enumerate(("3", "2", "1")):
        d.text(
            (300 + i * 50, 200), txt, font=font(FONT_NUM, 60), fill=WHITE, anchor="mm", stroke_width=3, stroke_fill=NAVY
        )
    d.text((350, 280), "GO!", font=font(FONT_NUM, 64), fill=AMBER, anchor="mm", stroke_width=3, stroke_fill=NAVY)
    for i in range(3):
        x0 = 30 + i * 150
        d.rounded_rectangle((x0, 360, x0 + 130, 440), 12, fill=(14, 26, 56, 200))
        d.text((x0 + 65, 390), HEAT_TIERS[i], font=font(FONT_CN, 22), fill=heat_color((i + 0.8) / 3), anchor="mm")
        d.text((x0 + 65, 420), f"热情 {[20, 55, 90][i]}%", font=font(FONT_CN, 12), fill=(200, 215, 240), anchor="mm")
    sheet.alpha_composite(bg)
    return sheet


def main():
    frame, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    shots = {
        "hud_a_corner_bar.png": layout_a(frame, 0.72),
        "hud_b_top_arc.png": layout_b(frame, 0.72),
        "hud_c_sled_bow.png": layout_c(frame, 0.72),
        "screen_title_mode.png": title_screen(frame),
        "screen_result.png": result_card(frame),
        "ui_elements.png": element_sheet(),
    }
    for name, im in shots.items():
        im.convert("RGB").save(out / name)
    print("wrote", len(shots), "files to", out)


if __name__ == "__main__":
    main()
