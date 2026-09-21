"""Which mods this install stages per season. The only file to edit.

Empty is the default and is fine: the in-engine layer needs nothing here. These tables
add the launch-time layers, which use mods you install yourself.

  TOGGLE_MODS    mods switched on or off per season. Nothing is copied. `above` is the
                 mod yours must outrank; find it with `season.py whowins <file>`.
  LAYOUT         mods whose contents are restaged per season from their archive, for
                 mods that ship one folder per season. Gigabytes move; prefer TOGGLE_MODS.
  SOUND_SRC      the ambience mod whose presets are gated by season. Must be the mod
                 that wins those files.
"""

# mod folder -> archive in downloads/, and per season the option folders to overlay
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
            # Aydin ships four sets, so both winters stage the same textures; INVERNO
            # (below) is what separates them.
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

TOGGLE_MODS = {
    # Must outrank both Aydin mods (shared terrain textures) and Atmospherics and SSS
    # (it carries settings_screenspace_TERRAIN.h and _PUDDLES.h). 388 sits above all of
    # them.
    "INVERNO Winter Textures (seasonal)": {
        "seasons": ("winter", "winter_snow"),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    # Patchy ground while the snow arrives; deep winter gets full cover from the base
    # INVERNO. Overrides only ground detail textures, so it sits above INVERNO.
    "INVERNO Partly Snowy (winter only)": {
        "seasons": ("winter",),
        "above": "INVERNO Winter Textures (seasonal)",
    },
    "Winter Loading Screens (seasonal)": {
        "seasons": ("winter", "winter_snow"),
        "above": "282- GAMMA Loading Screens - CS Eden",
    },
    # A pack that ships several seasonal variants of the SAME files is the easy case:
    # install each variant as its own mod and give it one season here. Only one can
    # ever be mounted, so they cannot fight each other. C Consciousness ships four -
    # Spring, Summer, Autumn and Dead - as the same 202 texture paths repainted.
    #
    # Its grass placement (23 level.details) does not change with the season, so that
    # is a separate mod that stays mounted year-round and is not listed here at all.
    # These four sit below INVERNO, so snow still wins both winters, and above the
    # Aydin packs, which is what 388 anchors.
    "CCon Spring (seasonal)": {
        "seasons": ("spring",),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    "CCon Summer (seasonal)": {
        "seasons": ("summer",),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    "CCon Autumn (seasonal)": {
        "seasons": ("autumn",),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    # Bare, dead foliage under INVERNO's snow.
    "CCon Dead (seasonal)": {
        "seasons": ("winter", "winter_snow"),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },

    # PanceRide's Summer and Autumn sets were listed here until 2026-09-20, on the same
    # anchor, until CCon replaced them: two seasons and textures only, against four
    # seasons plus placement. Swapping one pack for another is editing these entries -
    # nothing is copied and nothing else has to change.

    # Ground fog over standing water: thaw in spring, cool nights over warm water in
    # autumn. Collides with nothing; the anchor only keeps it with the visual mods.
    "Swamp Ground Fog (seasonal)": {
        "seasons": ("spring", "autumn"),
        "above": "Atmospherics 2.69 RC7.2 SSS24",
    },
    # Deep winter only: `winter` is first snowfall on bare ground. Four mods ship
    # actor/step sounds; this one is the highest.
    "Winter Footsteps (seasonal)": {
        "seasons": ("winter_snow",),
        "above": "472- Dark Signal Amplified Footsteps Extended - Shrike & oleh5230",
    },
    # Above both INVERNO mods, not just the map mods: INVERNO ships its own grayscale
    # textures/ui/ui_global_map.dds and is on in the same seasons.
    "Winter PDA Maps (seasonal)": {
        "seasons": ("winter", "winter_snow"),
        "above": "INVERNO Partly Snowy (winter only)",
    },
}

SOUND_SRC = "304- Dark Signal Weather and Ambiance Audio - Shrike"


# --- the calendar ----------------------------------------------------------------
#
# The five seasons are the calendar this ships with, not a limit. Add your own.
# Full reference: docs/SCHEDULING.md
#
# PERIODS are BASE periods: they partition the year alongside the seasons, so
# exactly one is ever active, and each runs until the next one starts.
#
#   PERIODS = {
#       "mud_season": (3, 20),        # name: (month, day) it begins
#   }
#
# EVENTS OVERLAY whatever period they land in - they are added to it, not swapped
# for it, so a Christmas event keeps deep winter's snow underneath.
#
#   EVENTS = {
#       "christmas":  ((12, 24), (12, 26)),   # (start), (end), both inclusive
#       "halloween":  ((10, 31), (10, 31)),   # one day is fine
#       "twelvetide": ((12, 26), (1, 6)),     # start after end wraps the year
#   }
#
# Scope a mod to either with the same key you use for a season:
#
#   TOGGLE_MODS = {
#       "Christmas Lights": {"when": ("christmas",), "above": "..."},
#   }
PERIODS = {}
EVENTS = {}
