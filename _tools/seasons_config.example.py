"""A worked example: the setup these tools were made on, each table filled in.

Your own settings go in seasons_config.py, next to this file. configure.bat makes that
file and edits it for you - its window, its commands and its presets - and you can edit
it by hand as well: the tool keeps what you write and rewrites only the entries it
changes. This file is only here to read. The same setup loads into configure.bat as the
"GAMMA example" preset.

With every table empty, the seasonal atmosphere still runs; the tables add what play.bat
changes at launch, using mods you install yourself. The full reference is
docs/CONFIGURING.md.

  TOGGLE_MODS    seasonal mods: each is enabled in the seasons it lists and disabled the
                 rest of the year. Nothing is copied. `above` is the mod it wins over,
                 which configure.bat finds from the files the two share; to check one,
                 `season.py whowins <file> --for "<your mod>"`.
  LAYOUT         texture sets: mods restaged from their archive each season, for mods
                 that ship one folder per season. Gigabytes move; prefer TOGGLE_MODS.
  SOUND_SRC      the ambience mod whose sound channels are cut back by season. It has to
                 be the mod that wins those files.
  PERIODS        base periods of your own, alongside the seasons: name: (month, day) it
                 starts. Each runs until the next one begins.
  EVENTS         windows laid over whatever period they land in, so an event keeps the
                 season under it: name: ((m, d) start, (m, d) end), both inclusive, and a
                 start after its end wraps the year. Or a rule, like
                 {"weekdays": ("sat", "sun")}. See docs/SCHEDULING.md.
  CALENDAR       the day each season starts, and which are on; None is Polesia's six.
  NAMES          names of your own for the seasons; None keeps the usual ones.
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
            # Aydin ships four sets, so all three winters stage the same textures;
            # INVERNO (below) is what separates them.
            "winter_snow": ["Aydin's Grass Tweaks - WINTER 3.0",
                            "Aydin's Grass Tweaks - WINTER TREES 3.0"],
            "late_winter": ["Aydin's Grass Tweaks - WINTER 3.0",
                            "Aydin's Grass Tweaks - WINTER TREES 3.0"],
        },
    },
    "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag": {
        "archive": "Aydins_Grass_Tweaks_SSS_Terrain_LOD_compatiblity.rar",
        "options": {
            "spring": ["Spring"], "summer": ["Summer"],
            "autumn": ["Autumn"], "winter": ["Winter"],
            "winter_snow": ["Winter"], "late_winter": ["Winter"],
        },
    },
}

TOGGLE_MODS = {
    # Must outrank both Aydin mods (shared terrain textures) and Atmospherics and SSS
    # (it carries settings_screenspace_TERRAIN.h and _PUDDLES.h). 388 sits above all of
    # them.
    "INVERNO Winter Textures (seasonal)": {
        "seasons": ("winter", "winter_snow", "late_winter"),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    # Patchy ground while the snow arrives and again while it melts; deep winter gets
    # full cover from the base INVERNO. Overrides only ground detail textures, so it
    # sits above INVERNO.
    "INVERNO Partly Snowy (winter only)": {
        "seasons": ("winter", "late_winter"),
        "above": "INVERNO Winter Textures (seasonal)",
    },
    "Winter Loading Screens (seasonal)": {
        "seasons": ("winter", "winter_snow", "late_winter"),
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
    # Bare, dead foliage under INVERNO's snow, until the green-up.
    "CCon Dead (seasonal)": {
        "seasons": ("winter", "winter_snow", "late_winter"),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },

    # PanceRide's Summer and Autumn sets were listed here until 2026-09-20, on the same
    # anchor, until CCon replaced them: two seasons and textures only, against four
    # seasons plus placement. Swapping one pack for another is editing these entries -
    # nothing is copied and nothing else has to change.

    # Ground fog over standing water: the thaw and the spring after it, and cool nights
    # over warm water in autumn. Collides with nothing; the anchor only keeps it with
    # the visual mods.
    "Swamp Ground Fog (seasonal)": {
        "seasons": ("late_winter", "spring", "autumn"),
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
        "seasons": ("winter", "winter_snow", "late_winter"),
        "above": "INVERNO Partly Snowy (winter only)",
    },
}

SOUND_SRC = "304- Dark Signal Weather and Ambiance Audio - Shrike"


# --- the calendar ----------------------------------------------------------------
#
# The six seasons are the calendar this ships with, not a limit. Add your own.
# Full reference: docs/SCHEDULING.md
#
# PERIODS are BASE periods: they partition the year alongside the seasons, so
# exactly one is ever active, and each runs until the next one starts.
#
#   PERIODS = {
#       "high_summer": (7, 1),        # name: (month, day) it begins
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
