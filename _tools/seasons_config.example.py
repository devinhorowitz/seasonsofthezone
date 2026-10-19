"""A worked example: the setup these tools were made on, every table described.

Your own settings go in seasons_config.py, next to this file. configure.bat makes that
file and edits it for you - its window, its commands and its presets - and you can edit
it by hand as well: the tool keeps what you write and rewrites only the entries it
changes. This file is only here to read. The same setup loads into configure.bat as the
"GAMMA example" preset.

With every table empty, the seasonal atmosphere still runs; the tables add what play.bat
changes at launch, using mods you install yourself. The full reference is
docs/CONFIGURING.md in the mod's folder: in MO2, right-click Seasons of the Zone and
choose Open in Explorer.

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
  WEATHER_PLACE  where the real weather comes from; None is Chornobyl.
  OWN_SEASONS    seasons of your own: name: ((m, d) first, (m, d) last), a week or
                 longer, up to 52, each laid over the season it falls in, as an event is.
  SPELLS         short stretches that start by chance: name: {"in": (seasons...),
                 "chance": percent a day, "days": (fewest, most), 1 to 6, "as": the season
                 it brings, or None}. See docs/SCHEDULING.md.
  MCM_SETTINGS   other mods' MCM options that follow the season: "page/option": {name:
                 its value then, ..., "else": the rest of the year}. play.bat sets them
                 in MCM's saved options before the game starts.
  SEASON_LUTS    a LUT for a season: season: (pack, the option folder in it or None,
                 percent). The pack is an archive in MO2's downloads folder or a mod's
                 folder; the season's color grade moves that far toward its LUT. play.bat
                 builds the mod Seasonal LUT from them.
  SEASON_ACCENTS True for Seasons' own color accents, built into each season's LUT on
                 top of its pack's or the game's, or season: {accent: value} of your own.
                 play.bat builds them into Seasonal LUT; they need numpy.
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
    # ever be mounted, so they cannot fight each other. Grizzly's CCon Overhaul (v0.3,
    # since 2026-10-10; its entries end this table) ships four - Spring, Summer, Autumn
    # and Dead - over the same tree and grass texture paths. The four sit below INVERNO,
    # so snow still wins the winters, and above the Aydin packs, which is what 388
    # anchors. RedDead, its Red Forest set, goes over the three warm sets, as its
    # installer lays it. Barks and the grass bump maps come with every season, so they
    # stay mounted year-round and are not listed here.
    #
    # Grass placement doesn't change with the season, except that the overhaul's
    # Overgrown option (grass on roads too) runs spring to autumn over CCon Grass
    # Placement. That one stays mounted year-round and is byte-identical to the
    # overhaul's Default option, so the winters keep the roads clear.
    #
    # Earlier packs on these entries: PanceRide's Summer and Autumn sets until
    # 2026-09-20; then C Consciousness 0.71's four sets, with Grizzly's Overgrown v0.6
    # over them spring to autumn from 2026-10-02. Swapping one pack for another is
    # editing these entries - nothing is copied and nothing else has to change.

    # Ground fog over standing water: the thaw and the spring after it, and cool nights
    # over warm water in autumn. Collides with nothing; the anchor only keeps it with
    # the visual mods.
    "Swamp Ground Fog (seasonal)": {
        "when": ("spring", "autumn", "late_winter"),
        "above": "Atmospherics 2.69 RC7.6 SSS24",
    },
    # Deep winter only: `winter` is first snowfall on bare ground. Four mods ship
    # actor/step sounds; this one is the highest.
    "Winter Footsteps (seasonal)": {
        "when": ("winter_snow",),
        "above": "MovementSFX 2026.09.27 - oleh5230",
    },
    # Above both INVERNO mods, not just the map mods: INVERNO ships its own grayscale
    # textures/ui/ui_global_map.dds and is on in the same seasons.
    "Winter PDA Maps (seasonal)": {
        "seasons": ("winter", "winter_snow", "late_winter"),
        "above": "INVERNO Partly Snowy (winter only)",
    },
    "SSS24 ICE Module": {
        "when": ("winter_snow",),
        "above": "190- Screen Space Shaders 24 - Ascii1457",
    },
    "Grizzly's CCon Spring (seasonal)": {
        "when": ("spring",),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    "Grizzly's CCon Summer (seasonal)": {
        "when": ("summer",),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    "Grizzly's CCon Autumn (seasonal)": {
        "when": ("autumn",),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    "Grizzly's CCon Dead (seasonal)": {
        "when": ("winter", "winter_snow", "late_winter"),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    "Grizzly's CCon RedDead (seasonal)": {
        "when": ("spring", "summer", "autumn"),
        "above": "Grizzly's CCon Spring (seasonal)",
    },
    "Grizzly's CCon Overgrown Placement (seasonal)": {
        "when": ("spring", "summer", "autumn"),
        "above": "CCon Grass Placement",
    },
    "Winter Mutants (seasonal)": {
        "when": ("winter", "winter_snow", "late_winter"),
        "above": "G.A.M.M.A. Large Files",
    },
    "Winter Main Menu (seasonal)": {
        "when": ("winter", "winter_snow", "late_winter"),
        "above": "G.A.M.M.A. New Main Menu",
    },
    "No Rain in Winter (seasonal)": {
        "when": ("winter", "winter_snow"),
        "above": "Weather Expansion for Atmospherics",
    },
    "Winterized Zone Maps (seasonal)": {
        "when": ("winter", "winter_snow", "late_winter"),
        "above": "Winter PDA Maps (seasonal)",
    },
    "Midwinter Trees (seasonal)": {
        "when": ("winter", "late_winter"),
        "above": "INVERNO Winter Textures (seasonal)",
    },
    "Snow Asphalt (seasonal)": {
        "when": ("winter_snow", "late_winter"),
        "above": "INVERNO Partly Snowy (winter only)",
    },
    "Thaw Ground (late winter)": {
        "when": ("late_winter",),
        "above": "INVERNO Partly Snowy (winter only)",
    },
    "Frosted Winter Mask Overlay (seasonal)": {
        "when": ("winter", "winter_snow"),
        "above": "190- Screen Space Shaders 24 - Ascii1457",
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

# Seasonal LUTs: {season: (source, option, percent)}. A season's color grade moves from the
# game's LUT toward the LUT in `source` - an archive in MO2's downloads folder or a mod's
# folder - in its `option` folder (None when gamedata is at the top), by `percent`.
# play.bat builds the mod Seasonal LUT from them. configure.bat writes this.
SEASON_LUTS = {
    "spring": ("Kumo's LUT Assortment v1.1.1.7z", "00 data/LUT - Fovea Memory", 50),
    "summer": ("Kumo's LUT Assortment v1.1.1.7z", "00 data/LUT - Fovea Objective", 50),
    "autumn": ("Kumo's Cinegraphy Vol. 1.7z", "00 data/EASTMAN", 30),
    "winter": ("Kumo's LUT Assortment v1.1.1.7z", "00 data/LUT - Iris", 60),
    "winter_snow": ("Kumo's LUT Assortment v1.1.1.7z", "00 data/LUT - Stalker 1979", 60),
    "late_winter": ("Kumo's Cinegraphy Vol. 1.7z", "00 data/FLIC", 50),
}

# Seasonal accents: True for Seasons' own, built into each season's LUT on top of its pack's
# (CONFIGURING.md's SEASON_ACCENTS). Tuned as ReShade presets in the game on 2026-10-18.
SEASON_ACCENTS = True
