"""Textures the pages draw charts with.

X-Ray has no "fill a rectangle" call. Every mod that draws a bar does the same thing:
a CUIStatic with a plain white texture, tinted with SetTextureColor and sized with
SetWndSize. So this ships one white pixel block for that, and the barometer.

The barometer is six images, not one. The first build shipped a single gauge with the
needle painted at a fixed angle - it looked like an instrument and read nothing, which is
worse than no instrument at all. There is one per Atmospherics weather cycle, and the page
picks the one matching what is actually outside, so the needle means something.

  python build_chart_parts.py --preview
  python build_chart_parts.py --write
"""
import argparse
import math
import os
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(os.path.dirname(HERE), "mods", "Seasons of the Zone")
TEXDIR = os.path.join(MOD, "gamedata", "textures")
DESCR = os.path.join(MOD, "gamedata", "configs", "ui", "textures_descr")
SCRATCH = os.path.join(tempfile.gettempdir(), "seasons_of_the_zone")

INK = (14, 17, 14, 255)
AMBER = (238, 196, 112, 255)

SIZE = 384
SS = 2

BANDS = [(0.00, 0.34, (116, 138, 158, 255)),
         (0.34, 0.68, AMBER),
         (0.68, 1.00, (226, 232, 220, 255))]

# Where the needle sits for each Atmospherics cycle. Storm hard left in the cold band,
# clear hard right in the fair band, the rest spread between - a barometer reads pressure,
# and low pressure is exactly what brings the storm.
CYCLE_AT = {
    "storm":  0.08,
    "rain":   0.24,
    "foggy":  0.42,
    "cloudy": 0.52,
    "partly": 0.72,
    "clear":  0.90,
}

A_START, A_END = 160.0, 380.0
R_OUT, R_IN, R_TICK = 234, 194, 185
CX = SIZE // 2
CY = SIZE // 2 + 62


def polar(cx, cy, deg, r):
    rad = math.radians(deg)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))


def gauge(fraction):
    s = SS
    im = Image.new("RGBA", (SIZE * s, SIZE * s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    cx, cy = CX * s, CY * s
    span = A_END - A_START

    def box(r):
        return [cx - r * s, cy - r * s, cx + r * s, cy + r * s]

    for f0, f1, col in BANDS:
        dr.arc(box((R_OUT + R_IN) / 2.0), A_START + span * f0, A_START + span * f1,
               fill=col, width=int((R_OUT - R_IN) * s))
    for r in (R_OUT, R_IN):
        dr.arc(box(r), A_START, A_END, fill=INK, width=int(2.5 * s))

    for i in range(11):
        f = i / 10.0
        a = A_START + span * f
        long_tick = i in (0, 10) or abs(f - 0.34) < 0.06 or abs(f - 0.68) < 0.06
        dr.line([polar(cx, cy, a, R_TICK * s),
                 polar(cx, cy, a, (R_TICK - (26 if long_tick else 14)) * s)],
                fill=(236, 240, 234, 235),
                width=int((4 if long_tick else 2.5) * s))

    def off(pt, deg, d):
        rad = math.radians(deg)
        return (pt[0] + d * s * math.cos(rad), pt[1] + d * s * math.sin(rad))

    at = A_START + span * fraction
    perp = at + 90.0
    tip = polar(cx, cy, at, (R_IN - 16) * s)
    hub = polar(cx, cy, at + 180.0, 34 * s)
    dr.polygon([off(hub, perp, 7.5), off(tip, perp, 1.8),
                off(tip, perp, -1.8), off(hub, perp, -7.5)],
               fill=(255, 255, 255, 250), outline=INK)
    dr.ellipse([cx - 11 * s, cy - 11 * s, cx + 11 * s, cy + 11 * s],
               fill=(252, 252, 252, 255), outline=INK, width=int(3 * s))
    return im.resize((SIZE, SIZE), Image.LANCZOS)


def white_block():
    """Tinted with SetTextureColor to draw every bar on both pages."""
    return Image.new("RGBA", (8, 8), (255, 255, 255, 255))


ENTRY = ('\t<file name="%s">\n\t\t<texture id="%s" x="0" y="0" '
         'width="%d" height="%d" />\n\t</file>\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    items = [("ui_sotz_px", "sotz_px", 8, white_block())]
    for cycle, f in sorted(CYCLE_AT.items()):
        items.append(("ui_sotz_gauge_" + cycle, "sotz_gauge_" + cycle, SIZE, gauge(f)))

    if a.write:
        os.makedirs(TEXDIR, exist_ok=True)
        os.makedirs(DESCR, exist_ok=True)
        for stem, _, _, im in items:
            im.save(os.path.join(TEXDIR, stem + ".dds"), "DDS")
            print("  %s.dds" % stem)
        body = "".join(ENTRY % (stem, idn, n, n) for stem, idn, n, _ in items)
        p = os.path.join(DESCR, "ui_sotz_charts.xml")
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("<w>\n" + body + "</w>\n")
        print("  textures_descr/ui_sotz_charts.xml  (%d declared)" % len(items))
        return 0

    cells = [im for _, _, _, im in items if im.width > 8]
    w = 150
    sh = Image.new("RGBA", (len(cells) * w, w + 4), (22, 26, 24, 255))
    for i, im in enumerate(cells):
        sh.paste(im.resize((w, w), Image.LANCZOS), (i * w, 2), im.resize((w, w),
                 Image.LANCZOS))
    os.makedirs(SCRATCH, exist_ok=True)
    p = os.path.join(SCRATCH, "gauge_preview.png")
    sh.save(p)
    print("  preview -> %s" % p)
    print("  order: " + ", ".join(sorted(CYCLE_AT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
