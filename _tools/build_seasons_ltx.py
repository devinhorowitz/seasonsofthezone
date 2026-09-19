"""Generate the packaged mod's season table.

Grade values are LIFTED FROM the validated Atmos_*.ltx presets rather than retyped,
so the packaged mod ships exactly what was tuned and tested in play. Flora, fog and
wind are authored here (they have no preset to source from).
"""
import io
import os
import re

APPDATA = r"D:\ANOMALY\appdata"
OUT = r"D:\GAMMA\mods\Seasons of the Zone\gamedata\configs\seasons_of_the_zone.ltx"

# console var in the preset  ->  ltx key in our mod
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

# Authored. See the header comment in the generated file for the reasoning.
FLORA = {
    "spring": dict(spec_grass=0.40, spec_grass_wet=0.55, spec_trees=0.45,
                   spec_trees_wet=0.60, sss_int=2.80, sss_color=0.85),
    "summer": dict(spec_grass=0.30, spec_grass_wet=0.45, spec_trees=0.35,
                   spec_trees_wet=0.50, sss_int=2.50, sss_color=0.75),
    "autumn": dict(spec_grass=0.38, spec_grass_wet=0.55, spec_trees=0.42,
                   spec_trees_wet=0.58, sss_int=1.80, sss_color=0.60),
    "winter": dict(spec_grass=0.50, spec_grass_wet=0.60, spec_trees=0.50,
                   spec_trees_wet=0.62, sss_int=0.80, sss_color=0.40),
    # snow-covered: wet, glassy specular; almost no light through a bare branch
    "winter_snow": dict(spec_grass=0.58, spec_grass_wet=0.66, spec_trees=0.54,
                        spec_trees_wet=0.66, sss_int=0.55, sss_color=0.30),
}

FOG = {  # height capped at 20.0 by the engine - see RANGES in the script
    "spring": dict(fog_height=15.0, fog_density=2.2, fog_suncolor=0.060, fog_scattering=1.0),
    "summer": dict(fog_height=10.0, fog_density=1.4, fog_suncolor=0.020, fog_scattering=0.9),
    "autumn": dict(fog_height=20.0, fog_density=3.0, fog_suncolor=0.080, fog_scattering=1.0),
    "winter": dict(fog_height=17.0, fog_density=2.4, fog_suncolor=0.015, fog_scattering=1.0),
    # ice fog over snow: lower, denser, and utterly colourless
    "winter_snow": dict(fog_height=14.0, fog_density=2.9, fog_suncolor=0.010, fog_scattering=1.0),
}

# ssfx_wetness_multiplier (buildup_speed, dry_speed, 0). How fast surfaces take on water
# and how fast they give it up - both 0.1..20.0, shipped 1.0/0.3, this install runs 1.4/0.5.
#
# This is the only RUNTIME lever on wetness. Puddle geometry (G_PUDDLES_SIZE,
# _REFLECTIVITY, _RIPPLES...) is compile-time #defines in settings_screenspace_PUDDLES.h
# with no console equivalent, which is why INVERNO ships a modified header rather than a
# setting. Wetness is the part that can follow the calendar.
WET = {
    # thaw: meltwater everywhere and nothing dries - the defining look of a Polesian spring
    "spring": dict(wet_buildup=2.60, wet_dry=0.18),
    # hot and dry: wet only while it is actually raining, then gone
    "summer": dict(wet_buildup=1.10, wet_dry=1.20),
    # damp, fog-fed, slow to dry
    "autumn": dict(wet_buildup=1.80, wet_dry=0.35),
    "winter": dict(wet_buildup=1.30, wet_dry=0.25),
    # frozen: almost nothing is liquid, and what is does not evaporate
    "winter_snow": dict(wet_buildup=0.60, wet_dry=0.20),
}

# SSS defaults for reference: grass (9.5, 1.4, 1.5, 0.4) trees (11.0, 0.15, 0.5) min 0.1
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
    # buried grass barely moves; frozen branches are the stiffest of the year
    "winter_snow": dict(wind_grass_speed=7.5, wind_grass_turbulence=1.1, wind_grass_push=1.0,
                        wind_grass_wave=0.22, wind_trees_speed=9.5, wind_trees_trunk=0.10,
                        wind_trees_bend=0.24, wind_min_speed=0.10),
}

# engine-enforced, from the SSS MCM sliders; a generated value outside these would be
# rejected wholesale by the console, so the builder refuses to emit one
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
}

SEASONS = ["spring", "summer", "autumn", "winter", "winter_snow"]

# The "no seasons" reference point, used by the MCM Intensity slider: 0 renders exactly
# this, 1 renders the full seasonal value, anything between is a lerp. Grade comes from
# Atmos_Neutral.ltx; flora and wind are the SSS shipped defaults; fog is GAMMA'S OWN MCM
# tuning (20 / 2 / 0.015) rather than the SSS default (8 / 1.3 / 0.1), because GAMMA's is
# what this install actually plays with and is therefore the honest "off" state.
NEUTRAL_EXTRA = dict(
    spec_grass=0.30, spec_grass_wet=0.21, spec_trees=0.30, spec_trees_wet=0.21,
    sss_int=2.00, sss_color=1.00,
    fog_height=20.0, fog_density=2.0, fog_suncolor=0.015, fog_scattering=1.0,
    wind_grass_speed=9.5, wind_grass_turbulence=1.4, wind_grass_push=1.5,
    wind_grass_wave=0.40, wind_trees_speed=11.0, wind_trees_trunk=0.15,
    wind_trees_bend=0.50, wind_min_speed=0.10,
    wet_buildup=1.40, wet_dry=0.50,        # what this install currently runs
)


def _scan(path):
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


PRESET_FILE = {"spring": "Atmos_Spring.ltx", "summer": "Atmos_Summer.ltx",
               "autumn": "Atmos_Autumn.ltx", "winter": "Atmos_Winter.ltx",
               # INVERNO's own grade, authored FOR its snow textures: neutral grading that
               # lets white ground carry the look, rather than our blue-tinted pre-snow winter.
               "winter_snow": "Atmos_WinterSnow.ltx"}


def read_preset(season, neutral):
    """Grade values for one season, with Atmos_Neutral filling any gap.

    The presets are not uniform: Atmos_Spring.ltx omits r2_sunshafts_value, so today
    `cfg_load atmos_spring` leaves sunshafts at whatever the previous preset set - the
    result depends on load order. The packaged mod sets every value explicitly, so a
    missing one falls back to GAMMA's neutral baseline and the season becomes
    deterministic. Fallbacks are reported, never silent.
    """
    p = os.path.join(APPDATA, PRESET_FILE[season])
    vals = _scan(p)
    filled = []
    for _, keys in GRADE_MAP:
        for k in keys:
            if k not in vals:
                vals[k] = neutral[k]
                filled.append(k)
    return vals, filled


ORDER = ([k for _, ks in GRADE_MAP for k in ks]
         + ["spec_grass", "spec_grass_wet", "spec_trees", "spec_trees_wet",
            "sss_int", "sss_color"]
         + ["fog_height", "fog_density", "fog_suncolor", "fog_scattering"]
         + ["wind_grass_speed", "wind_grass_turbulence", "wind_grass_push",
            "wind_grass_wave", "wind_trees_speed", "wind_trees_trunk",
            "wind_trees_bend", "wind_min_speed"]
         + ["wet_buildup", "wet_dry"])

HEADER = """; Seasons of the Zone - season parameter table
;
; One section per season. Every value the mod sends to the engine comes from here, so
; this file is the whole tuning surface: edit it, reload a save, done. No Lua changes.
;
; The mod BLENDS between two adjacent sections around each season boundary, so a value
; you set here is reached at the middle of that season and eased into before it. Because
; a blend of two in-range values is always itself in range, hand-edits stay safe as long
; as each individual value is legal.
;
; RANGES ARE ENFORCED BY THE ENGINE, NOT SUGGESTIONS. X-Ray rejects the WHOLE console
; command if ANY component is out of range - it does not clamp - and the only trace is
; "~ Invalid syntax in call to '<cmd>'" in the log. The mod clamps on the way out and
; says so loudly, but the sane move is to stay inside the documented bounds:
;
;   exposure/saturation/gamma  0..2      spec_* / sss_color         0..1
;   sss_int                    0..10     fog_height                 0..20  (hard cap)
;   fog_density                0..5      fog_suncolor/scattering    0..1
;   wind_*_speed               0.1..13   wind_grass_turbulence/push 0.1..3
;   wind_grass_wave            0.1..1    wind_trees_trunk           0.1..0.3
;   wind_trees_bend            0.1..2    wind_min_speed             0..1
;
; Grade values are lifted verbatim from the Atmos_*.ltx presets validated in play.
; Flora, fog and wind are authored:
;   flora  sss_int is sun-through-a-leaf: high on thin spring growth, near zero on bare
;          winter branches. Specular rises in winter (wet/icy) and falls in dry summer.
;   fog    autumn is the foggy season in Polesia - cool nights over damp warm ground.
;          Height is pinned at the engine's 20.0 ceiling, so seasonal spread rides on
;          density, which has headroom to 5.0.
;   wind   spring is the windiest (thaw storms), summer the calmest (stagnant hot air).
;          Winter's trees_trunk/bend are LOW on purpose: frozen branches are stiff.
;
; GENERATED by _tools/build_seasons_ltx.py - regenerate rather than hand-merging if the
; Atmos presets change.
"""


def main():
    neutral = _scan(os.path.join(APPDATA, "Atmos_Neutral.ltx"))
    out = [HEADER]
    for s in SEASONS:
        vals, filled = read_preset(s, neutral)
        if filled:
            print("  %-7s not defined in its preset, filled from Atmos_Neutral: %s"
                  % (s, ", ".join("%s=%s" % (k, vals[k]) for k in filled)))
        vals.update(FLORA[s]); vals.update(FOG[s]); vals.update(WIND[s])
        vals.update(WET[s])
        bad = []
        for k, v in vals.items():
            lo_hi = RANGES.get(k)
            if lo_hi and not (lo_hi[0] <= v <= lo_hi[1]):
                bad.append("%s.%s = %s (allowed %s..%s)" % (s, k, v, lo_hi[0], lo_hi[1]))
        if bad:
            raise SystemExit("refusing to emit out-of-range values: " + "; ".join(bad))
        out.append("[%s]" % s)
        for k in ORDER:
            out.append("%-22s = %s" % (k, vals[k]))
        out.append("")

    nvals = dict(neutral)
    nvals.update(NEUTRAL_EXTRA)
    out.append("; Intensity 0 renders this; intensity 1 renders the season. Not a season -")
    out.append("; the mod never selects [neutral] by date, it only blends toward it.")
    out.append("[neutral]")
    for k in ORDER:
        out.append("%-22s = %s" % (k, nvals[k]))
    out.append("")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    body = (chr(13) + chr(10)).join("\n".join(out).split("\n"))
    io.open(OUT, "w", encoding="cp1251", newline="").write(body)
    print("  wrote %s" % OUT)
    print("  %d seasons x %d keys" % (len(SEASONS), len(ORDER)))


main()
