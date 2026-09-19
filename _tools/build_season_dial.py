"""Render the season dial used by the MCM panel.

A year-clock: 12 o'clock is 1 January, the hand sweeps clockwise through the year, and
each arc is sized by the season's REAL length. The arcs are deliberately NOT equal
quarters - spring is 66 days and winter is 110 - and drawing them equal would contradict
the phenological mapping the whole mod is built on.

Arc colours are the seasons' actual r__color_grading values, read from the mod's own
config, so the dial shows the colour each season will really render in.

Textures are written as uncompressed RGBA DDS, matching the format MCM's own
AMCM_Banner.dds uses (444x43, RGBA, no fourcc) - so non-power-of-two and uncompressed are
both known to load in this engine.

Usage:
  python build_season_dial.py --preview        one PNG for today, to look at
  python build_season_dial.py --all            the full set of DDS hand positions
"""
import argparse
import datetime
import io
import math
import os
import tempfile
import re

from PIL import Image, ImageDraw, ImageFont

MOD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "mods", "Seasons of the Zone")
CFG = os.path.join(MOD, "gamedata", "configs", "seasons_of_the_zone.ltx")
TEXDIR = os.path.join(MOD, "gamedata", "textures")
SCRATCH = os.path.join(tempfile.gettempdir(), "seasons_of_the_zone")

BOUNDS = [(3, 5, "spring"), (5, 20, "summer"), (9, 15, "autumn"),
          (11, 1, "winter"), (12, 1, "winter_snow")]
THEMES = {
    "spring": ("thaw, mist,", "new growth"),
    "summer": ("dry, still,", "hard sun"),
    "autumn": ("fog, low sun,", "amber light"),
    "winter": ("first snows,", "bare ground"),
    "winter_snow": ("snow cover,", "ice fog"),
}
LABEL = {"winter_snow": "Deep Winter"}      # display name where the key is not the name

SIZE = 512
CX = CY = SIZE // 2
R_OUT = 206
R_IN = 116
R_LABEL = 159
POSITIONS = 32          # hand positions around the year (~11 days each)
TEX = 384               # saved texture size; 512 is only the drawing canvas

FONTS = [r"C:\Windows\Fonts\seguisb.ttf", r"C:\Windows\Fonts\segoeui.ttf",
         r"C:\Windows\Fonts\calibrib.ttf", r"C:\Windows\Fonts\arial.ttf"]


def font(sz):
    for f in FONTS:
        if os.path.isfile(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


def season_colours():
    """Arc colour per season: the grade, tinted by how green the world actually is.

    WHY NOT THE GRADE ALONE. Spring's r__color_grading peaks on blue (0.44, 0.44, 0.50)
    and so does winter's (0.69, 0.76, 0.87). Normalising each to its own peak - which is
    what makes all four read brightly - then collapsed both to nearly the same pale blue,
    and the dial showed spring as a second winter. The grade is genuinely cool in both;
    what separates them on screen is that spring's world is GREEN.

    THE TINT DRIVER is `sss_int * (hemi + amb)`: leaf translucency times diffuse sky
    light. That product is the visual signature of fresh foliage lit by a bright overcast
    sky, and it isolates spring sharply - spring carries 2.1x the diffuse light of any
    other season, so normalised and squared the strengths come out

        spring 0.450   summer 0.081   autumn 0.042   winter 0.008

    Only spring moves. That matters: earlier attempts drove the tint from sss_int alone,
    where spring and summer sit only 12% apart, so fixing spring also dragged summer from
    pale yellow into olive - fighting its own "dry, still, hard sun" label - and pulled
    autumn off the amber that was reading best of the four.

    Brightness is deliberately NOT modelled. Weighting each arc by its real light
    (exposure x sun/hemi/amb) is more honest photometrically and was tried, but it left
    autumn dim exactly when it is the highlighted arc. This is a legend, not a light meter.
    """
    out, cur = {}, None
    for ln in io.open(CFG, encoding="cp1251", errors="replace", newline=""):
        s = ln.strip()
        m = re.match(r"^\[([a-z_]+)\]$", s)      # _ matters: [winter_snow]
        if m:
            cur = m.group(1)
            out.setdefault(cur, {})
            continue
        m = re.match(r"^(grade_[rgb]|sss_int|sun_lumscale_hemi|sun_lumscale_amb)"
                     r"\s*=\s*([0-9.]+)", s)
        if m and cur:
            out[cur][m.group(1)] = float(m.group(2))

    seasons = ("spring", "summer", "autumn", "winter", "winter_snow")
    GREEN = (0.42, 0.80, 0.33)
    MIX, POWER = 0.45, 2.0

    def vigour(s):
        g = out.get(s, {})
        return g.get("sss_int", 0.0) * (g.get("sun_lumscale_hemi", 0.0)
                                        + g.get("sun_lumscale_amb", 0.0))

    vmax = max(vigour(s) for s in seasons) or 1.0

    cols = {}
    for s in seasons:
        g = out.get(s, {})
        rgb = [g.get("grade_r", 0.7), g.get("grade_g", 0.7), g.get("grade_b", 0.7)]
        k = MIX * (vigour(s) / vmax) ** POWER
        lum = sum(c * w for c, w in zip(rgb, (0.2126, 0.7152, 0.0722)))
        rgb = [c * (1 - k) + gc * lum * k / 0.56 for c, gc in zip(rgb, GREEN)]
        peak = max(rgb + [0.001])
        cols[s] = tuple(int(max(0, min(255, round(c / peak * 235)))) for c in rgb)
    return cols


def doy(m, d, year):
    return datetime.date(year, m, d).timetuple().tm_yday


def year_len(year):
    return datetime.date(year, 12, 31).timetuple().tm_yday


def arcs(year):
    """(start_deg, end_deg, season, days) with 0deg at 12 o'clock, clockwise."""
    yl = year_len(year)
    out = []
    for i, (m, d, s) in enumerate(BOUNDS):
        nm, nd, _ = BOUNDS[(i + 1) % len(BOUNDS)]
        a = doy(m, d, year)
        b = doy(nm, nd, year)
        days = b - a
        if days <= 0:
            days += yl
        out.append(((a - 1) / yl * 360.0, ((a - 1) + days) / yl * 360.0, s, days))
    return out


def polar(deg, radius):
    """deg 0 = 12 o'clock, increasing clockwise."""
    rad = math.radians(deg - 90.0)
    return (CX + radius * math.cos(rad), CY + radius * math.sin(rad))


def render(date, cols):
    ss = 2                                   # supersample: PIL has no arc antialiasing
    global CX, CY
    im = Image.new("RGBA", (SIZE * ss, SIZE * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)

    def box(r):
        return [(CX - r) * ss, (CY - r) * ss, (CX + r) * ss, (CY + r) * ss]

    year = date.year
    yl = year_len(year)
    today_deg = (date.timetuple().tm_yday - 1) / yl * 360.0

    cur = BOUNDS[-1][2]
    for m, d, s in BOUNDS:
        if date.timetuple().tm_yday >= doy(m, d, year):
            cur = s

    for a0, a1, s, days in arcs(year):
        col = cols[s]
        is_cur = (s == cur)
        # Dim the inactive arcs by DARKENING, not by going transparent. At low alpha the
        # dark-green panel behind showed through and pulled every muted arc toward green,
        # which collapsed spring and summer back together - the same complaint in a new
        # form. Near-opaque keeps each hue intact.
        fill = (col + (236,)) if is_cur else                (tuple(int(c * 0.52) for c in col) + (228,))
        dr.pieslice(box(R_OUT), a0 - 90, a1 - 90, fill=fill)
    dr.ellipse(box(R_IN), fill=(0, 0, 0, 0))

    # separators + outline
    for a0, _, _, _ in arcs(year):
        p1, p2 = polar(a0, R_IN), polar(a0, R_OUT)
        dr.line([p1[0] * ss, p1[1] * ss, p2[0] * ss, p2[1] * ss],
                fill=(20, 24, 20, 230), width=3 * ss)
    dr.ellipse(box(R_OUT), outline=(225, 230, 225, 190), width=2 * ss)
    dr.ellipse(box(R_IN), outline=(225, 230, 225, 150), width=2 * ss)

    # month ticks
    for mth in range(1, 13):
        deg = (doy(mth, 1, year) - 1) / yl * 360.0
        p1, p2 = polar(deg, R_OUT - 11), polar(deg, R_OUT)
        dr.line([p1[0] * ss, p1[1] * ss, p2[0] * ss, p2[1] * ss],
                fill=(235, 240, 235, 150), width=2 * ss)

    im = im.resize((SIZE, SIZE), Image.LANCZOS)
    dr = ImageDraw.Draw(im)

    f_name, f_theme, f_days, f_mid, f_sub = font(21), font(14), font(13), font(27), font(14)

    # hand - a tapered blade, not a needle: wide at the hub, narrow at the tip, so it
    # reads as a clock hand at a glance rather than as another separator line
    def offset(pt, deg, d):
        rad = math.radians(deg - 90.0)
        return (pt[0] + d * math.cos(rad), pt[1] + d * math.sin(rad))

    perp = today_deg + 90.0
    tip = polar(today_deg, R_OUT - 20)
    hub = polar(today_deg + 180.0, 34)
    blade = [offset(hub, perp, 7.5), offset(tip, perp, 1.8),
             offset(tip, perp, -1.8), offset(hub, perp, -7.5)]
    dr.polygon(blade, fill=(255, 255, 255, 250), outline=(14, 17, 14, 255))
    dr.ellipse([CX - 11, CY - 11, CX + 11, CY + 11], fill=(252, 252, 252, 255),
               outline=(14, 17, 14, 255), width=3)

    for a0, a1, s, days in arcs(year):
        mid = (a0 + a1) / 2.0
        is_cur = (s == cur)
        x, y = polar(mid, R_LABEL)
        disp = LABEL.get(s, s.capitalize())
        name = disp.upper() if is_cur else disp
        narrow = (a1 - a0) < 46.0
        nc = (255, 255, 255, 255) if is_cur else (240, 244, 240, 240)
        tc = (246, 249, 246, 240) if is_cur else (224, 230, 224, 215)
        # A 37-day season is a 36-degree arc; four stacked lines will not fit without
        # colliding with its neighbours, so narrow arcs drop the theme and keep the facts.
        if narrow:
            rows = ((name, f_name, nc, -16),
                    ("%d days" % days, f_days, tc, 8))
        else:
            rows = ((name, f_name, nc, -28),
                    (THEMES[s][0], f_theme, tc, -5),
                    (THEMES[s][1], f_theme, tc, 10),
                    ("%d days" % days, f_days, tc, 26))
        for txt, fnt, col, dy in rows:
            w = dr.textbbox((0, 0), txt, font=fnt)
            dr.text((x - (w[2] - w[0]) / 2, y + dy), txt, font=fnt, fill=col)

    # centre readout - season only. The exact date is NOT baked in: that would need one
    # texture per day. It is rendered as live text in the MCM row above the dial.
    # sits ABOVE the hub - anything at centre height is covered by it
    f_big = font(31)
    ctr = LABEL.get(cur, cur.capitalize()).upper()
    w = dr.textbbox((0, 0), ctr, font=f_big)
    dr.text((CX - (w[2] - w[0]) / 2, CY - 68), ctr, font=f_big,
            fill=(255, 255, 255, 250))
    return im


def save_dds(im, path):
    """Uncompressed RGBA, matching MCM's own AMCM_Banner.dds.

    DXT5 was measured at a quarter the size but scattered red block artifacts over the
    amber arc and fringed the white label text - unusable for an image that is mostly
    smooth gradient and small type.
    """
    im.convert("RGBA").resize((TEX, TEX), Image.LANCZOS).save(path, "DDS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--date", default=None)
    a = ap.parse_args()

    cols = season_colours()
    print("  arc colours from config: " +
          "  ".join("%s=%s" % (k, v) for k, v in sorted(cols.items())))

    if a.preview or not a.all:
        d = (datetime.date.fromisoformat(a.date) if a.date
             else datetime.date.today())
        out = os.path.join(SCRATCH, "dial_preview.png")
        dial = render(d, cols)
        bg = Image.new("RGBA", dial.size, (17, 30, 19, 255))   # MCM panel, roughly
        Image.alpha_composite(bg, dial).save(out)
        print("  preview -> %s  (%s)" % (out, d))
        return

    os.makedirs(TEXDIR, exist_ok=True)
    year = 2026                       # non-leap reference year for hand angles
    yl = year_len(year)

    # Every season MUST get at least one position, or the runtime picker (which selects
    # the nearest dial WITHIN the current season) has nothing to choose and the panel
    # highlights the wrong arc. Winter is only 30 days, so this is a live constraint,
    # not a formality - at the old 16 positions the step was 23 days and winter could
    # have been skipped entirely.
    got = {}
    for i in range(POSITIONS):
        day = int(round(i * yl / POSITIONS)) + 1
        d = datetime.date(year, 1, 1) + datetime.timedelta(days=day - 1)
        cur = BOUNDS[-1][2]
        for m, dd, s in BOUNDS:
            if d.timetuple().tm_yday >= doy(m, dd, year):
                cur = s
        got[cur] = got.get(cur, 0) + 1
    missing = [s for _, _, s in BOUNDS if s not in got]
    if missing:
        raise SystemExit("POSITIONS=%d leaves %s with no dial - raise it"
                         % (POSITIONS, ", ".join(missing)))
    print("  positions per season: %s"
          % "  ".join("%s=%d" % (s, got[s]) for _, _, s in BOUNDS))
    for i in range(POSITIONS):
        day = int(round(i * yl / POSITIONS)) + 1
        d = datetime.date(year, 1, 1) + datetime.timedelta(days=day - 1)
        p = os.path.join(TEXDIR, "ui_seasons_dial_%02d.dds" % i)
        save_dds(render(d, cols), p)
    print("  wrote %d dials to %s" % (POSITIONS, TEXDIR))
    print("  each %.0f KB, total %.1f MB"
          % (os.path.getsize(os.path.join(TEXDIR, "ui_seasons_dial_00.dds")) / 1024.0,
             sum(os.path.getsize(os.path.join(TEXDIR, f))
                 for f in os.listdir(TEXDIR) if f.startswith("ui_seasons_dial_"))
             / 1048576.0))


if __name__ == "__main__":
    main()
