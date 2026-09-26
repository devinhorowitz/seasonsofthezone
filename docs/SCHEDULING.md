# The calendar

Seasons of the Zone is two halves that share a name and nothing else.

The **seasonal atmosphere** blends twenty console values — color, fog, wind, wetness —
across the date, in game. It is about seasons, it needs no configuration, and it is not
what this page is about.

The **seasonal mods** half is a scheduler, run by `play.bat` before the game starts. It maps
today's date to a set of names, and mods declare which names they belong to. Nothing in it
is seasonal. The six seasons are the set it ships with, and you can add your own.

---

## The model

Two kinds of name.

**Base periods** partition the year. Exactly one is active on any date: a period runs from
its start until the next one begins, and the last of the year wraps around into January.
The six seasons are base periods. Their starts can move and seasons can be turned off,
with `configure.bat`'s Seasons step or `CALENDAR` in the config (see
[CONFIGURING.md](CONFIGURING.md#calendar)); a mod on only in seasons that are off is never
switched on.

**Events** overlay. An event is a window with a start and an end, or a rule like "every
weekend", and it does not displace the period it lands in — it is added to it.

**Seasons of your own** overlay the same way: a named stretch of the year, a week or
longer, up to 52 of them. They are made in the setup's Seasons step.

**Spells** overlay, and can do one thing nothing else can: bring another season for a few
days. A spell starts by chance on a day of the seasons it names, runs 1 to 6 days, and, if
it brings a season, that season is the base period while it lasts. See
[Seasons of your own and spells](#seasons-of-your-own-and-spells).

**Weather** overlays too. `play.bat` fetches the real Chornobyl forecast at each launch, and
three kinds of day are added to the list when they happen: `freezing` (the low is 0°C or
below), `thaw` (it freezes overnight and climbs above 0°C by afternoon) and `heat` (the
high reaches 28°C). Without `play.bat`, or without an internet connection, none of them is
on.

A date therefore resolves to a **list**: the base period, then every season of your own,
spell, event and kind of weather covering it.

```
Dec 20  ->  ["winter_snow"]
Dec 25  ->  ["winter_snow", "christmas"]
Dec 28  ->  ["winter_snow", "twelvetide"]
Aug 12  ->  ["summer", "Wormhole season"]
Jul 14  ->  ["winter", "Summer frost"]      a spell that brings winter to summer
```

A mod is switched on if **any** name in its `when` is in that list. That one rule is the
whole scheduler, and the reason Christmas does not cost you your snow.

---

## Declaring periods and events

Both live in `_tools/seasons_config.py`, and both are optional.

```python
PERIODS = {
    # name: (month, day) that it starts. Runs until the next period begins.
    "high_summer": (7, 1),
}

EVENTS = {
    # a window of dates: ((start month, day), (end month, day)) - both inclusive
    "christmas":  ((12, 24), (12, 26)),
    "halloween":  ((10, 31), (10, 31)),   # a single day is fine
    "twelvetide": ((12, 26), (1, 6)),     # start after end wraps the year

    # or a rule: a day is in the event when it is everything the rule names
    "weekend":      {"weekdays": ("sat", "sun")},
    "payday":       {"days": (1, 15, -1)},              # -1 is the month's last day
    "first_monday": {"weekdays": ("mon",), "weeks": (1,)},
    "friday_13th":  {"weekdays": ("fri",), "days": (13,)},
    "winter_weekends": {"weekdays": ("sat", "sun"), "within": ((12, 1), (2, 28))},
}
```

A rule takes any of five parts:

| Part | What it holds |
|---|---|
| `weekdays` | days of the week: `"mon"` to `"sun"` |
| `days` | days of the month, 1 to 31; -1 is the last, -2 the one before |
| `weeks` | with `weekdays`, which of them in the month: 1 is the first, -1 the last |
| `months` | only in these months, 1 to 12 |
| `within` | only inside this window of dates |

A rule nothing can meet, such as the 31st of February, is refused rather than left to never
fire.

Then name them in a mod's `when` exactly as you would a season:

```python
TOGGLE_MODS = {
    "Christmas Lights": {"when": ("christmas",), "above": "..."},
    "Spooky Props":     {"when": ("halloween",), "above": "..."},
}
```

`when` accepts any mix of seasons, periods, events and weather. `seasons` is the original
spelling of the same key and still works — configurations written for earlier versions
need no edit.

Names are checked at startup. A typo names itself and stops the run before anything is
staged, rather than silently never firing.

Events can also be made without editing the file: **New event...** in `configure.bat`,
or from a command prompt in your GAMMA folder (`python` in place of `py` if that is how
your Python starts):

```
py _tools\configure.py event christmas 12-24 12-26
py _tools\configure.py event weekend --weekdays weekends
py _tools\configure.py event payday --days 1 15 last
py _tools\configure.py event first_monday --weekdays mon --weeks first
py _tools\configure.py event winter_weekends --weekdays sat sun --between 12-01 02-28
py _tools\configure.py add "Christmas Lights" --when christmas
```

---

## Recipes

**A Christmas ceasefire.** Build a mod that sets faction relations to neutral, put it on
for a `christmas` event, and it is in force for those days and gone afterwards. The winter
textures stay mounted throughout.

```python
EVENTS = {"christmas": ((12, 24), (12, 26))}
TOGGLE_MODS = {"Peace On Earth": {"when": ("christmas",), "above": "..."}}
```

**A single day.** Start and end on the same date.

**A window across new year.** Put the start after the end: `((12, 26), (1, 6))`.

**Weekends.** `{"weekdays": ("sat", "sun")}`. The day is decided when `play.bat` stages
the launch, so a weekend mod comes on at the first launch on a Saturday, and a session that
runs past midnight on Sunday keeps it until the next launch.

**An anniversary.** The Chornobyl disaster was April 26th. A one-day event can swap in a
loading screen set, an ambient track, or a spawn table.

**Layering two events.** They stack. December 25th inside a `twelvetide` window that also
covers it resolves to three names, and every mod on for any of them is switched on.

**Stretching a season.** If you want a longer autumn, do not fight the shipped table — add
a base period. `PERIODS` entries sit in the same partition as the seasons and are sorted
with them by start date.

---

## Seasons of your own and spells

Both are made in `configure.bat`'s Seasons step, in the advanced editor, or from a command
prompt, and both can be written by hand:

```python
OWN_SEASONS = {
    # name: (first day, last day), both counted, a week or longer
    "Wormhole season": ((8, 1), (8, 31)),
}

SPELLS = {
    # "in": the seasons it can start in - yours too
    # "chance": the percent chance it starts on each of those days
    # "days": how long it runs, a number or (fewest, most), 1 to 6
    # "as": the season it brings, or None to leave the season as it is
    "Summer frost": {"in": ("summer",), "chance": 3, "days": (1, 2), "as": "winter"},
    "Wormhole storm": {"in": ("Wormhole season",), "chance": 10, "days": 2, "as": None},
}

TOGGLE_MODS = {
    "Rostok Wormhole": {"when": ("Wormhole season", "Wormhole storm"), "above": "..."},
}
```

**A season of your own** runs on top of the season it falls in, as an event does: its
mods come on for its days, and the season's own mods stay on. It is a week or longer - a
shorter stretch is an event - and there can be up to 52, as many weeks as the year has. A
name can be anything up to 24 characters that isn't a season, event, period or kind of
weather already, so "Wormhole season" is fine as it is.

**A spell** starts by chance. On each day of the seasons it names, it draws a number from
the date and its name; if the number falls under its chance, it starts that day and runs
for its days, past the end of the season if it has to; a start while it runs, or on the
day after, keeps it going. With `"as"`, the season it brings takes over while it lasts:
that season's mods come on, the calendar's season's go off, and `play.bat` tells the game,
whose light, weather and PDA follow it until its last day. With `"as": None` the season
stays, and only the mods on during the spell come on.

The same date and name always draw the same number, on every machine and every launch, so
a spell can't come and go between launches on the same day, and two players with the same
spell see it on the same days. `configure.bat` says how often each comes on average:
3% a day in Polesia's summer is about 3 a year. No one sees a spell coming: the Forecast
page doesn't show them.

An MCM pin fixes the season, and a spell doesn't change a pinned season; the mods on
during it still come on. `season.py status --season` works the same way.

**Seasons of your own and spells meet what they fall in.** When two seasonal mods ship the
same file and are on at the same time, the setup asks whose the game should use. For a
mod in a season of your own or a spell, "at the same time" is worked out from the dates, so
a Wormhole season mod is asked about against the summer mods under it.

---

## What it does not do yet

The model above invites all of these.

- **No moveable feasts.** Easter moves; a fixed window cannot follow it.
- **No MCM page for events.** The per-mod checkboxes in MCM are grouped by base period,
  because that is what has a page. A mod on for an event is switched by the calendar and can
  be held back with the global texture switch, but not on its own.
- **Nothing reacts mid-session.** Everything here is decided before the game starts, for
  the reason in the README: X-Ray mounts the virtual file system once. A date that rolls
  over while you play takes effect at the next launch.
- **One base period at a time.** Base periods partition the year by design. If you want two
  things true at once, one of them is an event, a season of your own or a spell.
- **Seasons of your own and spells aren't on the dial or the MCM pages.** The dial shows
  the calendar's seasons; a spell that brings a season shows as that season in game.

---

## Checking it

**Preview the next launch** in `configure.bat` shows what `play.bat` would switch, today or
in any season, before you save. From a command prompt, `season.py status` prints the date,
the resolved period, and every seasonal mod with whether it is on today. To see a
different date's answer without waiting for it, pin the base period:

```
py _tools\season.py status --season winter
```

A pin fixes the **base** period only. Events still resolve against the real date, so
pinning summer in December does not cancel a Christmas event — which is usually what you
want when you are testing one layer and not the other.
