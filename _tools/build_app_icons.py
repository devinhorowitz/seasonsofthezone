"""Render the Mod App Creator launcher icons, and the back button.

MAC builds each tile with Init3tButton + InitTexture, which is a FOUR-STATE button: the
engine appends _e / _h / _t / _d to the name and looks those up as declared texture ids.
A loose .dds does not satisfy that - the tile renders empty, which is exactly what this
mod shipped first. So each icon is a 512x512 sheet of 256x256 states, declared in a
texture_descr, laid out the way MAC's own ui_icon_apps.xml lays its out:

    (0,0) normal      (256,0) highlighted
    (0,256) pressed + disabled (MAC points both at this one)

The art is deliberately NOT the year dial. The dial carries season names and day counts
that are legible at 200px on the PDA page and complete mud at the ~48px a launcher tile
gets. These are the same instruments with everything unreadable stripped out: a ring with
the live season lit, and the barometer.

  python build_app_icons.py --preview    contact sheet to look at
  python build_app_icons.py --write      the .dds files and the texture_descr
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

CELL = 256
SHEET = 512
SS = 2

INK = (14, 17, 14, 255)
AMBER = (238, 196, 112, 255)

# The five seasons in calendar order with the arc colors the year dial uses, so the tile
# and the page agree at a glance.
SEASONS = [
    ("spring",      (122, 158, 104, 255)),
    ("summer",      (178, 166, 104, 255)),
    ("autumn",      (214, 170, 96, 255)),
    ("winter",      (150, 166, 182, 255)),
    ("winter_snow", (176, 182, 188, 255)),
]

# storm / change / fair, as on the forecast page's gauge
BANDS = [(0.00, 0.34, (116, 138, 158, 255)),
         (0.34, 0.68, AMBER),
         (0.68, 1.00, (226, 232, 220, 255))]


def polar(cx, cy, deg, r):
    rad = math.radians(deg)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))


def needle(dr, cx, cy, deg, length, s, width=5.0, hub_r=6.0):
    """The year dial's tapered blade, at icon scale."""
    def off(pt, d, dist):
        rad = math.radians(d)
        return (pt[0] + dist * s * math.cos(rad), pt[1] + dist * s * math.sin(rad))
    perp = deg + 90.0
    tip = polar(cx, cy, deg, length * s)
    hub = polar(cx, cy, deg + 180.0, 14 * s)
    blade = [off(hub, perp, width), off(tip, perp, 1.6),
             off(tip, perp, -1.6), off(hub, perp, -width)]
    dr.polygon(blade, fill=(255, 255, 255, 250), outline=INK)
    dr.ellipse([cx - hub_r * s, cy - hub_r * s, cx + hub_r * s, cy + hub_r * s],
               fill=(252, 252, 252, 255), outline=INK, width=int(2 * s))


def year_cell(active):
    """A ring of five season arcs with `active` lit and the hand on it. No text."""
    s = SS
    im = Image.new("RGBA", (CELL * s, CELL * s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    cx = cy = CELL * s // 2
    r_out, r_in = 106, 64

    # equal arcs: the tile says WHICH season, not how long it is - that is the page's job
    n = len(SEASONS)
    step = 360.0 / n
    idx = next((i for i, (k, _) in enumerate(SEASONS) if k == active), 0)
    for i, (key, col) in enumerate(SEASONS):
        a0 = -90.0 + i * step + 1.5
        a1 = -90.0 + (i + 1) * step - 1.5
        on = (i == idx)
        c = col if on else (col[0] // 4, col[1] // 4, col[2] // 4, 170)
        dr.arc([cx - ((r_out + r_in) // 2) * s, cy - ((r_out + r_in) // 2) * s,
                cx + ((r_out + r_in) // 2) * s, cy + ((r_out + r_in) // 2) * s],
               a0, a1, fill=c, width=int((r_out - r_in) * s))

    for r in (r_out, r_in):
        dr.ellipse([cx - r * s, cy - r * s, cx + r * s, cy + r * s],
                   outline=INK, width=int(2.5 * s))

    needle(dr, cx, cy, -90.0 + (idx + 0.5) * step, r_in - 6, s)
    return im.resize((CELL, CELL), Image.LANCZOS)


def forecast_cell():
    """The barometer, stripped of the fine ticks that vanish at tile size."""
    s = SS
    im = Image.new("RGBA", (CELL * s, CELL * s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    cx = CELL * s // 2
    cy = int(CELL * s * 0.62)
    a0, a1 = 160.0, 380.0
    span = a1 - a0
    r_out, r_in = 116, 84
    mid = (r_out + r_in) // 2

    for f0, f1, col in BANDS:
        dr.arc([cx - mid * s, cy - mid * s, cx + mid * s, cy + mid * s],
               a0 + span * f0, a0 + span * f1, fill=col, width=int((r_out - r_in) * s))
    for r in (r_out, r_in):
        dr.arc([cx - r * s, cy - r * s, cx + r * s, cy + r * s],
               a0, a1, fill=INK, width=int(2.5 * s))
    # three ticks only: the band joins
    for f in (0.0, 0.34, 0.68, 1.0):
        a = a0 + span * f
        dr.line([polar(cx, cy, a, (r_in - 4) * s), polar(cx, cy, a, (r_in - 22) * s)],
                fill=(236, 240, 234, 235), width=int(4 * s))
    needle(dr, cx, cy, a0 + span * 0.60, r_in - 12, s)
    return im.resize((CELL, CELL), Image.LANCZOS)


def back_cell():
    """A chevron on a plate - the only glyph that survives at this size."""
    s = SS
    im = Image.new("RGBA", (CELL * s, CELL * s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    pad = 54 * s
    dr.rounded_rectangle([pad, pad, CELL * s - pad, CELL * s - pad],
                         radius=10 * s, fill=(26, 32, 26, 210), outline=AMBER,
                         width=int(2.5 * s))
    cx, cy = CELL * s // 2, CELL * s // 2
    w, h = 26 * s, 34 * s
    dr.line([(cx + w // 2, cy - h // 2), (cx - w // 2, cy), (cx + w // 2, cy + h // 2)],
            fill=AMBER, width=int(7 * s), joint="curve")
    return im.resize((CELL, CELL), Image.LANCZOS)


def state(im, kind):
    """normal / highlighted / pressed, by lifting or dropping the whole cell."""
    if kind == "e":
        return im
    out = im.copy()
    px = out.load()
    k = {"h": 1.28, "t": 1.45, "d": 0.55}[kind]
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            px[x, y] = (min(255, int(r * k)), min(255, int(g * k)),
                        min(255, int(b * k)), a if kind != "d" else int(a * 0.7))
    return out


def sheet(cell):
    """MAC's layout: e top-left, h top-right, t and d both bottom-left."""
    im = Image.new("RGBA", (SHEET, SHEET), (0, 0, 0, 0))
    im.paste(state(cell, "e"), (0, 0))
    im.paste(state(cell, "h"), (CELL, 0))
    im.paste(state(cell, "t"), (0, CELL))
    return im


ENTRY = ('\t<file name="%s">\n'
         '\t\t<texture id="%s_e" x="0"   y="0"   width="256" height="256" />\n'
         '\t\t<texture id="%s_h" x="256" y="0"   width="256" height="256" />\n'
         '\t\t<texture id="%s_t" x="0"   y="256" width="256" height="256" />\n'
         '\t\t<texture id="%s_d" x="0"   y="256" width="256" height="256" />\n'
         '\t</file>\n')


def build():
    """(texture file stem, declared id base, the 256px cell)."""
    out = [("ui_sotz_app_forecast", "sotz_app_forecast", forecast_cell()),
           ("ui_sotz_app_back", "sotz_app_back", back_cell())]
    for key, _ in SEASONS:
        out.append(("ui_sotz_app_year_" + key, "sotz_app_year_" + key, year_cell(key)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    items = build()

    if a.write:
        os.makedirs(TEXDIR, exist_ok=True)
        os.makedirs(DESCR, exist_ok=True)
        for stem, _, cell in items:
            p = os.path.join(TEXDIR, stem + ".dds")
            sheet(cell).save(p, "DDS")
            print("  %s.dds" % stem)
        body = "".join(ENTRY % (stem, idb, idb, idb, idb) for stem, idb, _ in items)
        p = os.path.join(DESCR, "ui_sotz_apps.xml")
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("<w>\n" + body + "</w>\n")
        print("  textures_descr/ui_sotz_apps.xml  (%d files declared)" % len(items))
        return 0

    # contact sheet: every icon in every state, on the launcher's dark tile
    cols = len(items)
    pad = 8
    sh = Image.new("RGBA", (cols * (96 + pad) + pad, 3 * (96 + pad) + pad + 16),
                   (22, 26, 24, 255))
    for c, (stem, _, cell) in enumerate(items):
        for r, kind in enumerate(("e", "h", "t")):
            s = state(cell, kind).resize((96, 96), Image.LANCZOS)
            bg = Image.new("RGBA", (96, 96), (30, 36, 32, 255))
            sh.paste(Image.alpha_composite(bg, s),
                     (pad + c * (96 + pad), pad + r * (96 + pad)))
    os.makedirs(SCRATCH, exist_ok=True)
    p = os.path.join(SCRATCH, "app_icons_preview.png")
    sh.save(p)
    print("  preview -> %s" % p)
    print("  columns: " + ", ".join(s for s, _, _ in items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
