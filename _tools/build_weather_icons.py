"""Weather condition glyphs for the forecast page.

The page could already tell you it was a storm turning to rain in three hours - in words,
in a table, four rows down. These say it in the first half second: the sky you are under,
an arrow, the sky you are getting.

Drawn rather than sourced, so they sit in the same palette as the dial, the barometer and
the ribbon: amber for anything the sun is in, cold grey-blue for anything that keeps you
indoors. One glyph per Atmospherics cycle, plus the arrow between them.

  python build_weather_icons.py --preview
  python build_weather_icons.py --write
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

N = 128
SS = 4

SUN = (238, 196, 112, 255)
SUN_DIM = (176, 148, 92, 255)
CLOUD_HI = (214, 220, 214, 255)
CLOUD_LO = (146, 156, 162, 255)
RAIN = (138, 172, 204, 255)
BOLT = (248, 214, 124, 255)
FOG = (176, 186, 184, 255)
ICE = (188, 216, 236, 255)


def canvas():
    im = Image.new("RGBA", (N * SS, N * SS), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def sun(dr, cx, cy, r, rays=True, col=SUN):
    s = SS
    if rays:
        for i in range(8):
            a = math.radians(i * 45.0)
            x0 = cx + math.cos(a) * (r + 7) * s
            y0 = cy + math.sin(a) * (r + 7) * s
            x1 = cx + math.cos(a) * (r + 17) * s
            y1 = cy + math.sin(a) * (r + 17) * s
            dr.line([(x0, y0), (x1, y1)], fill=col, width=int(4.5 * s))
    dr.ellipse([cx - r * s, cy - r * s, cx + r * s, cy + r * s], fill=col)


def cloud(dr, cx, cy, w, hi=CLOUD_HI, lo=CLOUD_LO):
    """Three lobes over a slab - reads as a cloud at 48px, which the pretty ones do not."""
    s = SS
    h = w * 0.62
    lobes = [(cx - w * 0.26 * s, cy - h * 0.06 * s, w * 0.30),
             (cx + w * 0.02 * s, cy - h * 0.26 * s, w * 0.38),
             (cx + w * 0.30 * s, cy + h * 0.00 * s, w * 0.28)]
    for lx, ly, lr in lobes:
        dr.ellipse([lx - lr * s, ly - lr * s, lx + lr * s, ly + lr * s], fill=hi)
    dr.rounded_rectangle([cx - w * 0.52 * s, cy + h * 0.02 * s,
                          cx + w * 0.56 * s, cy + h * 0.40 * s],
                         radius=int(h * 0.20 * s), fill=lo)


def g_clear():
    im, dr = canvas()
    sun(dr, N * SS // 2, N * SS // 2, 26)
    return im


def g_partly():
    im, dr = canvas()
    sun(dr, N * SS * 0.36, N * SS * 0.34, 20)
    cloud(dr, N * SS * 0.56, N * SS * 0.60, 44)
    return im


def g_cloudy():
    im, dr = canvas()
    cloud(dr, N * SS * 0.50, N * SS * 0.50, 52)
    return im


def g_foggy():
    im, dr = canvas()
    cloud(dr, N * SS * 0.50, N * SS * 0.40, 48, hi=(196, 204, 200, 235),
          lo=(150, 160, 160, 235))
    s = SS
    for i, y in enumerate((0.68, 0.79, 0.90)):
        inset = (8 + i * 6) * s
        dr.line([(N * s * 0.20 + inset, N * s * y), (N * s * 0.80 - inset, N * s * y)],
                fill=FOG, width=int(4.5 * s))
    return im


def g_rain():
    im, dr = canvas()
    cloud(dr, N * SS * 0.50, N * SS * 0.40, 48)
    s = SS
    for i, x in enumerate((0.33, 0.46, 0.59, 0.72)):
        y0 = N * s * (0.68 if i % 2 == 0 else 0.72)
        dr.line([(N * s * x, y0), (N * s * (x - 0.05), y0 + 20 * s)],
                fill=RAIN, width=int(4.5 * s))
    return im


def g_storm():
    im, dr = canvas()
    cloud(dr, N * SS * 0.50, N * SS * 0.38, 48, hi=(168, 178, 186, 255),
          lo=(104, 116, 128, 255))
    s = SS
    # a bolt, not a zigzag line: filled reads at any size
    pts = [(0.52, 0.58), (0.38, 0.82), (0.48, 0.82), (0.42, 1.00),
           (0.64, 0.74), (0.53, 0.74), (0.62, 0.58)]
    dr.polygon([(N * s * x, N * s * y) for x, y in pts], fill=BOLT)
    return im


def g_frost():
    """Shown when the real Zone's low dips below zero. A six-arm crystal, because a
    snowflake with any more detail than this turns to mush at 34px."""
    im, dr = canvas()
    s = SS
    cx = cy = N * s * 0.5
    r = 40 * s
    for i in range(6):
        a = math.radians(i * 60.0)
        x, y = cx + math.cos(a) * r, cy + math.sin(a) * r
        dr.line([(cx, cy), (x, y)], fill=ICE, width=int(5 * s))
        # one pair of barbs per arm, two thirds out
        bx, by = cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.62
        for d in (-38, 38):
            b = math.radians(i * 60.0 + d)
            dr.line([(bx, by), (bx + math.cos(b) * 13 * s, by + math.sin(b) * 13 * s)],
                    fill=ICE, width=int(4 * s))
    dr.ellipse([cx - 6 * s, cy - 6 * s, cx + 6 * s, cy + 6 * s], fill=ICE)
    return im


def g_arrow():
    """Between the two conditions. A chevron pair reads as motion; one does not."""
    im, dr = canvas()
    s = SS
    cy = N * s * 0.5
    for i, x in enumerate((0.30, 0.54)):
        col = SUN if i else SUN_DIM
        dr.line([(N * s * x, cy - 16 * s), (N * s * (x + 0.16), cy),
                 (N * s * x, cy + 16 * s)],
                fill=col, width=int(6 * s), joint="curve")
    return im


GLYPHS = [
    ("clear", g_clear), ("partly", g_partly), ("cloudy", g_cloudy),
    ("foggy", g_foggy), ("rain", g_rain), ("storm", g_storm),
    ("frost", g_frost), ("arrow", g_arrow),
]

ENTRY = ('\t<file name="%s">\n\t\t<texture id="%s" x="0" y="0" '
         'width="%d" height="%d" />\n\t</file>\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    made = [(k, fn().resize((N, N), Image.LANCZOS)) for k, fn in GLYPHS]

    if a.write:
        os.makedirs(TEXDIR, exist_ok=True)
        os.makedirs(DESCR, exist_ok=True)
        for k, im in made:
            im.save(os.path.join(TEXDIR, "ui_sotz_wx_" + k + ".dds"), "DDS")
            print("  ui_sotz_wx_%s.dds" % k)
        body = "".join(ENTRY % ("ui_sotz_wx_" + k, "sotz_wx_" + k, N, N)
                       for k, _ in made)
        p = os.path.join(DESCR, "ui_sotz_weather.xml")
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("<w>\n" + body + "</w>\n")
        print("  textures_descr/ui_sotz_weather.xml  (%d declared)" % len(made))
        return 0

    cell = 96
    sh = Image.new("RGBA", (len(made) * cell, cell + 4), (24, 29, 26, 255))
    for i, (_, im) in enumerate(made):
        r = im.resize((cell, cell), Image.LANCZOS)
        sh.paste(r, (i * cell, 2), r)
    os.makedirs(SCRATCH, exist_ok=True)
    p = os.path.join(SCRATCH, "wx_preview.png")
    sh.save(p)
    print("  preview -> %s" % p)
    print("  order: " + ", ".join(k for k, _ in made))
    return 0


if __name__ == "__main__":
    sys.exit(main())
