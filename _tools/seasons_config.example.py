"""Which mods this install stages per season - the ONE file to edit for your own setup.

season.py is the engine and knows nothing about your folder names. Everything here is a
description of one particular mod set, so adapting the system to a different install means
editing this file and nothing else.

RUNNING WITH NOTHING CONFIGURED IS FINE AND IS THE DEFAULT.
  Leave LAYOUT and TOGGLE_MODS empty and SOUND_SRC as None, and you still get the whole
  in-engine layer: seasonal light and colour, fog, wind, wetness, gated snowfall, the
  calendar dial and the MCM panel. None of that needs a single extra download. The tables
  below only add the launch-time layers - swapping terrain textures, toggling seasonal
  mods, and gating ambient sound - which need mods you supply yourself.

THE THREE TABLES
  LAYOUT       mods whose CONTENTS are restaged per season by extracting a different
               option out of the original archive. Expensive (gigabytes copied on a
               season change) and only worth it for a mod that ships one folder per
               season, like Aydin's Grass Tweaks.

  TOGGLE_MODS  mods that are simply switched on or off per season by flipping the modlist
               flag. Nothing is copied, so an 11 GB winter texture set costs nothing to
               "swap". This is the cheap mechanism and the one to prefer.

               `above` is the mod this one must outrank. GET THIS RIGHT: MO2 resolves a
               shared file to the HIGHEST enabled mod that ships it, and anchoring on the
               wrong one is silent - the flag flips correctly and nothing changes on
               screen. Find the real winner before you trust a placement.

  SOUND_SRC    the ambient-preset mod to generate seasonal sound gating from. Again, the
               mod that WINS those files, which is not always the obvious one: several
               soundscape mods ship the same presets and only the highest enabled one is
               read.
"""
import os


# mod folder -> {season: [option folder names, in overlay order]}
LAYOUT = {
    "289- Grass Tweaks (reinstall for different options) - Aydin": {
        "archive": "Aydins_Grass_Tweaks_4.0.7z",
        "options": {
            "spring": ["Aydin's Grass Tweaks - SPRING 4.0",
                       "Aydin's Grass Tweaks - SPRING TREES 4.0"],
            "summer": ["Aydin's Grass Tweaks - SUMMER 3.0",
                       "Aydin's Grass Tweaks - SUMMER TREES 3.0"],
            "autumn": ["Aydin's Grass Tweaks - AUTUMN 3.0",
                       "Aydin's Grass Tweaks - AUTUMN TREES 3.0"],
            "winter": ["Aydin's Grass Tweaks - WINTER 3.0",
                       "Aydin's Grass Tweaks - WINTER TREES 3.0"],
            # Aydin ships only four sets, so BOTH winters stage the same textures.
            # They are separated by grade, flora, fog, wind and SNOWFALL, not by
            # terrain. Project I.N.V.E.R.N.O's snow textures are the proper
            # winter_snow layer - phase 2.
            "winter_snow": ["Aydin's Grass Tweaks - WINTER 3.0",
                            "Aydin's Grass Tweaks - WINTER TREES 3.0"],
        },
    },
    "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag": {
        "archive": "Aydins_Grass_Tweaks_SSS_Terrain_LOD_compatiblity.rar",
        "options": {
            "spring": ["Spring"], "summer": ["Summer"],
            "autumn": ["Autumn"], "winter": ["Winter"],
            "winter_snow": ["Winter"],
        },
    },
}

# Mods enabled only in certain seasons, by flipping the modlist flag rather than by
# copying files. That is the whole reason an 11 GB winter texture set is practical to
# swap at all: nothing moves on disk, MO2 simply stops mounting it.
#
# PLACEMENT MATTERS. INVERNO must outrank (sit above) both seasonally-staged Aydin mods,
# whose terrain_*.dds it overlaps in 38 places, and also Atmospherics and SSS24, because
# it carries settings_screenspace_TERRAIN.h and _PUDDLES.h. Anything above the Aydin LOD
# patch satisfies all three.
TOGGLE_MODS = {
    "INVERNO Winter Textures (seasonal)": {
        "seasons": ("winter", "winter_snow"),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    # WINTER ONLY, not winter_snow. This is what finally separates the two winters:
    # patchy ground while the snow is arriving, full cover once it holds. It overrides
    # only the ground DETAIL textures, so it must outrank the base INVERNO mod, which
    # stays enabled through both winters for terrain, flora and levels.
    "INVERNO Partly Snowy (winter only)": {
        "seasons": ("winter",),
        "above": "INVERNO Winter Textures (seasonal)",
    },
    "Winter Loading Screens (seasonal)": {
        "seasons": ("winter", "winter_snow"),
        "above": "282- GAMMA Loading Screens - CS Eden",
    },
    # PanceRide's Summer and Autumn editions: one mod with the foliage repainted. They
    # share 553 of their paths (85 autumn-only, 11 summer-only), so the Zone keeps its
    # shape across the 15 September boundary and only its colour changes. Never both at
    # once, so the shared paths never contest.
    #
    # They ship build_details.dds for all 24 levels - grass PLACEMENT, not just textures -
    # and sit above BOTH Aydin mods. Aydin still fills the 45 files PanceRide does not
    # ship, and stays seasonally consistent underneath because season.py stages it to the
    # matching season. Aydin remains the sole source for spring and both winters, where
    # PanceRide has no edition. The SSS terrain LOD patch has ZERO overlap and survives
    # intact.
    # INVARIANT: these two share ZERO files with their anchor. The anchor works only
    # because 388 sits above Atmospherics, SSS 24 and the Aydin base pack (289). If 388
    # ever moves below any of those, re-anchor PanceRide on whichever of them is highest.
    "PanceRide Grass and Trees - Summer (seasonal)": {
        "seasons": ("summer",),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    "PanceRide Grass and Trees - Autumn (seasonal)": {
        "seasons": ("autumn",),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    # Ground fog over standing water is a SHOULDER-SEASON thing: saturated thaw ground in
    # spring, then cool nights over warmer water in autumn. Thin in high summer, and both
    # winters freeze the swamps. Self-contained - scripts, particles and textures are all
    # namespaced under semitone/ - so it collides with nothing and the anchor is only
    # about keeping it with the other visual mods.
    "Swamp Ground Fog (seasonal)": {
        "seasons": ("spring", "autumn"),
        "above": "Atmospherics 2.69 RC7.2 SSS24",
    },
    # DEEP WINTER ONLY. `winter` is first snowfall on bare ground - Partly Snowy gives it
    # patchy cover - and crunching through snow that is not there would be wrong.
    #
    # Anchored on the mod that ACTUALLY wins these files, which is not the obvious one.
    # Four enabled mods ship actor/step sounds: "472- Dark Signal Amplified Footsteps
    # Extended" (~209), "275- Dark Signal Footsteps" (~211), "G.A.M.M.A. Footsteps" (~348)
    # and "20- EFT footsteps and tinnitus" (~838). The highest wins, so anchoring on
    # G.A.M.M.A. Footsteps would have buried this under Dark Signal - the same mistake
    # that made the Winter PDA Maps toggle look broken.
    "Winter Footsteps (seasonal)": {
        "seasons": ("winter_snow",),
        "above": "472- Dark Signal Amplified Footsteps Extended - Shrike & oleh5230",
    },
    # Must outrank BOTH map mods. GAMMA ships two that overlap almost completely - "358-
    # Global Map Rework" (line ~517) and "26- High Res PDA Maps" (line ~833), 31 shared
    # textures and not one byte-identical - and the higher one wins. Anchoring on the
    # lower one alone put this BELOW Global Map Rework, so the snow maps never rendered
    # and the toggle looked broken while the modlist flag was flipping correctly.
    # ...AND above INVERNO Winter Textures, which ships its own near-greyscale
    # textures/ui/ui_global_map.dds and is on in the same seasons. Anchoring on the map mod
    # alone put this below INVERNO, so the coloured winter global map never showed. No
    # enabled mod above INVERNO ships any of these files, so the higher anchor costs nothing.
    "Winter PDA Maps (seasonal)": {
        "seasons": ("winter", "winter_snow"),
        "above": "INVERNO Partly Snowy (winter only)",
    },
}

SOUND_SRC = "304- Dark Signal Weather and Ambiance Audio - Shrike"
