# SPDX-License-Identifier: Apache-2.0
"""Small Pillow-only helpers shared by the asset library scripts.

No numpy: the IDF Python used by native builds has none, and these scripts only
run on a developer host with the project .venv (Pillow).
"""

from collections import deque

from PIL import Image, ImageChops, ImageFilter

LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
NEAREST = getattr(Image, "Resampling", Image).NEAREST


def trim(im, pad=0):
    box = im.getchannel("A").getbbox()
    if not box:
        return im
    x0, y0, x1, y1 = box
    return im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)))


def scale(im, factor):
    return im.resize((max(1, round(im.width * factor)), max(1, round(im.height * factor))), LANCZOS)


def fit(im, w, h):
    f = min(w / im.width, h / im.height)
    return scale(im, f)


def geodesic_labels(mask, seeds):
    """Multi-source BFS inside a binary mask. Returns a label image (L, 0 = none,
    i + 1 = seed i). Fronts meet at narrow necks, which splits touching dogs."""
    w, h = mask.size
    m = mask.load()
    out = Image.new("L", mask.size, 0)
    o = out.load()
    q = deque()
    for i, (x, y) in enumerate(seeds):
        if not m[x, y]:
            raise ValueError(f"seed {i} at {(x, y)} is outside the mask")
        o[x, y] = i + 1
        q.append((x, y))
    while q:
        x, y = q.popleft()
        lab = o[x, y]
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and m[nx, ny] and not o[nx, ny]:
                o[nx, ny] = lab
                q.append((nx, ny))
    return out


def label_mask(labels, index):
    return labels.point(lambda v: 255 if v == index else 0)


def multiply_alpha(im, mask):
    out = im.copy()
    out.putalpha(ImageChops.multiply(im.getchannel("A"), mask))
    return out


def soft_mask(binary, grow=0, blur=0.0):
    m = binary
    if grow > 0:
        m = m.filter(ImageFilter.MaxFilter(grow * 2 + 1))
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur))
    return m


def mirror_tile(im):
    """2x2 mirror tiling: seamless in both directions."""
    w, h = im.size
    out = Image.new(im.mode, (w * 2, h * 2))
    flip = im.transpose(Image.FLIP_LEFT_RIGHT)
    out.paste(im, (0, 0))
    out.paste(flip, (w, 0))
    out.paste(im.transpose(Image.FLIP_TOP_BOTTOM), (0, h))
    out.paste(flip.transpose(Image.FLIP_TOP_BOTTOM), (w, h))
    return out


def checker(size, a=(205, 214, 230), b=(180, 192, 214), step=8):
    im = Image.new("RGB", size, a)
    px = im.load()
    for y in range(size[1]):
        for x in range(size[0]):
            if (x // step + y // step) % 2:
                px[x, y] = b
    return im
