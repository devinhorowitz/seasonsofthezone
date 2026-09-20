"""Render the year dial for the MCM page.

12 o'clock is 1 January and the hand sweeps clockwise through the year. Each arc is sized
by the season's real length. Arc colors come from the seasons' own color grades in the
mod's config, so the dial is also a legend.

Textures are uncompressed RGBA DDS, the format MCM's own AMCM_Banner.dds uses. DXT5 was
a quarter the size but put block artefacts over the amber arc and fringed the text.

Usage:
  python build_season_dial.py --preview        one PNG for today
  python build_season_dial.py --all            the full set of hand positions
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
LABEL = {"winter_snow": "Deep Winter"}

SIZE = 512
CX = CY = SIZE // 2
R_OUT = 206
R_IN = 116
R_LABEL = 159
POSITIONS = 32          # hand positions around the year (~11 days apart)
TEX = 384               # saved texture size; 512 is the drawing canvas

FONTS = [r"C:\Windows\Fonts\seguisb.ttf", r"C:\Windows\Fonts\segoeui.ttf",
         r"C:\Windows\Fonts\calibrib.ttf", r"C:\Windows\Fonts\arial.ttf"]


def font(sz):
    for f in FONTS:
        if os.path.isfile(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


def season_colors():
    """Arc color per season: the color grade, tinted green by how much diffuse light
    reaches the foliage (sss_int * (hemi + amb)).

    The grade alone is not enough: spring's and winter's grades both peak on blue and
    normalized to their own peak they came out the same pale blue. The tint separates
    them; spring carries about twice the diffuse light of any other season, so after
    normalising and squaring only spring moves noticeably. Brightness is not modeled;
    this is a legend, not a light meter.
    """
    out, cur = {}, None
    for ln in io.open(CFG, encoding="cp1251", errors="replace", newline=""):
        s = ln.strip()
        m = re.match(r"^\[([a-z_]+)\]$", s)
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
    """(start_deg, end_deg, season, days), 0 deg at 12 o'clock, clockwise."""
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
        # inactive arcs are darkened, not made transparent: the green panel behind
        # would show through and pull every hue towards green
        fill = (col + (236,)) if is_cur else (tuple(int(c * 0.52) for c in col) + (228,))
        dr.pieslice(box(R_OUT), a0 - 90, a1 - 90, fill=fill)
    dr.ellipse(box(R_IN), fill=(0, 0, 0, 0))

    for a0, _, _, _ in arcs(year):
        p1, p2 = polar(a0, R_IN), polar(a0, R_OUT)
        dr.line([p1[0] * ss, p1[1] * ss, p2[0] * ss, p2[1] * ss],
                fill=(20, 24, 20, 230), width=3 * ss)
    dr.ellipse(box(R_OUT), outline=(225, 230, 225, 190), width=2 * ss)
    dr.ellipse(box(R_IN), outline=(225, 230, 225, 150), width=2 * ss)

    for mth in range(1, 13):
        deg = (doy(mth, 1, year) - 1) / yl * 360.0
        p1, p2 = polar(deg, R_OUT - 11), polar(deg, R_OUT)
        dr.line([p1[0] * ss, p1[1] * ss, p2[0] * ss, p2[1] * ss],
                fill=(235, 240, 235, 150), width=2 * ss)

    im = im.resize((SIZE, SIZE), Image.LANCZOS)
    dr = ImageDraw.Draw(im)

    f_name, f_theme, f_days, f_mid, f_sub = font(21), font(14), font(13), font(27), font(14)

    # the hand: a tapered blade, wide at the hub
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
        # a 30-day arc has no room for the theme lines
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

    # center: the season name, above the hub. The date is live text in the MCM row
    # above the dial, not baked in.
    f_big = font(31)
    ctr = LABEL.get(cur, cur.capitalize()).upper()
    w = dr.textbbox((0, 0), ctr, font=f_big)
    dr.text((CX - (w[2] - w[0]) / 2, CY - 68), ctr, font=f_big,
            fill=(255, 255, 255, 250))
    return im


def save_dds(im, path):
    im.convert("RGBA").resize((TEX, TEX), Image.LANCZOS).save(path, "DDS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--date", default=None)
    a = ap.parse_args()

    cols = season_colors()
    print("  arc colors from config: " +
          "  ".join("%s=%s" % (k, v) for k, v in sorted(cols.items())))

    if a.preview or not a.all:
        d = (datetime.date.fromisoformat(a.date) if a.date
             else datetime.date.today())
        out = os.path.join(SCRATCH, "dial_preview.png")
        os.makedirs(SCRATCH, exist_ok=True)
        dial = render(d, cols)
        bg = Image.new("RGBA", dial.size, (17, 30, 19, 255))   # roughly the MCM panel
        Image.alpha_composite(bg, dial).save(out)
        print("  preview -> %s  (%s)" % (out, d))
        return

    os.makedirs(TEXDIR, exist_ok=True)
    year = 2026                       # non-leap reference year for hand angles
    yl = year_len(year)

    # Every season needs at least one position: the mod picks the nearest dial within
    # the current season, and winter is only 30 days.
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
