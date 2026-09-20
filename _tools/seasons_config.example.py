"""Which mods this install stages per season. The only file to edit.

Empty is the default and is fine: the in-engine layer needs nothing here. These tables
add the launch-time layers, which use mods you install yourself.

  TOGGLE_MODS    mods switched on or off per season. Nothing is copied. `above` is the
                 mod yours must outrank; find it with `season.py whowins <file>`.
  LAYOUT         mods whose contents are restaged per season from their archive, for
                 mods that ship one folder per season. Gigabytes move; prefer TOGGLE_MODS.
  SOUND_SRC      the ambience mod whose presets are gated by season. Must be the mod
                 that wins those files.
  GRADE_PRESETS  {season or "neutral": cfg preset file}. The season's color grade is
                 taken from that preset at each launch instead of the shipped table.
                 Presets are found in the game's appdata/ or in an enabled mod's
                 appdata/ folder (Atmospherics ships Atmos_Cold/Neutral/Warm there).
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
    # PanceRide's Summer and Autumn editions are one mod with the foliage repainted, so
    # the Zone keeps its shape across the boundary. They share no file with 388; the
    # anchor works because 388 sits above Atmospherics, SSS 24 and the Aydin base pack.
    # If 388 ever moves below those, re-anchor these on whichever is highest.
    "PanceRide Grass and Trees - Summer (seasonal)": {
        "seasons": ("summer",),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
    "PanceRide Grass and Trees - Autumn (seasonal)": {
        "seasons": ("autumn",),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
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

# The presets the shipped table was tuned in. With these set, retuning a preset in
# appdata/ changes the season at the next launch.
GRADE_PRESETS = {
    "spring": "Atmos_Spring.ltx",
    "summer": "Atmos_Summer.ltx",
    "autumn": "Atmos_Autumn.ltx",
    "winter": "Atmos_Winter.ltx",
    "winter_snow": "Atmos_WinterSnow.ltx",
    "neutral": "Atmos_Neutral.ltx",
}
