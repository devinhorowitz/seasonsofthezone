"""Add the Seasons of the Zone seasonal layer to your copy of INVERNO's snowfall script.

  INVERNO's snowfall addon plays its particles off the weather alone, so it snows in
  September. This edits your copy so the particles follow the calendar: snow only in
  the two winters and lighter in the first, seeds in spring, leaves in autumn, dust
  in the dry months.

  yawm_snowfall.script is not mine (Yet Another Winter Mod by Daedalus-Prime,
  refactored by demonized, edited by Fabio Conte for INVERNO; particles by
  S.e.m.i.t.o.n.e.), so this ships the changes and applies them to the copy you
  installed. Use the standalone "Snowfall (light + Dynamic Fog)" addon: the v1.08.4
  FOMOD's Light/Heavy Snowfall options install a cut-down script without the seed,
  leaf and fog particles the layer uses, and this refuses that copy.

  Where the addon sits in MO2 does not matter. Keep it enabled all year; the gate
  decides what plays. The addon also ships level_weathers.script, an older weather
  manager that beats yours from any position - remove it. This warns when it sees
  one; --disable-weathers renames it. Check with:
      python _tools/season.py whowins scripts/level_weathers.script

USE
    python apply_seasonal_snowfall.py
        find the script under mods/ and patch it
    python apply_seasonal_snowfall.py "<path to yawm_snowfall.script>"
        patch one named file
    python apply_seasonal_snowfall.py --disable-weathers
        also rename level_weathers.script beside it to .disabled
    python apply_seasonal_snowfall.py --revert
        put the original back from the .orig backup

  The original is copied to yawm_snowfall.script.orig before anything is written, and
  an existing backup is never overwritten - so the first copy taken is always the
  pristine one, however many times this is run.
"""
import io
import os
import re
import shutil
import sys

# Anchors. Short on purpose: these locate the insertion points and are the only
# fragments of the original this file contains. Leading whitespace is never matched,
# because that addon mixes tabs and spaces and a user's copy may differ.
A_HEADER = "function on_game_start()"
A_UPDATE = "function actor_on_update()"
A_HOOK = 'switch_particles(weather_to_particles[weather], inside_pos, is_inside)'

# Every particle local the seasonal tables key on. A copy that does not declare all of
# them would take the patch cleanly and then die at load with "table index is nil".
NEEDS = ['snow_particle_dust', 'snow_particle_flakes', 'snow_particle_fog1', 'snow_particle_fog2', 'snow_particle_fog3', 'snow_particle_front', 'snow_particle_heavy', 'snow_particle_leaves', 'snow_particle_light', 'snow_particle_rainl', 'snow_particle_rainr', 'snow_particle_seed1', 'snow_particle_seed2', 'snow_particle_storm']

BANNER = r"""--==============================================================================================
-- MODIFIED FOR "Seasons of the Zone" - a seasonal layer is inserted; nothing original is removed.
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
-- If this addon's download also shipped level_weathers.script, that file must NOT be
-- mounted above your weather-manager mod: it is an older fork of the weather manager
-- and replaces the newer one silently. Remove it. See apply_seasonal_snowfall.py.
--==============================================================================================
"""

HELPERS = r"""local function seasons_weight()
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
    -- fog3 (lanforse/fog_light) is REMOVED, not season-gated. It was the last particle
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
    """Match the file's own dominant line ending; a mod folder can hold either."""
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


def warn_weathers(path, disable=False):
    """The one genuine load-order hazard, see the header. Returns True if present."""
    lw = os.path.join(os.path.dirname(path), "level_weathers.script")
    if not os.path.isfile(lw):
        return False
    if disable:
        os.replace(lw, lw + ".disabled")
        print("  disabled  %s" % lw)
        print("            (renamed to .disabled; rename it back to undo)")
        return True
    print()
    print("  ** WARNING: this module also ships level_weathers.script **")
    print("     %s" % lw)
    print("     It is an older fork of the weather manager. Mounted above your weather")
    print("     mod it replaces the newer one silently - dead MCM weather options, no")
    print("     log line. Delete it, hide it in MO2, or re-run with --disable-weathers.")
    print("     Check:  python _tools/season.py whowins scripts/level_weathers.script")
    return True


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
        warn_weathers(path)
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

    # Refuse a copy that lacks a particle the seasonal tables key on (the FOMOD Light /
    # Heavy variants). Patched, it would load as far as the season table and die there.
    missing = [n for n in NEEDS
               if not re.search(r"^\s*local\s+" + n + r"\b", raw, re.M)
               and not re.search(r"^\s*" + n + r"\s*=", raw, re.M)]
    if missing:
        raise SystemExit(
            "  this copy of yawm_snowfall.script does not declare %s.\n"
            "  It looks like INVERNO's FOMOD Light/Heavy Snowfall variant, which has no"
            " seed,\n  leaf or fog particles - the seasonal layer keys on them and would"
            " fail at load.\n  Use the standalone \"Snowfall (light + Dynamic Fog)\""
            " addon. Nothing was changed." % ", ".join(missing))

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

    # Build back to front so the earlier indices stay valid. The helper block gets one
    # blank line on each side whatever the original has there: INVERNO's file runs
    # `local inside_pos` straight into `function actor_on_update()` with no gap.
    out = list(lines)
    out[i_hook:i_hook + 1] = replacement
    lead = [] if (i_update > 0 and out[i_update - 1] == "") else [""]
    out[i_update:i_update] = lead + HELPERS.splitlines() + [""]
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
    warn_weathers(path)
    return 0


def main():
    args = [a for a in sys.argv[1:]]
    want_revert = "--revert" in args
    disable_weathers = "--disable-weathers" in args
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

    if want_revert:
        raise SystemExit(revert(path))
    rc = patch(path)
    if disable_weathers:
        warn_weathers(path, disable=True)
    raise SystemExit(rc)


main()
