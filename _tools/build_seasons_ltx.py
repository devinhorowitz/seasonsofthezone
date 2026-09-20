"""Generate the mod's season table, gamedata/configs/seasons_of_the_zone.ltx.

Every value the mod sends to the engine comes from that file. The tables here are the
source: edit them, run this, reload a save.

Grade values were tuned in play as cfg_load presets and are carried here as data.
`--presets <dir>` re-reads them from a folder of Atmos_<season>.ltx files. (At launch,
season.py can also take the grade from presets named in seasons_config.py's
GRADE_PRESETS; see scan_preset().) Flora, fog, wind and wetness are authored here.

Usage:
    python _tools/build_seasons_ltx.py                  # regenerate the shipped file
    python _tools/build_seasons_ltx.py --out X.ltx      # write elsewhere
    python _tools/build_seasons_ltx.py --presets DIR    # grade from preset files
"""
import argparse
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "mods", "Seasons of the Zone", "gamedata",
                   "configs", "seasons_of_the_zone.ltx")

# console variable in a preset -> ltx key(s), in component order
GRADE_MAP = [
    ("r__color_grading",       ["grade_r", "grade_g", "grade_b"]),
    ("r__saturation",          ["saturation"]),
    ("r__gamma",               ["gamma"]),
    ("r__exposure",            ["exposure"]),
    ("r2_sun_lumscale",        ["sun_lumscale"]),
    ("r2_sun_lumscale_hemi",   ["sun_lumscale_hemi"]),
    ("r2_sun_lumscale_amb",    ["sun_lumscale_amb"]),
    ("r2_tonemap_adaptation",  ["tonemap_adaptation"]),
    ("r2_tonemap_lowlum",      ["tonemap_lowlum"]),
    ("r2_tonemap_middlegray",  ["tonemap_middlegray"]),
    ("ssfx_hud_hemi",          ["hud_hemi"]),
    ("r2_sunshafts_value",     ["sunshafts_value"]),
]
GRADE_KEYS = [k for _, ks in GRADE_MAP for k in ks]

# The grade per season. winter_snow is a neutral grade for snow textures: white ground
# carries the look. Spring's preset had no sunshafts_value; it takes the neutral 0.55.
GRADE = {
    "spring": dict(grade_r=0.44, grade_g=0.44, grade_b=0.5, saturation=0.93, gamma=0.985,
                   exposure=1.08, sun_lumscale=3.0, sun_lumscale_hemi=1.45,
                   sun_lumscale_amb=1.7, tonemap_adaptation=3.0, tonemap_lowlum=0.55,
                   tonemap_middlegray=1.2, hud_hemi=0.3, sunshafts_value=0.55),
    "summer": dict(grade_r=0.725, grade_g=0.725, grade_b=0.525, saturation=1.05, gamma=1.0,
                   exposure=0.75, sun_lumscale=3.0, sun_lumscale_hemi=0.8,
                   sun_lumscale_amb=0.7, tonemap_adaptation=2.0, tonemap_lowlum=0.25,
                   tonemap_middlegray=1.8, hud_hemi=0.1, sunshafts_value=0.51),
    "autumn": dict(grade_r=0.86, grade_g=0.705, grade_b=0.44, saturation=1.13, gamma=1.01,
                   exposure=0.8, sun_lumscale=2.1, sun_lumscale_hemi=0.82,
                   sun_lumscale_amb=0.68, tonemap_adaptation=2.6, tonemap_lowlum=0.23,
                   tonemap_middlegray=1.45, hud_hemi=0.15, sunshafts_value=0.58),
    "winter": dict(grade_r=0.69, grade_g=0.76, grade_b=0.87, saturation=1.0, gamma=1.03,
                   exposure=0.77, sun_lumscale=2.05, sun_lumscale_hemi=0.8,
                   sun_lumscale_amb=0.65, tonemap_adaptation=3.0, tonemap_lowlum=0.21,
                   tonemap_middlegray=1.15, hud_hemi=0.14, sunshafts_value=0.55),
    "winter_snow": dict(grade_r=0.7, grade_g=0.7, grade_b=0.7, saturation=1.0, gamma=1.0,
                        exposure=0.8, sun_lumscale=2.05, sun_lumscale_hemi=0.75,
                        sun_lumscale_amb=0.65, tonemap_adaptation=3.0, tonemap_lowlum=0.21,
                        tonemap_middlegray=1.1, hud_hemi=0.14, sunshafts_value=0.55),
}

# GAMMA's stock grade: what intensity 0 renders.
NEUTRAL_GRADE = dict(grade_r=0.7, grade_g=0.7, grade_b=0.7, saturation=1.0, gamma=1.0,
                     exposure=0.8, sun_lumscale=2.05, sun_lumscale_hemi=0.75,
                     sun_lumscale_amb=0.65, tonemap_adaptation=3.0, tonemap_lowlum=0.21,
                     tonemap_middlegray=1.1, hud_hemi=0.14, sunshafts_value=0.55)

# sss_int is sun-through-a-leaf: high on thin spring growth, near zero on bare branches.
# Specular rises in winter (wet, icy) and falls in dry summer.
FLORA = {
    "spring": dict(spec_grass=0.40, spec_grass_wet=0.55, spec_trees=0.45,
                   spec_trees_wet=0.60, sss_int=2.80, sss_color=0.85),
    "summer": dict(spec_grass=0.30, spec_grass_wet=0.45, spec_trees=0.35,
                   spec_trees_wet=0.50, sss_int=2.50, sss_color=0.75),
    "autumn": dict(spec_grass=0.38, spec_grass_wet=0.55, spec_trees=0.42,
                   spec_trees_wet=0.58, sss_int=1.80, sss_color=0.60),
    "winter": dict(spec_grass=0.50, spec_grass_wet=0.60, spec_trees=0.50,
                   spec_trees_wet=0.62, sss_int=0.80, sss_color=0.40),
    "winter_snow": dict(spec_grass=0.58, spec_grass_wet=0.66, spec_trees=0.54,
                        spec_trees_wet=0.66, sss_int=0.55, sss_color=0.30),
}

# Autumn is the foggy season in Polesia. Height is capped at 20 by the engine, so the
# seasonal spread is mostly in density. Ice fog in deep winter takes no sun color.
FOG = {
    "spring": dict(fog_height=15.0, fog_density=2.2, fog_suncolor=0.060, fog_scattering=1.0),
    "summer": dict(fog_height=10.0, fog_density=1.4, fog_suncolor=0.020, fog_scattering=0.9),
    "autumn": dict(fog_height=20.0, fog_density=3.0, fog_suncolor=0.080, fog_scattering=1.0),
    "winter": dict(fog_height=17.0, fog_density=2.4, fog_suncolor=0.015, fog_scattering=1.0),
    "winter_snow": dict(fog_height=14.0, fog_density=2.9, fog_suncolor=0.010, fog_scattering=1.0),
}

# ssfx_wetness_multiplier (build-up speed, drying speed). The thaw makes spring wet;
# summer dries almost as fast as it wets. This is the only runtime lever on wetness;
# puddle size and reflectivity are compile-time shader defines.
WET = {
    "spring": dict(wet_buildup=2.60, wet_dry=0.18),
    "summer": dict(wet_buildup=1.10, wet_dry=1.20),
    "autumn": dict(wet_buildup=1.80, wet_dry=0.35),
    "winter": dict(wet_buildup=1.30, wet_dry=0.25),
    "winter_snow": dict(wet_buildup=0.60, wet_dry=0.20),
}

# Spring is the windiest (thaw storms), summer the calmest. Frozen branches are stiff:
# low trunk and bend values in winter. SSS defaults: grass (9.5, 1.4, 1.5, 0.4),
# trees (11.0, 0.15, 0.5), min 0.1.
WIND = {
    "spring": dict(wind_grass_speed=11.0, wind_grass_turbulence=1.8, wind_grass_push=1.8,
                   wind_grass_wave=0.50, wind_trees_speed=12.0, wind_trees_trunk=0.18,
                   wind_trees_bend=0.65, wind_min_speed=0.15),
    "summer": dict(wind_grass_speed=8.0, wind_grass_turbulence=1.1, wind_grass_push=1.2,
                   wind_grass_wave=0.35, wind_trees_speed=9.0, wind_trees_trunk=0.12,
                   wind_trees_bend=0.40, wind_min_speed=0.06),
    "autumn": dict(wind_grass_speed=10.5, wind_grass_turbulence=1.7, wind_grass_push=1.7,
                   wind_grass_wave=0.45, wind_trees_speed=11.5, wind_trees_trunk=0.17,
                   wind_trees_bend=0.60, wind_min_speed=0.12),
    "winter": dict(wind_grass_speed=9.0, wind_grass_turbulence=1.3, wind_grass_push=1.3,
                   wind_grass_wave=0.30, wind_trees_speed=10.0, wind_trees_trunk=0.10,
                   wind_trees_bend=0.30, wind_min_speed=0.10),
    "winter_snow": dict(wind_grass_speed=7.5, wind_grass_turbulence=1.1, wind_grass_push=1.0,
                        wind_grass_wave=0.22, wind_trees_speed=9.5, wind_trees_trunk=0.10,
                        wind_trees_bend=0.24, wind_min_speed=0.10),
}

# Engine ranges, from the SSS MCM sliders. The console rejects a whole command when any
# component is out of range, so the generator refuses to emit one.
RANGES = {
    "saturation": (0.0, 2.0), "gamma": (0.0, 2.0), "exposure": (0.0, 2.0),
    "spec_grass": (0.0, 1.0), "spec_grass_wet": (0.0, 1.0),
    "spec_trees": (0.0, 1.0), "spec_trees_wet": (0.0, 1.0),
    "sss_int": (0.0, 10.0), "sss_color": (0.0, 1.0),
    "fog_height": (0.0, 20.0), "fog_density": (0.0, 5.0),
    "fog_suncolor": (0.0, 1.0), "fog_scattering": (0.0, 1.0),
    "wind_grass_speed": (0.1, 13.0), "wind_grass_turbulence": (0.1, 3.0),
    "wind_grass_push": (0.1, 3.0), "wind_grass_wave": (0.1, 1.0),
    "wind_trees_speed": (0.1, 13.0), "wind_trees_trunk": (0.1, 0.3),
    "wind_trees_bend": (0.1, 2.0), "wind_min_speed": (0.0, 1.0),
    "wet_buildup": (0.1, 20.0), "wet_dry": (0.1, 20.0),
}

SEASONS = ["spring", "summer", "autumn", "winter", "winter_snow"]

# What intensity 0 renders, beyond the grade: SSS's shipped flora and wind defaults,
# GAMMA's own fog tuning (20 / 2 / 0.015) and wetness (1.4 / 0.5).
NEUTRAL_EXTRA = dict(
    spec_grass=0.30, spec_grass_wet=0.21, spec_trees=0.30, spec_trees_wet=0.21,
    sss_int=2.00, sss_color=1.00,
    fog_height=20.0, fog_density=2.0, fog_suncolor=0.015, fog_scattering=1.0,
    wind_grass_speed=9.5, wind_grass_turbulence=1.4, wind_grass_push=1.5,
    wind_grass_wave=0.40, wind_trees_speed=11.0, wind_trees_trunk=0.15,
    wind_trees_bend=0.50, wind_min_speed=0.10,
    wet_buildup=1.40, wet_dry=0.50,
)

PRESET_FILE = {"spring": "Atmos_Spring.ltx", "summer": "Atmos_Summer.ltx",
               "autumn": "Atmos_Autumn.ltx", "winter": "Atmos_Winter.ltx",
               "winter_snow": "Atmos_WinterSnow.ltx", "neutral": "Atmos_Neutral.ltx"}


def scan_preset(path):
    """The grade keys found in one cfg_load preset (lines like `r__saturation 1.13`)."""
    vals = {}
    for ln in io.open(path, encoding="cp1251", errors="replace", newline=""):
        s = ln.strip()
        for var, keys in GRADE_MAP:
            if s.startswith(var + " "):
                nums = re.findall(r"-?\d+\.?\d*", s[len(var):])
                if len(nums) < len(keys):
                    raise SystemExit("%s: %s has %d numbers, need %d"
                                     % (path, var, len(nums), len(keys)))
                for k, n in zip(keys, nums):
                    vals[k] = float(n)
    return vals


def grade_tables(presets_dir):
    """(GRADE, NEUTRAL_GRADE): the embedded tables, or re-read from a presets folder. A
    key a preset omits takes the neutral value, and is reported."""
    if not presets_dir:
        return GRADE, NEUTRAL_GRADE
    neutral = scan_preset(os.path.join(presets_dir, PRESET_FILE["neutral"]))
    grade = {}
    for s in SEASONS:
        vals = scan_preset(os.path.join(presets_dir, PRESET_FILE[s]))
        filled = [k for k in GRADE_KEYS if k not in vals]
        for k in filled:
            vals[k] = neutral[k]
        if filled:
            print("  %-11s not in its preset, filled from neutral: %s" % (s, ", ".join(filled)))
        grade[s] = vals
    return grade, neutral


ORDER = (GRADE_KEYS
         + ["spec_grass", "spec_grass_wet", "spec_trees", "spec_trees_wet",
            "sss_int", "sss_color"]
         + ["fog_height", "fog_density", "fog_suncolor", "fog_scattering"]
         + ["wind_grass_speed", "wind_grass_turbulence", "wind_grass_push",
            "wind_grass_wave", "wind_trees_speed", "wind_trees_trunk",
            "wind_trees_bend", "wind_min_speed"]
         + ["wet_buildup", "wet_dry"])

HEADER = """; Seasons of the Zone - season table
;
; One section per season. Every value the mod sends to the engine comes from here. The
; mod blends between adjacent sections around each season boundary, so a value set here
; is reached at the middle of that season.
;
; The engine rejects a whole console command if any component is out of range, so stay
; inside these:
;   exposure/saturation/gamma  0..2      spec_* / sss_color         0..1
;   sss_int                    0..10     fog_height                 0..20
;   fog_density                0..5      fog_suncolor/scattering    0..1
;   wind_*_speed               0.1..13   wind_grass_turbulence/push 0.1..3
;   wind_grass_wave            0.1..1    wind_trees_trunk           0.1..0.3
;   wind_trees_bend            0.1..2    wind_min_speed             0..1
;   wet_buildup / wet_dry      0.1..20
;
; Generated by _tools/build_seasons_ltx.py. Edit the tables there and regenerate, or edit
; this file directly for a quick test. With GRADE_PRESETS set in seasons_config.py, the
; grade keys are rewritten from those presets at each launch.
"""


CRLF = chr(13) + chr(10)

# The same grades as cfg_load presets, so they can be picked per season on the MCM page,
# cfg_load-ed by hand, or edited in appdata/ beside Atmospherics' own.
PRESET_NAME = {"spring": "Seasons_Spring", "summer": "Seasons_Summer",
               "autumn": "Seasons_Autumn", "winter": "Seasons_Winter",
               "winter_snow": "Seasons_DeepWinter", "neutral": "Seasons_Neutral"}


def preset_text(vals):
    """A cfg_load preset: one console command per line, vectors in parentheses."""
    lines = []
    for var, keys in GRADE_MAP:
        nums = ["%s" % vals[k] for k in keys]
        lines.append(var + " " + ("(" + ", ".join(nums) + ")" if len(nums) > 1 else nums[0]))
    return CRLF.join(lines) + CRLF


def write_presets(grade, neutral, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for s in SEASONS + ["neutral"]:
        vals = neutral if s == "neutral" else grade[s]
        io.open(os.path.join(out_dir, PRESET_NAME[s] + ".ltx"), "w", encoding="cp1251",
                newline="").write(preset_text(vals))
    return len(PRESET_NAME)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--presets", default=None,
                    help="folder of Atmos_<season>.ltx presets to take the grade from")
    a = ap.parse_args()

    grade, neutral = grade_tables(a.presets)
    out = [HEADER]
    for s in SEASONS:
        vals = dict(grade[s])
        vals.update(FLORA[s]); vals.update(FOG[s]); vals.update(WIND[s]); vals.update(WET[s])
        bad = []
        for k, v in vals.items():
            lo_hi = RANGES.get(k)
            if lo_hi and not (lo_hi[0] <= v <= lo_hi[1]):
                bad.append("%s.%s = %s (allowed %s..%s)" % (s, k, v, lo_hi[0], lo_hi[1]))
        if bad:
            raise SystemExit("refusing to emit out-of-range values: " + "; ".join(bad))
        missing = [k for k in ORDER if k not in vals]
        if missing:
            raise SystemExit("%s is missing %s" % (s, ", ".join(missing)))
        out.append("[%s]" % s)
        for k in ORDER:
            out.append("%-22s = %s" % (k, vals[k]))
        out.append("")

    nvals = dict(neutral)
    nvals.update(NEUTRAL_EXTRA)
    out.append("; Intensity 0 renders this; intensity 1 renders the season.")
    out.append("[neutral]")
    for k in ORDER:
        out.append("%-22s = %s" % (k, nvals[k]))
    out.append("")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    body = (chr(13) + chr(10)).join(chr(10).join(out).split(chr(10)))
    io.open(a.out, "w", encoding="cp1251", newline="").write(body)
    print("  wrote %s" % a.out)
    print("  %d seasons x %d keys" % (len(SEASONS), len(ORDER)))
    pdir = os.path.join(os.path.dirname(os.path.abspath(a.out)), "seasons_presets")
    print("  wrote %d presets to %s" % (write_presets(grade, neutral, pdir), pdir))


if __name__ == "__main__":
    main()
