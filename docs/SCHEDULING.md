# The calendar

Seasons of the Zone is two halves that share a name and nothing else.

The **in-engine** half blends twenty console values — colour, fog, wind, wetness — across
the date. It is about seasons, it needs no configuration, and it is not what this page is
about.

The **launch-time** half is a scheduler. It maps today's date to a set of names, and mods
declare which names they belong to. Nothing in it is seasonal. The six seasons are the
set it ships with, and you can add your own.

---

## The model

Two kinds of name.

**Base periods** partition the year. Exactly one is active on any date: a period runs from
its start until the next one begins, and the last of the year wraps around into January.
The six seasons are base periods. Their starts can move and seasons can be turned off,
with `configure.bat`'s Seasons tab or `CALENDAR` in the config (see
[CONFIGURING.md](CONFIGURING.md#calendar)); a mod scoped to a season that is off is never
staged.

**Events** overlay. An event is a window with a start and an end, and it does not displace
the period it lands in — it is added to it.

A date therefore resolves to a **list**: the base period, then every event covering it.

```
Dec 20  ->  ["winter_snow"]
Dec 25  ->  ["winter_snow", "christmas"]
Dec 28  ->  ["winter_snow", "twelvetide"]
```

A mod is staged if **any** name it is scoped to is in that list. That one rule is the whole
scheduler, and the reason Christmas does not cost you your snow.

---

## Declaring periods and events

Both live in `_tools/seasons_config.py`, and both are optional.

```python
PERIODS = {
    # name: (month, day) that it starts. Runs until the next period begins.
    "high_summer": (7, 1),
}

EVENTS = {
    # name: ((start month, day), (end month, day)) - both inclusive
    "christmas":  ((12, 24), (12, 26)),
    "halloween":  ((10, 31), (10, 31)),   # a single day is fine
    "twelvetide": ((12, 26), (1, 6)),     # start after end wraps the year
}
```

Then scope a mod to them exactly as you would a season:

```python
TOGGLE_MODS = {
    "Christmas Lights": {"when": ("christmas",), "above": "..."},
    "Spooky Props":     {"when": ("halloween",), "above": "..."},
}
```

`when` accepts any mix of base periods and events. `seasons` is the original spelling of
the same key and still works — configurations written for earlier versions need no edit.

Names are checked at startup. A typo names itself and stops the run before anything is
staged, rather than silently never firing.

Events can also be made without editing the file: **New event...** in `configure.bat`,
or from a command prompt in your GAMMA folder:

```
python _tools\configure.py event christmas 12-24 12-26
python _tools\configure.py add "Christmas Lights" --when christmas
```

---

## Recipes

**A Christmas ceasefire.** Build a mod that sets faction relations to neutral, scope it to
a `christmas` event, and it is in force for those days and gone afterwards. The winter
textures stay mounted throughout.

```python
EVENTS = {"christmas": ((12, 24), (12, 26))}
TOGGLE_MODS = {"Peace On Earth": {"when": ("christmas",), "above": "..."}}
```

**A single day.** Start and end on the same date.

**A window across new year.** Put the start after the end: `((12, 26), (1, 6))`.

**An anniversary.** The Chornobyl disaster was April 26th. A one-day event can swap in a
loading screen set, an ambient track, or a spawn table.

**Layering two events.** They stack. December 25th inside a `twelvetide` window that also
covers it resolves to three names, and every mod scoped to any of them is staged.

**Stretching a season.** If you want a longer autumn, do not fight the shipped table — add
a base period. `PERIODS` entries sit in the same partition as the seasons and are sorted
with them by start date.

---

## What it does not do yet

Worth stating plainly, because the model above invites all of these.

- **No weekday or nth-of-month recurrence.** Windows are `(month, day)` pairs, so "every
  weekend" and "the first Monday of the month" cannot be expressed. This is the most
  obvious next step.
- **No moveable feasts.** Easter moves; a fixed window cannot follow it.
- **No MCM page for events.** The per-mod ticks in MCM are grouped by base period, because
  that is what has a page. An event-scoped mod is staged by the calendar and can be held
  back with the global texture switch, but not individually.
- **Nothing reacts mid-session.** Everything here is decided before the game starts, for
  the reason in the README: X-Ray mounts the virtual file system once. A date that rolls
  over while you play takes effect at the next launch.
- **One base period at a time.** Base periods partition the year by design. If you want two
  things true at once, one of them is an event.

---

## Checking it

`season.py status` prints the date, the resolved period, and every scoped mod with whether
it is staged today. To see a different date's answer without waiting for it, pin the base
period:

```
python _tools/season.py status --season winter
```

A pin fixes the **base** period only. Events still resolve against the real date, so
pinning summer in December does not cancel a Christmas event — which is usually what you
want when you are testing one layer and not the other.
