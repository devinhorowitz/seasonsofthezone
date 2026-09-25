"""Render the year dial for the MCM page.

12 o'clock is 1 January and the hand sweeps clockwise through the year. Each arc is sized
by the season's real length. Arc colors come from the seasons' own color grades in the
mod's config, so the dial is also a legend.

Textures are uncompressed RGBA DDS, the format MCM's own AMCM_Banner.dds uses. DXT5 was
a quarter the size but put block artefacts over the amber arc and fringed the text.

A calendar of the player's own, or names of their own for the seasons, gets its own set,
drawn by season.py through write_set() as ui_seasons_dial_cNN.dds, so the shipped set is
never touched.

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

BOUNDS = [(3, 5, "late_winter"), (4, 15, "spring"), (5, 20, "summer"), (9, 15, "autumn"),
          (11, 1, "winter"), (12, 1, "winter_snow")]
THEMES = {
    "late_winter": ("thaw, mud,", "bare trees"),
    "spring": ("new leaves,", "showers"),
    "summer": ("dry, still,", "hard sun"),
    "autumn": ("fog, low sun,", "amber light"),
    "winter": ("first snows,", "bare ground"),
    "winter_snow": ("snow cover,", "ice fog"),
}
LABEL = {"winter_snow": "Deep Winter", "late_winter": "Late Winter"}

SIZE = 512
CX = CY = SIZE // 2
R_OUT = 206
R_IN = 116
R_LABEL = 159
POSITIONS = 32          # hand positions around the year (~11 days apart)
TEX = 384               # saved texture size; 512 is the drawing canvas
YEAR = 2026             # a year without Feb 29: the hand angles are drawn for it

FONTS = [r"C:\Windows\Fonts\seguisb.ttf", r"C:\Windows\Fonts\segoeui.ttf",
         r"C:\Windows\Fonts\calibrib.ttf", r"C:\Windows\Fonts\arial.ttf"]


def font(sz):
    for f in FONTS:
        if os.path.isfile(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


def season_colors(cfg=None):
    """Arc color per season: the color grade, tinted green by how much diffuse light
    reaches the foliage (sss_int * (hemi + amb)).

    The grade alone is not enough: spring's and winter's grades both peak on blue and
    normalized to their own peak they came out the same pale blue. The tint separates
    them; spring carries about twice the diffuse light of any other season, so after
    normalising and squaring only spring moves noticeably. Brightness is not modeled;
    this is a legend, not a light meter.
    """
    out, cur = {}, None
    for ln in io.open(cfg or CFG, encoding="cp1251", errors="replace", newline=""):
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

    seasons = ("spring", "summer", "autumn", "winter", "winter_snow", "late_winter")
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


def arcs(year, bounds=None):
    """(start_deg, end_deg, season, days), 0 deg at 12 o'clock, clockwise."""
    bounds = bounds or BOUNDS
    yl = year_len(year)
    out = []
    for i, (m, d, s) in enumerate(bounds):
        nm, nd, _ = bounds[(i + 1) % len(bounds)]
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


def season_on(date, bounds=None):
    """The season a date falls in: the last start on or before it, else the one that
    wraps the year end."""
    bounds = bounds or BOUNDS
    cur = bounds[-1][2]
    for m, d, s in bounds:
        if date.timetuple().tm_yday >= doy(m, d, date.year):
            cur = s
    return cur


def radial_text(im, txt, fnt, col, deg, radius):
    """txt along the radius at deg, centered on `radius`: reading outward on the right half
    of the dial and inward on the left, so it is never upside down. For an arc too short
    to hold its name across it."""
    dr = ImageDraw.Draw(im)
    l, t, r, b = dr.textbbox((0, 0), txt, font=fnt)
    tile = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((2 - l, 2 - t), txt, font=fnt, fill=col)
    a = deg % 360.0
    tile = tile.rotate((90.0 - a) if a <= 180.0 else (270.0 - a),
                       resample=Image.BICUBIC, expand=True)
    x, y = polar(deg, radius)
    im.alpha_composite(tile, (int(round(x - tile.width / 2.0)),
                              int(round(y - tile.height / 2.0))))


def fit(dr, text, avail, sizes):
    """(text, font) at the largest of `sizes` that fits `avail`; at the smallest, a name
    that still does not fit is shortened, with an ellipsis."""
    for size in sizes:
        f = font(size)
        if dr.textbbox((0, 0), text, font=f)[2] <= avail:
            return text, f
    while len(text) > 1 and dr.textbbox((0, 0), text + "\u2026", font=f)[2] > avail:
        text = text[:-1].rstrip()
    return text + "\u2026", f


def render(date, cols, bounds=None, names=None):
    """The dial for `date`. `names` is {season: name} for seasons the player renamed."""
    bounds = bounds or BOUNDS
    names = names or {}
    ss = 2                                   # supersample: PIL has no arc antialiasing
    im = Image.new("RGBA", (SIZE * ss, SIZE * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)

    def box(r):
        return [(CX - r) * ss, (CY - r) * ss, (CX + r) * ss, (CY + r) * ss]

    year = date.year
    yl = year_len(year)
    today_deg = (date.timetuple().tm_yday - 1) / yl * 360.0

    cur = season_on(date, bounds)

    for a0, a1, s, days in arcs(year, bounds):
        col = cols[s]
        is_cur = (s == cur)
        # inactive arcs are darkened, not made transparent: the green panel behind
        # would show through and pull every hue towards green
        fill = (col + (236,)) if is_cur else (tuple(int(c * 0.52) for c in col) + (228,))
        dr.pieslice(box(R_OUT), a0 - 90, a1 - 90, fill=fill)
    dr.ellipse(box(R_IN), fill=(0, 0, 0, 0))

    for a0, _, _, _ in arcs(year, bounds):
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

    for a0, a1, s, days in arcs(year, bounds):
        mid = (a0 + a1) / 2.0
        is_cur = (s == cur)
        x, y = polar(mid, R_LABEL)
        disp = names.get(s) or LABEL.get(s, s.capitalize())
        name = disp.upper() if is_cur else disp
        narrow = (a1 - a0) < 46.0
        nc = (255, 255, 255, 255) if is_cur else (240, 244, 240, 240)
        tc = (246, 249, 246, 240) if is_cur else (224, 230, 224, 215)
        # A long name on a short arc shrinks to fit the chord it sits on: "LATE WINTER"
        # at full size runs out of its 41 days. Past a half circle the chord is no limit.
        avail = 2 * R_LABEL * math.sin(math.radians(min(a1 - a0, 180.0)) / 2) - 10
        f_n, size = f_name, 21
        while dr.textbbox((0, 0), name, font=f_n)[2] > avail and size > 14:
            size -= 1
            f_n = font(size)
        if (dr.textbbox((0, 0), name, font=f_n)[2] > avail
                or (narrow and dr.textbbox((0, 0), "%d days" % days, font=f_days)[2] > avail)):
            # A season of a player's own can be two weeks long, too short to hold its
            # name across it: the name runs along the radius instead, and the days go.
            text, f_r = fit(dr, name, R_OUT - R_IN - 14, range(17, 10, -1))
            radial_text(im, text, f_r, nc, mid, (R_OUT + R_IN) / 2.0)
            continue
        # a 30-day arc has no room for the theme lines
        if narrow:
            rows = ((name, f_n, nc, -16),
                    ("%d days" % days, f_days, tc, 8))
        else:
            rows = ((name, f_n, nc, -28),
                    (THEMES[s][0], f_theme, tc, -5),
                    (THEMES[s][1], f_theme, tc, 10),
                    ("%d days" % days, f_days, tc, 26))
        for txt, fnt, col, dy in rows:
            w = dr.textbbox((0, 0), txt, font=fnt)
            dr.text((x - (w[2] - w[0]) / 2, y + dy), txt, font=fnt, fill=col)

    # center: the season name, above the hub. The date is live text in the MCM row
    # above the dial, not baked in.
    # 200px is the inner circle's width at the top of the line: "DEEP WINTER" is 197
    ctr, f_big = fit(dr, (names.get(cur) or LABEL.get(cur, cur.capitalize())).upper(), 200,
                     range(31, 13, -1))
    w = dr.textbbox((0, 0), ctr, font=f_big)
    dr.text((CX - (w[2] - w[0]) / 2, CY - 68), ctr, font=f_big,
            fill=(255, 255, 255, 250))
    return im


def save_dds(im, path):
    im.convert("RGBA").resize((TEX, TEX), Image.LANCZOS).save(path, "DDS")


def positions(year=YEAR):
    """(index, date) for each hand position. floor(x + 0.5), not round(): the mod's
    dial_texture() works the same days out in Lua, and round() halves to even."""
    yl = year_len(year)
    return [(i, datetime.date(year, 1, 1)
             + datetime.timedelta(days=int(math.floor(i * yl / POSITIONS + 0.5))))
            for i in range(POSITIONS)]


def positions_per_season(bounds):
    """{season: hand positions inside it}. The mod shows the nearest dial whose own date
    is in today's season, so a season with none would show another season's dial."""
    got = {s: 0 for _, _, s in bounds}
    for _, d in positions():
        got[season_on(d, bounds)] += 1
    return got


def write_set(bounds, texdir, prefix, cfg=None, quiet=False, names=None):
    """Draw every hand position for `bounds`, [(month, day, season), ...], as
    <texdir>/<prefix>NN.dds, with `names` ({season: name}) for seasons the player renamed.
    Returns how many were written."""
    bounds = sorted(bounds)
    got = positions_per_season(bounds)
    missing = [s for s, n in got.items() if not n]
    if missing:
        raise ValueError("POSITIONS=%d leaves %s with no dial"
                         % (POSITIONS, ", ".join(missing)))
    cols = season_colors(cfg)
    os.makedirs(texdir, exist_ok=True)
    for i, d in positions():
        save_dds(render(d, cols, bounds, names),
                 os.path.join(texdir, "%s%02d.dds" % (prefix, i)))
    if not quiet:
        print("  positions per season: %s"
              % "  ".join("%s=%d" % (s, got[s]) for _, _, s in bounds))
        print("  wrote %d dials to %s" % (POSITIONS, texdir))
    return POSITIONS


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

    write_set(BOUNDS, TEXDIR, "ui_seasons_dial_")
    print("  each %.0f KB, total %.1f MB"
          % (os.path.getsize(os.path.join(TEXDIR, "ui_seasons_dial_00.dds")) / 1024.0,
             sum(os.path.getsize(os.path.join(TEXDIR, f))
                 for f in os.listdir(TEXDIR) if f.startswith("ui_seasons_dial_")
                 and not f.startswith("ui_seasons_dial_c"))
             / 1048576.0))


if __name__ == "__main__":
    main()
