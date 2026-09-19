"""Apply the Seasons of the Zone snowfall gate to your own copy of INVERNO's script.

WHAT THIS IS
  Project I.N.V.E.R.N.O's snowfall addon plays its particles off the WEATHER alone,
  with no notion of season, so in an install that runs all year it snows in September
  the moment the right weather comes round. This edits your copy so the particles are
  resolved through Seasons of the Zone's calendar first: snow only in the two winters
  and thinner in the first of them, seeds in spring, leaves in autumn, dust in the dry
  months, each easing in and out across the turn.

WHY A SCRIPT AND NOT THE FINISHED FILE
  yawm_snowfall.script is not mine. Its lineage is Yet Another Winter Mod
  (Daedalus-Prime), refactored by demonized, edited by Fabio Conte / crazewastaken for
  Project I.N.V.E.R.N.O, with particles by S.e.m.i.t.o.n.e. for The Arrival. Shipping a
  patched copy would be redistributing their work, so this ships the changes instead
  and applies them to the copy you already installed.

USE
    python apply_seasonal_snowfall.py
        find the script under mods/ and patch it
    python apply_seasonal_snowfall.py "<path to yawm_snowfall.script>"
        patch one named file
    python apply_seasonal_snowfall.py --revert
        put the original back from the .orig backup

  The original is copied to yawm_snowfall.script.orig before anything is written, and
  an existing backup is never overwritten - so the first copy taken is always the
  pristine one, however many times this is run.
"""
import io
import os
import shutil
import sys

# Anchors. Short on purpose: these locate the insertion points and are the only
# fragments of the original this file contains. Leading whitespace is never matched,
# because that addon mixes tabs and spaces and a user's copy may differ.
A_HEADER = "function on_game_start()"
A_UPDATE = "function actor_on_update()"
A_HOOK = 'switch_particles(weather_to_particles[weather], inside_pos, is_inside)'

BANNER = """\
--==============================================================================================
-- MODIFIED FOR "Seasons of the Zone" - the ONLY change is a seasonal gate.
--
-- As shipped this snows whenever the WEATHER matches, with no notion of season:
--     weather_to_particles[level.get_weather()]
-- so in an install that runs all year it snows in September the moment w_partly1 comes
-- round. The gate below defers to zzz_seasons_of_the_zone.snow_factor(), which is 0
-- outside the winter months and ramps in and out across the turn, so snowfall follows
-- the real calendar instead of appearing overnight.
--
-- If Seasons of the Zone is absent the gate is inert and this behaves exactly as shipped.
--
-- level_weathers.script, which this addon also ships, is DELIBERATELY NOT INSTALLED:
-- INVERNO's copy is an older fork missing Atmospherics' weather weights, progression
-- matrix and MCM starting-weather work.
--==============================================================================================
"""

HELPERS = """\
local function seasons_weight()
    if not (zzz_seasons_of_the_zone and zzz_seasons_of_the_zone.snow_factor) then
        return 1.0                      -- standalone: behave exactly as shipped
    end
    local ok, f = pcall(zzz_seasons_of_the_zone.snow_factor)
    return (ok and f) or 0.0
end

-- SEASONAL PARTICLES.
--
-- This addon is a weather-driven environmental particle system; snow is a minority of
-- it. Two earlier versions of this gate were both wrong in opposite directions:
--
--   v1 returned early whenever snow_factor() was 0, which switched off wind-blown
--      leaves, seeds and the whole dynamic-fog layer for ten months a year.
--   v2 fixed that by gating ONLY snow - and then dandelion and maple seeds drifted
--      through September. Pale, slow and small against an overcast sky, they read as
--      light snow, which is exactly what the user reported.
--
-- Ambience is seasonal too; it just has different seasons from snow. Each particle
-- declares which seasons it belongs to and takes the blended weight of those, so every
-- transition eases rather than switching.
-- DIAGNOSTIC. The script is silent when it works, which made "is that snow or seeds?"
-- impossible to answer from the log - so it now names whatever it turns on, whenever the
-- set changes. Reverse map from particle object to a readable name.
local PARTICLE_NAME = {
    [snow_particle_dust]   = "dust",      [snow_particle_leaves] = "leaves",
    [snow_particle_flakes] = "SNOWflakes",[snow_particle_light]  = "SNOWlight",
    [snow_particle_heavy]  = "SNOWheavy", [snow_particle_front]  = "SNOWblizzard",
    [snow_particle_rainl]  = "SNOWrainL", [snow_particle_rainr]  = "SNOWrainR",
    [snow_particle_seed1]  = "seeds1",    [snow_particle_seed2]  = "seeds2",
    [snow_particle_storm]  = "leaves_wind",
    [snow_particle_fog1]   = "fog_mist",  [snow_particle_fog2]   = "fog_dust",
    [snow_particle_fog3]   = "fog_light",
}

local last_report = nil

local function report(tbl, weather, weight)
    local on = {}
    for k, v in pairs(tbl) do
        if v then on[#on + 1] = PARTICLE_NAME[k] or "?" end
    end
    table.sort(on)
    local line = string.format("%s w=%.2f : %s", tostring(weather), weight,
                               (#on > 0) and table.concat(on, ", ") or "(nothing)")
    if line ~= last_report then
        last_report = line
        printf("%s", "[snowfall] " .. line)
    end
end

local SEASON_OF = {
    -- Drifting seeds: SPRING ONLY. Allowing summer too kept them alive through the 29%
    -- summer trace of a mid-September blend - which is what the user saw drifting and
    -- took for snow. Dandelion clocks are a May phenomenon, not a September one.
    [snow_particle_seed1] = {"spring"},
    [snow_particle_seed2] = {"spring"},
    -- falling and wind-blown leaves: autumn, with some in summer storms
    [snow_particle_leaves] = {"autumn"},
    [snow_particle_storm]  = {"autumn", "summer"},
    -- dry dust: the hot, dry months
    [snow_particle_dust]   = {"summer", "autumn"},
    -- FOG PARTICLES ARE SEASONAL TOO. Leaving them unclassified was the last gap: they
    -- played in every weather of every season, and in a clear sky they are the ONLY thing
    -- on screen - pale motes drifting, which is what still read as flurries in autumn
    -- after the seeds were fixed. Assigned by what each effect actually is, and matching
    -- the fog density curve this mod already drives (autumn 3.0 > winter_snow 2.9 >
    -- winter 2.4 > spring 2.2 > summer 1.4):
    [snow_particle_fog1] = {"spring", "autumn"},              -- mist: thaw and radiation fog
    [snow_particle_fog2] = {"summer"},                        -- airborne dust: dry air only
    -- fog3 (lanforse
og_light) is REMOVED, not season-gated. It was the last particle
    -- playing in clear skies and the one that still read as flurries. It is a PARTICLE
    -- haze, and this mod already drives real volumetric fog per season through ssfx_fog
    -- (autumn 20/3.0/0.08, deep winter 14/2.9/0.010) - so it was duplicating, in a worse
    -- form, something we already have. An empty season list never meets MIN_WEIGHT.
    [snow_particle_fog3] = {},
}

-- Snow: allowed only in the two winters, and thinner in the first of them.
--   tier 1  flakes only            - the thin first snows of November
--   tier 2  whatever the table says - the depth of January
local SNOW_HEAVY_AT = 0.80
local SNOW_TIER = {
    [snow_particle_flakes] = 1,
    [snow_particle_light]  = 2,
    [snow_particle_rainl]  = 2,
    [snow_particle_rainr]  = 2,
    [snow_particle_heavy]  = 2,
    [snow_particle_front]  = 2,
}

local MIN_WEIGHT = 0.50   -- a particle plays only while its season(s) are the MAJORITY.
                          -- At 0.15 the 29% summer trace of a mid-September blend was
                          -- still enough to keep summer particles on - first the seeds,
                          -- then the dust. These are binary on/off, not faded, so a
                          -- minority share should not switch them on at full strength;
                          -- 0.50 makes them change hands at the midpoint of the turn.

local function seasonal(tbl, weight)
    if not tbl then return tbl end
    local tier = 0
    if weight >= SNOW_HEAVY_AT then tier = 2 elseif weight > 0.02 then tier = 1 end

    local mix
    if zzz_seasons_of_the_zone and zzz_seasons_of_the_zone.season_mix then
        local ok, m = pcall(zzz_seasons_of_the_zone.season_mix)
        if ok then mix = m end
    end

    local out = {}
    for k, v in pairs(tbl) do
        local need = SNOW_TIER[k]
        if need then
            out[k] = (v and tier >= need) and true or false
        elseif mix and SEASON_OF[k] then
            local w = 0
            for _, s in ipairs(SEASON_OF[k]) do w = w + (mix[s] or 0) end
            out[k] = (v and w >= MIN_WEIGHT) and true or false
        else
            out[k] = v          -- fog, and anything unclassified: weather decides
        end
    end
    return out
end
"""


def _nl(raw):
    """Match the file's own line endings; a mod folder can hold either."""
    crlf = chr(13) + chr(10)
    return crlf if crlf in raw else chr(10)


def _find():
    """Look for the script under a GAMMA install, starting from this file's folder."""
    here = os.path.dirname(os.path.abspath(__file__))
    for root in (here, os.path.dirname(here), os.getcwd()):
        mods = os.path.join(root, "mods")
        if not os.path.isdir(mods):
            continue
        hits = []
        for name in sorted(os.listdir(mods)):
            p = os.path.join(mods, name, "gamedata", "scripts",
                             "yawm_snowfall.script")
            if os.path.isfile(p):
                hits.append(p)
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            print("  more than one copy - name the one to patch:")
            for p in hits:
                print("    " + p)
            raise SystemExit(2)
    return None


def revert(path):
    bak = path + ".orig"
    if not os.path.isfile(bak):
        raise SystemExit("  no backup at %s - nothing to revert" % bak)
    shutil.copy2(bak, path)
    print("  restored  %s" % path)
    print("  from      %s" % bak)
    return 0


def patch(path):
    raw = io.open(path, encoding="latin-1", newline="").read()
    nl = _nl(raw)
    lines = raw.splitlines()

    if "zzz_seasons_of_the_zone" in raw:
        print("  already patched - nothing to do")
        print("  (%s)" % path)
        return 0

    # Verify this is the file we think it is BEFORE touching anything. A patcher that
    # half-applies is worse than one that refuses.
    def only(anchor):
        hits = [i for i, l in enumerate(lines) if l.strip().startswith(anchor)]
        if len(hits) != 1:
            raise SystemExit(
                "  expected exactly one %r, found %d - this does not look like\n"
                "  INVERNO's yawm_snowfall.script, so nothing was changed."
                % (anchor, len(hits)))
        return hits[0]

    i_header = only(A_HEADER)
    i_update = only(A_UPDATE)
    hook = [i for i, l in enumerate(lines) if l.strip() == A_HOOK]
    if len(hook) != 1:
        raise SystemExit(
            "  expected exactly one call to switch_particles(weather_to_particles"
            "[weather], ...),\n  found %d - nothing was changed." % len(hook))
    i_hook = hook[0]

    # Keep the caller's own indentation on the lines that replace theirs.
    src = lines[i_hook]
    indent = src[:len(src) - len(src.lstrip())]
    replacement = [
        indent + "local w = seasons_weight()",
        indent + "local resolved = seasonal(weather_to_particles[weather], w)",
        indent + "report(resolved, weather, w)",
        indent + "switch_particles(resolved, inside_pos, is_inside)",
    ]

    # Build back to front so the earlier indices stay valid.
    out = list(lines)
    out[i_hook:i_hook + 1] = replacement
    out[i_update:i_update] = HELPERS.splitlines() + [""]
    out[i_header:i_header] = BANNER.splitlines() + [""]

    bak = path + ".orig"
    if not os.path.isfile(bak):
        shutil.copy2(path, bak)
        print("  backed up %s" % bak)
    else:
        print("  backup already exists, left alone: %s" % bak)

    io.open(path, "w", encoding="latin-1", newline="").write(nl.join(out))
    print("  patched   %s" % path)
    print("  +%d lines: seasonal gate, particle season table, diagnostics"
          % (len(out) - len(lines)))
    print()
    print("  Snowfall now follows the calendar. With Seasons of the Zone absent the")
    print("  gate is inert and the addon behaves exactly as shipped.")
    return 0


def main():
    args = [a for a in sys.argv[1:]]
    want_revert = "--revert" in args
    args = [a for a in args if not a.startswith("--")]

    path = args[0] if args else _find()
    if not path:
        raise SystemExit(
            "  could not find yawm_snowfall.script under mods/.\n"
            "  Put this file in your GAMMA root, or name the script:\n"
            "    python apply_seasonal_snowfall.py "
            "\"mods/<the addon>/gamedata/scripts/yawm_snowfall.script\"")
    if not os.path.isfile(path):
        raise SystemExit("  no such file: %s" % path)

    raise SystemExit(revert(path) if want_revert else patch(path))


main()
