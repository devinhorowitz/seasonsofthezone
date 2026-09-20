"""Render one colored header bar per season for the MCM mod list.

A texture rather than a colored label: MCM documents a desc's `clr` as {a,r,b,g} in one
place and uses it as {a,r,g,b} in another. The colors come from season_colors() in
build_season_dial.py, so the bars and the dial always agree.

The bar is full strength on the left and fades to the right, so it reads as a rule under
the heading rather than a block. The heading text is a separate row beneath it.
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_season_dial import season_colors          # noqa: E402

MOD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "mods", "Seasons of the Zone")
TEXDIR = os.path.join(MOD, "gamedata", "textures")

W, H = 256, 16            # drawn size; MCM scales it to the row
FADE_FROM = 0.45          # fraction of the width at full alpha before the fade


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
            a = a * a
        for y in range(H):
            v = 1.0 - 0.35 * abs((y / float(H - 1)) - 0.5) * 2.0    # slight vertical shading
            px[x, y] = (int(r * v), int(g * v), int(b * v), int(255 * a))
    return im


def main():
    cols = season_colors()
    os.makedirs(TEXDIR, exist_ok=True)
    for season, rgb in sorted(cols.items()):
        p = os.path.join(TEXDIR, "ui_season_hdr_%s.dds" % season)
        bar(rgb).save(p, "DDS")
        print("  %-14s rgb%-18s %-34s %5.1f KB"
              % (season, rgb, os.path.basename(p), os.path.getsize(p) / 1024.0))


main()
