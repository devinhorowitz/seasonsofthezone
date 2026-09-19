"""Render one coloured header bar per season for the MCM mod panel.

WHY A TEXTURE AND NOT A COLOURED LABEL
  MCM exposes `clr` on a desc row, but it documents that field as {a,r,b,g} in one place
  and consumes it as {a,r,g,b} elsewhere, so any hue is a coin flip between the two
  readings - which is why the calendar rows and the group headings are greyscale. An
  image row has no such ambiguity: the colour is in the file.

  This is the same mechanism the year dial already uses - a flat .dds in gamedata/textures
  referenced by bare name, uncompressed RGBA, non-power-of-two - so it needs no texture
  description XML and no new machinery.

COLOURS
  Taken from season_colours() in build_season_dial.py, which derives them from each
  season's actual r__color_grading values in seasons_of_the_zone.ltx rather than from
  taste. The dial and these bars therefore cannot drift apart: change a season's grade and
  both follow.

SHAPE
  A wide, short bar with the colour at full strength on the left fading out to the right,
  so it reads as a section rule rather than a block that fights the panel background. The
  heading text is a separate desc row directly beneath, because it carries live counts and
  sizes that cannot be baked into an image.
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_season_dial import season_colours          # noqa: E402

MOD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "mods", "Seasons of the Zone")
TEXDIR = os.path.join(MOD, "gamedata", "textures")

W, H = 256, 16            # drawn size; MCM scales it to the row size it is given
FADE_FROM = 0.45          # fraction of the width held at full alpha before fading


def bar(rgb):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = im.load()
    r, g, b = rgb
    for x in range(W):
        t = x / float(W - 1)
        if t <= FADE_FROM:
            a = 1.0
        else:
            a = 1.0 - (t - FADE_FROM) / (1.0 - FADE_FROM)
            a = a * a                       # ease out, so the tail is a long soft fade
        for y in range(H):
            # slight vertical shading keeps it from looking like a flat rectangle
            v = 1.0 - 0.35 * abs((y / float(H - 1)) - 0.5) * 2.0
            px[x, y] = (int(r * v), int(g * v), int(b * v), int(255 * a))
    return im


def main():
    cols = season_colours()
    os.makedirs(TEXDIR, exist_ok=True)
    for season, rgb in sorted(cols.items()):
        p = os.path.join(TEXDIR, "ui_season_hdr_%s.dds" % season)
        bar(rgb).save(p, "DDS")
        print("  %-14s rgb%-18s %-34s %5.1f KB"
              % (season, rgb, os.path.basename(p), os.path.getsize(p) / 1024.0))


main()
