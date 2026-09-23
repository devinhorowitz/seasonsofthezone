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

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(os.path.dirname(HERE), "mods", "Seasons of the Zone")
TEXDIR = os.path.join(MOD, "gamedata", "textures")
DESCR = os.path.join(MOD, "gamedata", "configs", "ui", "textures_descr")
SCRATCH = os.path.join(tempfile.gettempdir(), "seasons_of_the_zone")

INK = (14, 17, 14, 255)

FONTS = [r"C:\Windows\Fonts\seguisb.ttf", r"C:\Windows\Fonts\segoeui.ttf",
         r"C:\Windows\Fonts\calibrib.ttf", r"C:\Windows\Fonts\arial.ttf"]


def font(sz):
    for f in FONTS:
        if os.path.isfile(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


# What an aneroid barometer actually says on its face. The gauge already reasons in these
# terms - the bands are storm, change and fair - so labelling it this way costs nothing
# and turns an unlabelled arc into a dial you can read a value off.
FACE_WORDS = [(0.07, "STORMY"), (0.26, "RAIN"), (0.50, "CHANGE"),
              (0.74, "FAIR"), (0.93, "DRY")]
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
# These have to FIT the canvas. The first version reused the radii from the 512px app
# icon on a 384px sheet, so the arc was drawn from x=-42 to x=426 and both ends were
# simply clipped away - the gauge looked sawn off on the page and nothing warned.
R_OUT, R_IN, R_TICK = 184, 152, 145
CX = SIZE // 2
CY = 252

# The arc only covers the top of the circle, so its box is not the circle's box: the
# lowest ink is at CY + R*sin(A_START), about two thirds of the way up from the middle,
# not at CY + R. Measuring it properly is what lets the gauge be this large and still fit.
_ANGLES = [A_START, A_END] + [a for a in (180.0, 270.0, 360.0) if A_START <= a <= A_END]
_XS = [CX + R_OUT * math.cos(math.radians(a)) for a in _ANGLES]
_YS = [CY + R_OUT * math.sin(math.radians(a)) for a in _ANGLES]
assert min(_XS) >= 0 and max(_XS) <= SIZE, (
    "the arc spans x %.0f..%.0f on a %d canvas - both ends would be clipped away, "
    "which is exactly what shipped once" % (min(_XS), max(_XS), SIZE))
assert min(_YS) >= 0 and max(_YS) <= SIZE, (
    "the arc spans y %.0f..%.0f on a %d canvas" % (min(_YS), max(_YS), SIZE))


def polar(cx, cy, deg, r):
    rad = math.radians(deg)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))


def gauge_face():
    """Bands and ticks. Identical for every cycle, so it is drawn once."""
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

    # the words, set inside the ticks and centred on their own gradation
    f = font(int(15 * s))
    for frac, word in FACE_WORDS:
        a = A_START + span * frac
        px, py = polar(cx, cy, a, (R_TICK - 44) * s)
        bb = dr.textbbox((0, 0), word, font=f)
        dr.text((px - (bb[2] - bb[0]) / 2.0, py - (bb[3] - bb[1]) / 2.0), word,
                font=f, fill=(206, 214, 204, 240))
    return im.resize((SIZE, SIZE), Image.LANCZOS)


def needle(fraction):
    """The needle alone, on the same canvas as the face so the two share a rect.

    Separate because a baked-in needle cannot move, and a barometer that never moves is
    a picture of an instrument rather than one. The page nudges this by a pixel now and
    then; the bands underneath stay put, which is what makes the nudge read as the
    needle rather than as the whole panel shaking.
    """
    s = SS
    im = Image.new("RGBA", (SIZE * s, SIZE * s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    cx, cy = CX * s, CY * s
    span = A_END - A_START

    def off(pt, deg, d):
        rad = math.radians(deg)
        return (pt[0] + d * s * math.cos(rad), pt[1] + d * s * math.sin(rad))

    at = A_START + span * fraction
    perp = at + 90.0
    tip = polar(cx, cy, at, (R_IN - 16) * s)
    hub = polar(cx, cy, at + 180.0, 26 * s)
    dr.polygon([off(hub, perp, 6.0), off(tip, perp, 1.5),
                off(tip, perp, -1.5), off(hub, perp, -6.0)],
               fill=(255, 255, 255, 250), outline=INK)
    dr.ellipse([cx - 9 * s, cy - 9 * s, cx + 9 * s, cy + 9 * s],
               fill=(252, 252, 252, 255), outline=INK, width=int(3 * s))
    return im.resize((SIZE, SIZE), Image.LANCZOS)


def white_block():
    """Tinted with SetTextureColor to draw every bar on both pages."""
    return Image.new("RGBA", (8, 8), (255, 255, 255, 255))


def button_strip():
    """A four-state plate, 4 cells of 16x16 in a row.

    Init3tButton makes the engine append _e/_h/_t/_d and look those up as declared ids -
    the white block alone satisfies none of them and the button draws nothing, which is
    the same fault that shipped the empty launcher tiles. Four distinct cells also buys
    real hover feedback, which one tinted block could not.
    """
    cells = [(40, 46, 40, 235),     # e  resting
             (62, 70, 58, 245),     # h  hovered
             (86, 74, 44, 255),     # t  pressed, warm like the amber label
             (30, 34, 30, 180)]     # d  disabled
    im = Image.new("RGBA", (64, 16), (0, 0, 0, 0))
    for i, c in enumerate(cells):
        im.paste(Image.new("RGBA", (16, 16), c), (i * 16, 0))
    return im


ENTRY = ('\t<file name="%s">\n\t\t<texture id="%s" x="0" y="0" '
         'width="%d" height="%d" />\n\t</file>\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    items = [("ui_sotz_px", "sotz_px", 8, white_block()),
             ("ui_sotz_gauge_face", "sotz_gauge_face", SIZE, gauge_face())]
    for cycle, f in sorted(CYCLE_AT.items()):
        items.append(("ui_sotz_needle_" + cycle, "sotz_needle_" + cycle, SIZE,
                      needle(f)))

    if a.write:
        os.makedirs(TEXDIR, exist_ok=True)
        os.makedirs(DESCR, exist_ok=True)
        for stem, _, _, im in items:
            im.save(os.path.join(TEXDIR, stem + ".dds"), "DDS")
            print("  %s.dds" % stem)
        body = "".join(ENTRY % (stem, idn, n, n) for stem, idn, n, _ in items)
        # the button strip declares four ids into one file, so it is written by hand
        button_strip().save(os.path.join(TEXDIR, "ui_sotz_btn.dds"), "DDS")
        print("  ui_sotz_btn.dds")
        # The ecologists' emblem, taken from the faction banner G.A.M.M.A. UI already
        # ships. The whole 383x179 region is a shield on the left and an empty name
        # plate on the right, and using it whole put a large black box on the page.
        body += ('\t<file name="ui\\ui_actor_menu_factions">\n'
                 '\t\t<texture id="sotz_eco_mark" x="8" y="952" width="112" '
                 'height="112" />\n\t</file>\n')
        body += '\t<file name="ui_sotz_btn">\n'
        for i, suf in enumerate(("e", "h", "t", "d")):
            body += ('\t\t<texture id="sotz_btn_%s" x="%d" y="0" width="16" '
                     'height="16" />\n' % (suf, i * 16))
        body += "\t</file>\n"
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
