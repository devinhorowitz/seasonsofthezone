"""Render the app icon for the Forecast PDA page.

A barometer: a 220-degree arc banded storm / change / fair, with the same tapered white
needle and hub the year dial uses. The two icons sit next to each other in the Mod App
Creator launcher, so they share a drawing language on purpose - circular, white needle,
dark outline - while reading as different instruments at a glance.

Unlike the dial there is only one frame. The needle is fixed: it is an icon, not a
readout, and an icon that changed every few minutes would just be noise in the launcher.

Usage:
  python build_forecast_icon.py --preview     a PNG to look at
  python build_forecast_icon.py --write       the shipped .dds
"""
import argparse
import math
import os
import tempfile

from PIL import Image, ImageDraw

MOD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "mods", "Seasons of the Zone")
TEXDIR = os.path.join(MOD, "gamedata", "textures")
SCRATCH = os.path.join(tempfile.gettempdir(), "seasons_of_the_zone")
NAME = "ui_seasons_forecast"

SIZE = 512                  # drawing canvas
TEX = 384                   # saved texture, same as the dial
SS = 2                      # supersample factor
CX = SIZE // 2
# A 220-degree sweep centred on 12 o'clock puts the arc entirely in the upper half, so
# the hub sits below the middle of the frame to centre the instrument rather than the
# circle it is part of.
CY = SIZE // 2 + 62

# the sweep, in PIL's degrees (0 = 3 o'clock, growing clockwise)
A_START, A_END = 160.0, 380.0

R_OUT = 234
R_IN = 194
R_TICK = 185

# storm / change / fair. The amber is the page's heading color; the flanks are a cold
# grey-blue and a warm off-white, so the band reads without needing a legend.
BANDS = [(0.00, 0.34, (116, 138, 158, 255)),
         (0.34, 0.68, (238, 196, 112, 255)),
         (0.68, 1.00, (226, 232, 220, 255))]

INK = (14, 17, 14, 255)


def polar(cx, cy, deg, r):
    rad = math.radians(deg)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))


def render():
    s = SS
    im = Image.new("RGBA", (SIZE * s, SIZE * s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    cx, cy = CX * s, CY * s
    span = A_END - A_START

    def box(r):
        return [cx - r * s, cy - r * s, cx + r * s, cy + r * s]

    # the banded arc, drawn as three thick pieces
    for f0, f1, col in BANDS:
        dr.arc(box((R_OUT + R_IN) / 2.0), A_START + span * f0, A_START + span * f1,
               fill=col, width=int((R_OUT - R_IN) * s))

    # a dark rim on both edges so the bands read against any panel color
    for r in (R_OUT, R_IN):
        dr.arc(box(r), A_START, A_END, fill=INK, width=int(2.5 * s))

    # ticks: eleven, with the band joins doubled in length
    for i in range(11):
        f = i / 10.0
        a = A_START + span * f
        long_tick = i in (0, 10) or abs(f - 0.34) < 0.06 or abs(f - 0.68) < 0.06
        r1 = R_TICK - (26 if long_tick else 14)
        p0 = polar(cx, cy, a, R_TICK * s)
        p1 = polar(cx, cy, a, r1 * s)
        dr.line([p0, p1], fill=(236, 240, 234, 235), width=int((4 if long_tick else 2.5) * s))

    # the needle, tapered and outlined exactly as the year dial draws its hand
    def offset(pt, deg, d):
        rad = math.radians(deg)
        return (pt[0] + d * s * math.cos(rad), pt[1] + d * s * math.sin(rad))

    point_at = A_START + span * 0.60          # sitting in "change", leaning fair
    perp = point_at + 90.0
    tip = polar(cx, cy, point_at, (R_IN - 16) * s)
    hub = polar(cx, cy, point_at + 180.0, 34 * s)
    blade = [offset(hub, perp, 7.5), offset(tip, perp, 1.8),
             offset(tip, perp, -1.8), offset(hub, perp, -7.5)]
    dr.polygon(blade, fill=(255, 255, 255, 250), outline=INK)
    dr.ellipse([cx - 11 * s, cy - 11 * s, cx + 11 * s, cy + 11 * s],
               fill=(252, 252, 252, 255), outline=INK, width=int(3 * s))

    return im.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    im = render()

    if a.write:
        os.makedirs(TEXDIR, exist_ok=True)
        out = os.path.join(TEXDIR, NAME + ".dds")
        im.convert("RGBA").resize((TEX, TEX), Image.LANCZOS).save(out, "DDS")
        print("  wrote %s  (%dx%d)" % (out, TEX, TEX))
        return

    os.makedirs(SCRATCH, exist_ok=True)
    out = os.path.join(SCRATCH, "forecast_preview.png")
    bg = Image.new("RGBA", im.size, (17, 30, 19, 255))      # roughly the PDA panel
    Image.alpha_composite(bg, im).save(out)
    print("  preview -> %s" % out)


if __name__ == "__main__":
    main()
