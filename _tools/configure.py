#!/usr/bin/env python3
r"""Set up Seasons of the Zone without editing seasons_config.py by hand.

configure.bat opens the window. The same changes can be made with commands, run in the
GAMMA folder (use python in place of py if that is how your Python starts):

  py _tools\configure.py list                    the seasonal mods, events and calendar
  py _tools\configure.py add "<mod>" --when winter "deep winter" [--above "<mod>"]
  py _tools\configure.py remove "<mod>"
  py _tools\configure.py event <name> <MM-DD> [<MM-DD>]
  py _tools\configure.py event <name> --weekdays sat sun
  py _tools\configure.py event <name> --days 1 15 last [--months dec jan]
  py _tools\configure.py event <name> --weekdays mon --weeks first [--between 12-01 02-28]
  py _tools\configure.py event <name> --remove
  py _tools\configure.py season                  your own seasons
  py _tools\configure.py season "<name>" <MM-DD> <MM-DD>    add or change one, a week or
                                                longer; it runs on top of the season it
                                                falls in
  py _tools\configure.py season "<name>" --rename "<new>" | --remove
  py _tools\configure.py spell                   your spells
  py _tools\configure.py spell "<name>" --in summer --chance 3 [--days 1 2] [--as winter]
                                                a short stretch, 1 to 6 days, that starts by
                                                chance; --as is the season it brings
  py _tools\configure.py spell "<name>" --rename "<new>" | --remove
  py _tools\configure.py calendar                when each season starts
  py _tools\configure.py calendar summer=5-1 "deep winter=11-15" [--only]
  py _tools\configure.py calendar --off "late winter" | --on "late winter"
  py _tools\configure.py calendar --dates met | --reset
  py _tools\configure.py name                    what the seasons are called
  py _tools\configure.py name "deep winter" "The Long Cold" | name "deep winter" --reset
  py _tools\configure.py place                   where the real weather comes from
  py _tools\configure.py place "Kyiv" [--pick 2]  look a place up, and take the weather there
  py _tools\configure.py place --at 50.45 30.52 [--name "Home"] | place --reset
  py _tools\configure.py --advanced              the tabbed editor, not the guided setup
  py mods\<the mod>\_tools\configure.py install  put the tools in the GAMMA folder, or
                                                update them there (configure.bat does it
                                                when opened from the mod's folder)
  py _tools\configure.py preset                  the presets there are
  py _tools\configure.py preset save "<name>" [--about "..."] [--parts calendar mods]
  py _tools\configure.py preset load "<name>" [--parts calendar events mods textures]
  py _tools\configure.py preset show "<name>"

Mod names are as MO2's mod list shows them; a name with a space goes in quotes. --above
is the mod a seasonal mod wins over, worked out from the files they share when left out.
Every change is checked with season.py's rules before it is written, and the previous
file is kept as seasons_config.py.bak.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

import config_edit as ce
import season

EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
DAY_BOX = re.compile(r"^\s*\d{1,2}\s*$", re.ASCII)


def label(p, cal=None):
    """A season or period as the player sees it: their own name for a season, if any."""
    return season.season_label(p, cal.names if cal else None)


def title(p, cal=None):
    """label() for the start of a line: a usual name capitalized, the player's as given."""
    if cal is not None and p in cal.names:
        return cal.names[p]
    v = label(p)
    return v[:1].upper() + v[1:]


def when_text(when, cal=None):
    return ", ".join(label(p, cal) for p in when) or "-"


def fail(*lines):
    for l in lines:
        print("  " + l)
    raise SystemExit(1)


def loaded():
    season._check_install()
    cal = ce.Calendar()
    if cal.error:
        fail(*(["seasons_config.py can't be edited here, so nothing was changed:"]
               + ["  " + l for l in cal.error]
               + ["Fix _tools\\seasons_config.py by hand, or open configure.bat and let it "
                  "start a new, empty one (the old file is kept next to it with the date in "
                  "its name)."]))
    return cal


def have_pillow():
    """Whether Pillow imports, which a broken install does not."""
    try:
        import PIL                                  # noqa: F401
        return True
    except ImportError:
        return False


def draw_dial():
    """season.py dial: hands the saved calendar and names to the game and draws a dial for
    them. Returns (ok, lines). A process of its own, so it reads the file just saved."""
    r = subprocess.run([sys.executable, os.path.join(ce.HERE, "season.py"), "dial"],
                       capture_output=True, text=True, cwd=season.ROOT, encoding="utf-8",
                       errors="replace")
    return r.returncode == 0, [l.strip() for l in (r.stdout + r.stderr).splitlines()
                               if l.strip()]


def dial_sentence(cal):
    """What the game has, once `season.py dial` has run for a saved calendar."""
    if not (cal.custom() or cal.names):
        return ["The game now uses Polesia's dates and the usual names, on the dial it "
                "ships with."]
    if have_pillow():
        return ["The game now has your dates and names, and the year dial was drawn for "
                "them."]
    return ["The game now has your dates and names. The year dial stays hidden until "
            "Pillow is installed."]


def fetch_now():
    """fetch_weather.py --force: the weather at a new place, for the game now rather than
    at the next launch. Its lines, credit included; it never fails."""
    try:
        r = subprocess.run([sys.executable, os.path.join(ce.HERE, "fetch_weather.py"),
                            "--force"], capture_output=True, text=True, cwd=season.ROOT,
                           encoding="utf-8", errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        return ["The weather there comes at the next launch."]
    return [l.strip() for l in (r.stdout + r.stderr).splitlines() if l.strip()]


def calendar_moved(cal):
    """Would saving change what the game is told: the dates, the names, or a repair that
    changes which CALENDAR or NAMES is in force?"""
    return (cal.dates_changed() or cal.names_changed()
            or any("CALENDAR" in f or "NAMES" in f for f in cal.fixes))


def save(cal, summary=()):
    """Save from a command. Written: the `summary` of what changed, the save's own lines,
    and a changed calendar handed to the game; True. Refused: why, and exit 1, with no word
    of a change that was not made. Nothing to write: False."""
    moved = calendar_moved(cal)
    saved, lines = cal.save()
    if not saved:
        for l in lines:
            print("  " + l)
        raise SystemExit(1)
    if lines == ["Nothing to save."]:
        print("  Nothing changed: it is already set that way.")
        return False
    for l in list(summary) + lines:
        print("  " + l)
    if moved:
        ok, out = draw_dial()
        for l in out:
            print("  " + l)
    return True


def calendar_lines(dates, cal=None):
    """One line per season that is on, and one for those that are off."""
    wins = ce.season_windows(dates)
    days = season.season_lengths(dates)
    out = ["%-14s %-17s %3d days" % (title(s, cal), wins[s], days[s])
           for s in season.SEASONS if s in dates]
    off = [label(s, cal) for s in season.SEASONS if s not in dates]
    if off:
        out.append("off: " + ", ".join(off))
    return out


def stranded(cal, dates):
    """Mods on the calendar only in seasons that `dates` has off."""
    return [n for n, c in cal.toggle.items() if c["when"] and all(
        p in season.SEASONS and p not in dates for p in c["when"])]


# --- commands -------------------------------------------------------------------------

def cmd_list(a):
    cal = loaded()
    inst = ce.Install()
    print("  calendar  %s" % ce.calendar_words(cal))
    print()
    if not cal.toggle:
        print("  No seasonal mods yet.")
    width = max([len(n) for n in cal.toggle] + [10])
    for name, c in cal.toggle.items():
        mark = "" if name in inst.names else "   <-- not in MO2's mod list"
        print("  %-*s  on in %s%s" % (width, name, when_text(c["when"], cal), mark))
        if not c["above"]:
            print("  %-*s  wins over (none set)" % (width, ""))
        else:
            mark = "" if inst.listed(c["above"]) else "   <-- not in MO2's mod list"
            print("  %-*s  wins over %s%s" % (width, "", c["above"], mark))
    if cal.own or cal._bad_own:
        print()
        for name in cal.own_order():
            print("  season %-24s %s  (%d days)" % (name, ce.window_text(cal.own[name]),
                                                     season.own_days(cal.own[name])))
        for name in cal._bad_own:
            print("  season %-24s can't be used; see below" % name)
    if cal.spells or cal._bad_spells:
        print()
        for name in sorted(cal.spells, key=str.casefold):
            print("  spell  %-24s %s" % (name, spell_words(cal, cal.spells[name])))
        for name in cal._bad_spells:
            print("  spell  %-24s can't be used; see below" % name)
    if cal.events or cal.periods or cal._bad_events:
        print()
        for name, md in cal.periods.items():
            print("  period %-17s from %s" % (name, ce.day_text(md)))
        for name, spec in cal.events.items():
            print("  event  %-17s %s" % (name, ce.window_text(spec)))
        for name in cal._bad_events:
            print("  event  %-17s can't be used; see below" % name)
    if cal.layout or cal.sound_src:
        print()
        for name in cal.layout:
            print("  texture set    %s" % name)
        print("  ambient sound  %s" % (cal.sound_src or "off"))
    if cal.problems:
        print()
        print("  play.bat can't switch anything until these are fixed:")
        for p in cal.problems:
            print("  ! " + p)
    if cal.fixes:
        print()
        print("  Saving from configure.bat also fixes:")
        for f in cal.fixes:
            print("  - " + f)


def pick_when(words, cal):
    """What --when names, as the config spells it; fails on a word that is none of them."""
    known = cal.known()
    when = []
    for w in words:
        p = ce.resolve(w, known, cal.names)
        if not p:
            fail("\"%s\" is not a season, an event or a kind of weather. These are: %s"
                 % (w, ", ".join(label(k, cal) for k in known)),
                 "A name with a space goes in quotes, like --when winter \"deep winter\".")
        when.append(p)
    return when


def typed(p, cal=None):
    """A season or event as it would be typed in a command: in quotes if it has a space."""
    v = label(p, cal)
    return '"%s"' % v if " " in v else v


def cmd_add(a):
    cal = loaded()
    inst = ce.Install()
    name, close = inst.match(a.mod)
    if not name:
        fail("No mod named \"%s\" in MO2's mod list." % a.mod,
             *(["Did you mean one of these?"] + ["  " + c for c in close] if close else
               ["Copy the name exactly as MO2's mod list shows it, in quotes."]))
    if name in season._own_folders():
        fail("That is Seasons of the Zone itself. It stays on all year, so it can't be a "
             "seasonal mod.")
    when = pick_when(a.when, cal)
    rivals = ce.anchor_for(inst, name, when, cal.toggle, cal)[2]
    if a.above:
        above, close = inst.match(a.above)
        if not above and a.above in inst.separators:
            above = a.above
        if not above:
            fail("No mod named \"%s\" in MO2's mod list for it to win over." % a.above,
                 *(["Did you mean one of these?"] + ["  " + c for c in close] if close else
                   ["Copy the name exactly as MO2's mod list shows it, in quotes."]))
        if above == name:
            fail("A mod can't win over itself. To find the mod it has to win over, run:",
                 "  " + season.command("season.py", "whowins <a file it ships> --for \"%s\""
                                       % name))
        chain = ce.loops(cal.toggle, name, above)
        if chain:
            fail("%s already wins over this mod, so this one can't win over it as well "
                 "(%s)." % (above, " -> ".join(chain)))
        why = "as you asked"
    elif name in cal.toggle and inst.listed(cal.toggle[name]["above"]):
        above, why = cal.toggle[name]["above"], "as it was"
    else:
        above, why, _ = ce.anchor_for(inst, name, when, cal.toggle)
        if not above:
            fail("Can't place it: %s. Name the mod it wins over with --above \"<mod>\"." % why)
    was = cal.toggle.get(name)
    cal.put(name, when, above)
    summary = ["%-9s %s" % ("changed" if was else "added", name)]
    if was:
        summary.append("%-9s %s" % ("was on in", when_text(was["when"], cal)))
    summary += ["%-9s %s" % ("on in", when_text(cal.toggle[name]["when"], cal)),
                "%-9s %s  (%s)" % ("wins over", above, why)]
    if not save(cal, summary):
        return
    for other, n, both in rivals:
        if other != above:
            print("  note      %s is also on in %s and ships %d of the same files. To make "
                  "this mod win them, run the command again with --above \"%s\"."
                  % (other, when_text(both, cal), n, other))
    off = [p for p in when if p in season.SEASONS and p not in cal.dates]
    if off:
        print("  note      %s %s off in your calendar, so the mod does not switch on then. "
              "To turn %s back on: %s" % (
                  season.seasons_text(off), "is" if len(off) == 1 else "are",
                  "it" if len(off) == 1 else "them",
                  season.command("configure.py", "calendar --on "
                                 + " ".join(typed(s) for s in off))))
    print("  play.bat switches it from the next launch.")


def cmd_remove(a):
    cal = loaded()
    names = list(cal.toggle)
    hit = next((n for n in names if n == a.mod), None) or next(
        (n for n in names if n.lower() == a.mod.lower()), None)
    if not hit:
        import difflib
        close = difflib.get_close_matches(a.mod, names, n=5, cutoff=0.5)
        fail("\"%s\" is not a seasonal mod." % a.mod,
             *(["Did you mean one of these?"] + ["  " + c for c in close] if close else
               ["%s shows them." % season.command("configure.py", "list")]))
    cal.take(hit)
    save(cal, ["stopped switching %s; play.bat leaves it as it is in MO2" % hit])


def event_rule(a):
    """The rule the options give, {} for none; fails on a part that does not read."""
    rule = {}
    if a.weekdays:
        rule["weekdays"] = ce.parse_weekdays(a.weekdays) or fail(
            "--weekdays takes days of the week, like sat sun, or weekends or workdays.")
    if a.days:
        rule["days"] = ce.parse_month_days(a.days) or fail(
            "--days takes days of the month, 1 to 31, or last, like 1 15 last.")
    if a.weeks:
        rule["weeks"] = ce.parse_weeks(a.weeks) or fail(
            "--weeks takes first, second, third, fourth, fifth or last.")
    if a.months:
        rule["months"] = ce.parse_months(a.months) or fail(
            "--months takes months, like dec jan feb, or 12 1 2.")
    if a.between:
        s, e = ce.parse_day(a.between[0]), ce.parse_day(a.between[1])
        if not s or not e:
            fail("--between takes two dates, month-day, like 12-01 02-28.")
        rule["within"] = (s, e)
    return rule


def cmd_event(a):
    cal = loaded()
    name = a.name.strip().lower()
    have = next((n for n in list(cal.events) + list(cal._bad_events) if n.lower() == name),
                None)
    if a.remove:
        if not have:
            fail("There is no event called \"%s\". %s shows the events."
                 % (a.name.strip(), season.command("configure.py", "list")))
        users = cal.users_of(have)
        if users:
            fail("These seasonal mods still use %s. Uncheck it for them first (the Delete "
                 "event button in configure.bat does both), then remove it:" % have,
                 *["  " + u for u in users])
        cal.events.pop(have, None)
        cal._bad_events.pop(have, None)
        save(cal, ["removed event %s" % have])
        return
    if not EVENT_NAME.match(name):
        fail("An event name is lowercase letters, digits and underscores, like christmas or "
             "new_year.")
    if (name in season.SEASONS or name in cal.periods or name in season.WEATHER_NAMES
            or ce.resolve(name, season.SEASONS, cal.names)):
        fail("\"%s\" is already taken by a season, a period or a kind of weather. Pick "
             "another name." % name)
    rule = event_rule(a)
    if rule:
        if a.start:
            fail("A rule can't also take a first and last day. Give dates with --between, "
                 "like --between 12-01 02-28.")
        spec = rule
    else:
        if not a.start:
            fail("Give the first day, like 12-24, and the last day if it runs more than one "
                 "day. Or give a rule, like --weekdays sat sun.")
        start = ce.parse_day(a.start)
        end = ce.parse_day(a.end) if a.end else start
        if not start or not end:
            fail("Dates are month-day, like 12-24.")
        spec = (start, end)
    problems = season.event_problems(name, spec)
    if problems:
        fail(*(["Not saved:"] + problems))
    key = have or name
    cal.events[key] = ce.norm_event(spec)
    cal._bad_events.pop(key, None)
    if not save(cal, ["event %s  %s" % (key, ce.window_text(spec))]):
        return
    if isinstance(spec, tuple) and spec[0] > spec[1]:
        print("  note    it runs across the new year")
    if (2, 29) in (spec if isinstance(spec, tuple) else ()):
        print("  note    February 29 comes only in leap years")


def cmd_season(a):
    """A season of the player's own: shown, added, changed, renamed or removed."""
    cal = loaded()
    if not a.name:
        if not cal.own:
            print("  No seasons of your own yet. To add one:")
            print("  " + season.command("configure.py",
                                        "season \"Wormhole season\" 08-01 08-31"))
        for n in cal.own_order():
            print("  %-24s %s  (%d days)" % (n, ce.window_text(cal.own[n]),
                                             season.own_days(cal.own[n])))
        return
    name = a.name.strip()
    have = next((n for n in list(cal.own) + list(cal._bad_own)
                 if n.casefold() == name.casefold()), None)
    if (a.remove or a.rename) and not have:
        fail("You have no season called \"%s\". %s shows yours."
             % (name, season.command("configure.py", "season")))
    if a.remove:
        gone = cal.take_own(have)
        save(cal, ["removed season %s" % have] + (
            ["stopped switching %s, on in nothing else" % ce.few(gone, 6)] if gone else []))
        return
    if a.rename:
        new = a.rename.strip()
        if have not in cal.own:
            fail("%s can't be used as it is. Give it dates first, then rename it:" % have,
                 "  " + season.command("configure.py", "season \"%s\" 08-01 08-31" % have))
        if any(n.casefold() == new.casefold() and n != have for n in cal.own):
            fail("You have a season called \"%s\" already." % new)
        cal.put_own(new, cal.own[have], was=have)
        save(cal, ["renamed season %s to %s" % (have, new)])
        return
    if not a.start or not a.end:
        fail("Give the first and the last day, month-day, like:",
             "  " + season.command("configure.py", "season \"%s\" 08-01 08-31" % name))
    start, end = ce.parse_day(a.start), ce.parse_day(a.end)
    if not start or not end:
        fail("Dates are month-day, like 08-01.")
    if not have and len(cal.own) >= season.OWN_MOST:
        fail("You have %d seasons of your own, as many as the year has room for. Remove "
             "one first." % len(cal.own))
    key = have or name
    was = cal.own.get(key)
    cal.put_own(key, (start, end))
    if not save(cal, ["%s season %s  %s  (%d days)" % (
            "changed" if was else "added", key, ce.window_text((start, end)),
            season.own_days((start, end)))]):
        return
    if not cal.users_of(key):
        print("  To have a mod on in it: " + season.command(
            "configure.py", "add \"<mod>\" --when \"%s\"" % key))


def spell_words(cal, spec):
    """A spell in words: where it starts, how likely, how long, what it brings, how often."""
    lo, hi = spec["days"]
    often = season.spells_a_year(spec, cal.where)
    return "in %s, %s%% a day, %s; %s; %s" % (
        season._and(label(p, cal) for p in spec["in"]), ("%g" % spec["chance"]),
        "%d day%s" % (lo, "" if lo == 1 else "s") if lo == hi else "%d to %d days" % (lo, hi),
        "brings %s" % label(spec["as"], cal) if spec["as"] else "the season stays",
        often_words(often))


def often_words(n):
    """How often something happens, from the times a year on average."""
    if n >= 1.5:
        return "about %d times a year" % round(n)
    if n >= 0.75:
        return "about once a year"
    if n > 0:
        return "about once every %d years" % max(2, round(1 / n))
    return "never"


def cmd_spell(a):
    """A spell: shown, added, changed, renamed or removed."""
    cal = loaded()
    if not a.name:
        if not cal.spells:
            print("  No spells yet. To add one:")
            print("  " + season.command("configure.py", "spell \"Summer frost\" --in summer "
                                        "--chance 3 --days 1 2 --as winter"))
        for n in sorted(cal.spells, key=str.casefold):
            print("  %-24s %s" % (n, spell_words(cal, cal.spells[n])))
        return
    name = a.name.strip()
    have = next((n for n in list(cal.spells) + list(cal._bad_spells)
                 if n.casefold() == name.casefold()), None)
    if (a.remove or a.rename) and not have:
        fail("You have no spell called \"%s\". %s shows yours."
             % (name, season.command("configure.py", "spell")))
    if a.remove:
        gone = cal.take_spell(have)
        save(cal, ["removed spell %s" % have] + (
            ["stopped switching %s, on in nothing else" % ce.few(gone, 6)] if gone else []))
        return
    if a.rename:
        new = a.rename.strip()
        if have not in cal.spells:
            fail("%s can't be used as it is. Fix it first with --in, --chance or --days."
                 % have)
        if any(n.casefold() == new.casefold() and n != have for n in cal.spells):
            fail("You have a spell called \"%s\" already." % new)
        cal.put_spell(new, cal.spells[have], was=have)
        save(cal, ["renamed spell %s to %s" % (have, new)])
        return
    old = dict(cal.spells.get(have, {}))
    if not old and not (a.start and a.chance is not None):
        fail("A new spell needs --in and --chance, like:",
             "  " + season.command("configure.py", "spell \"%s\" --in summer --chance 3 "
                                   "--days 1 2 --as winter" % name))
    spec = dict(old)
    if a.start:
        spec["in"] = tuple(pick_when(a.start, cal))
    if a.chance is not None:
        spec["chance"] = int(a.chance) if a.chance == int(a.chance) else a.chance
    if a.days:
        if len(a.days) > 2:
            fail("--days takes one number, or the fewest and the most, like --days 1 2.")
        spec["days"] = (a.days[0], a.days[-1])
    spec.setdefault("days", (1, 1))
    if a.brings is not None:
        spec["as"] = None if a.brings.lower() in ("none", "") else (
            pick_when([a.brings], cal)[0])
    spec.setdefault("as", None)
    key = have or name
    cal.put_spell(key, spec)
    if not save(cal, ["%s spell %s  %s" % ("changed" if old else "added", key,
                                            spell_words(cal, cal.spells[key]))]):
        return
    if not cal.users_of(key):
        print("  To have a mod on during it: " + season.command(
            "configure.py", "add \"<mod>\" --when \"%s\"" % key))


def cmd_calendar(a):
    cal = loaded()
    # argparse files "summer=5-1" after --off or --on under that option
    for opt in (a.off, a.on):
        for x in list(opt or []):
            if "=" in x:
                opt.remove(x)
                a.starts.append(x)
    if a.reset and a.dates:
        fail("--reset and --dates each set the whole calendar; give one.")
    if a.dates and a.only:
        fail("--dates turns every season on and --only turns some off; give one.")

    def name(n):
        s = ce.resolve(n, season.SEASONS, cal.names)
        if not s:
            fail("\"%s\" is not a season. These are: %s" % (
                n, ", ".join(label(s, cal) for s in season.SEASONS)),
                "A name with a space goes in quotes, like --off \"late winter\".")
        return s

    moves = {}
    for arg in a.starts:
        n, eq, day = arg.partition("=")
        if not eq:
            fail("Give each season as name=month-day, like summer=5-20.")
        md = ce.parse_day(day)
        if not md:
            fail("\"%s\" is not a date. Dates are month-day, like 5-20." % day)
        s = name(n)
        if s in moves:
            fail("%s is given twice." % title(s, cal))
        moves[s] = md
    on = [name(n) for n in a.on or []]
    off = [name(n) for n in a.off or []]
    for s in set(on) & set(off):
        fail("%s is both turned on and turned off." % title(s, cal))
    for s in set(moves) & set(off):
        fail("%s is both moved and turned off." % title(s, cal))
    if a.only and not moves:
        fail("--only needs the seasons to keep, like summer=5-20 \"deep winter=12-1\".")

    if not (a.reset or a.dates or moves or on or off):
        print("  %s" % ("Your own dates:" if cal.custom() else "Polesia's dates, the default:"))
        for l in calendar_lines(cal.dates, cal):
            print("  " + l)
        for p in cal.calendar_bad + cal.names_bad:
            print("  ! " + p)
        return
    dates = dict(cal.dates)
    if a.reset:
        dates = ce.polesia()
    elif a.dates:
        dates = ce.meteorological() if a.dates == "met" else ce.polesia()
    if a.only:
        dates = {}
    for s in on:
        dates.setdefault(s, ce.polesia()[s])
    for s in off:
        dates.pop(s, None)
    dates.update(moves)
    problems = season.calendar_problems(dates)
    if problems:
        fail(*(["Not saved:"] + problems))
    cal.set_dates(dates)
    if not save(cal, calendar_lines(dates, cal)):
        return
    for n in stranded(cal, dates):
        print("  note    %s is on only in seasons that are off, so it never switches on. Give "
              "it other seasons, or turn one of them back on." % n)


def cmd_name(a):
    cal = loaded()
    if not a.season:
        for s in season.SEASONS:
            print("  %-12s %s" % (season.default_label(s),
                                  cal.names.get(s, "(its usual name)")))
        for p in cal.names_bad:
            print("  ! " + p)
        return
    s = ce.resolve(a.season, season.SEASONS, cal.names)
    if not s:
        fail("\"%s\" is not a season. These are: %s" % (
            a.season, ", ".join(season.default_label(s) for s in season.SEASONS)))
    names = dict(cal.names)
    if a.reset:
        names.pop(s, None)
    elif not a.name or not a.name.strip():
        fail("Give the name in quotes, like: "
             + season.command("configure.py", "name \"deep winter\" \"The Long Cold\""))
    else:
        names[s] = a.name.strip()
    problems = season.names_problems(names)
    if problems:
        fail(*(["Not saved:"] + problems))
    cal.set_names(names)
    save(cal, ["%s is now called \"%s\"" % (season.default_label(s).capitalize(), cal.names[s])
               if s in cal.names else
               "%s has its usual name again" % season.default_label(s).capitalize()])


def cmd_place(a):
    import fetch_weather as fw
    cal = loaded()
    if not (a.text or a.at or a.reset):
        print("  The weather comes from %s%s." % (ce.place_text(cal.place),
                                                 "" if cal.place else ", the default"))
        for p in cal.place_bad:
            print("  ! " + p)
        return
    if a.reset and (a.text or a.at):
        fail("--reset brings Chornobyl back; give it on its own.")
    if a.text and a.at:
        fail("Give a place to look up, or --at and its coordinates, not both.")
    if a.reset:
        place = None
    elif a.at:
        lat, lon = a.at
        place = {"name": (a.name or "%.2f, %.2f" % (lat, lon)).strip(), "lat": lat, "lon": lon}
    else:
        try:
            found = fw.search(a.text)
        except Exception as e:
            fail("Couldn't reach open-meteo.com to look it up (%s). Give its coordinates "
                 "instead, like --at 50.45 30.52 --name Kyiv." % type(e).__name__)
        print("  " + fw.PLACES_CREDIT)
        if not found:
            fail("No place called \"%s\" was found. Try another spelling, or give its "
                 "coordinates with --at." % a.text)
        if a.pick and not 1 <= a.pick <= len(found):
            fail("--pick takes 1 to %d." % len(found))
        if not a.pick and len(found) > 1:
            print("  Several places are called that:")
            for i, f in enumerate(found, 1):
                print("  %2d  %s" % (i, found_text(f)))
            fail("Run the command again with --pick and the number, like --pick 1.")
        f = found[(a.pick or 1) - 1]
        place = {"name": f["name"][:season.PLACE_CHARS].strip(), "lat": f["lat"],
                 "lon": f["lon"]}
    if place:
        problems = season.place_problems(place)
        if problems:
            fail(*(["Not saved:"] + problems))
    cal.set_place(place)
    if save(cal, ["the weather comes from %s" % ce.place_text(cal.place)]):
        for l in fetch_now():
            print("  " + l)


def found_text(f):
    """A place the search found, as the lists show it."""
    return "%s%s   %s" % (f["name"], " - " + f["where"] if f["where"] else "",
                          ce.place_text(dict(f, name=""))[1:].strip("() "))


def cmd_preset(a):
    files = ce.preset_files()
    if not a.action or a.action == "list":
        if not files:
            print("  No presets yet. Save one with: "
                  + season.command("configure.py", "preset save \"<name>\""))
            return
        for name, path in files.items():
            p, problems = ce.read_preset(path)
            parts = ce.preset_parts(p) if p else []
            print("  %-26s %s%s" % (name, "; ".join(ce.PART_TEXT[x] for x in parts) or "-",
                                    "   (can't be used; preset show says why)" if problems
                                    else ""))
            if p and p["about"]:
                print("  %-26s %s" % ("", p["about"]))
        return
    if not a.name:
        fail("Name the preset, in quotes if it has spaces.")
    if a.action == "save":
        name = a.name.strip()
        if not ce.PRESET_NAME.match(name):
            fail("A preset name is up to 40 letters, digits, spaces and - _ . , ' ( ).")
        same = next((n for n in files if n.lower() == name.lower()), None)
        if same:
            old, _ = ce.read_preset(files[same])
            if old and old["shipped"]:
                fail("\"%s\" comes with the tool; save yours under another name." % same)
            if not a.force:
                fail("There is already a preset called \"%s\". Add --force to replace it."
                     % same)
            name = same
        cal = loaded()
        if cal.problems:
            fail(*(["Not saved as a preset. Fix these in seasons_config.py first:"]
                   + cal.problems))
        parts = a.parts or ce.parts_with_content(cal)
        path = ce.write_preset(name, a.about, ce.preset_from(cal, parts))
        print("  Saved preset %s (%s) as:" % (name, "; ".join(ce.PART_TEXT[p] for p in parts)))
        print("  %s" % path)
        return
    name = next((n for n in files if n.lower() == a.name.strip().lower()), None)
    if not name:
        fail("There is no preset called \"%s\"." % a.name.strip(),
             *(["These are: " + ", ".join(files)] if files else []))
    p, problems = ce.read_preset(files[name])
    if problems:
        fail(*(["\"%s\" can't be used:" % name] + problems))
    have = ce.preset_parts(p)
    if a.action == "show":
        if p["about"]:
            print("  " + p["about"])
        print("  holds: %s" % "; ".join(ce.PART_TEXT[x] for x in have))
        if "calendar" in have:
            for l in calendar_lines(p["calendar"] or ce.polesia()):
                print("    " + l)
            for s, n in (p.get("names") or {}).items():
                print("    %s is called \"%s\"" % (season.default_label(s).capitalize(), n))
        if "events" in have:
            for n, spec in p.get("events", {}).items():
                print("    event %-18s %s" % (n, ce.window_text(spec)))
        if "mods" in have:
            for n, c in p["mods"].items():
                print("    %s  (on in %s)" % (n, when_text(c["when"])))
        if "textures" in have:
            for n in p.get("layout") or {}:
                print("    texture set %s" % n)
            print("    ambient sound: %s" % (p.get("sound_src") or "off"))
        return
    parts = [x for x in (a.parts or have) if x in have]
    if not parts:
        fail("\"%s\" holds none of those parts; it holds %s."
             % (name, "; ".join(ce.PART_TEXT[x] for x in have)))
    cal = loaded()
    inst = ce.Install()
    lines, losses = ce.preset_effect(cal, inst, p, parts)
    if losses and not a.force:
        fail(*(["Nothing was changed. Loading %s would do this:" % name]
               + ["  " + l for l in lines]
               + ["It takes the place of %s. Run the command again with --force to load it "
                  "anyway; the old file is kept as seasons_config.py.bak."
                  % " and ".join(losses)]))
    said = ce.apply_preset(cal, inst, p, parts)
    save(cal, ["loaded %s" % name] + said)


# --- the window -----------------------------------------------------------------------

WEATHER_TEXT = {"freezing": "the low is 0°C or below",
                "thaw": "it freezes overnight and climbs above 0°C by afternoon",
                "heat": "the high reaches 28°C"}
GREY, RED, AMBER = "#666666", "#b03020", "#9a5b00"
TITLE = "Seasons of the Zone setup"
SEP = "|sep|"               # a list row that is a separator; no mod folder holds a |


# Open-Meteo's data is CC BY 4.0: credited, with links, wherever the window shows it or
# asks for it. Each credit is (text, link) pieces.
LICENSE = "https://creativecommons.org/licenses/by/4.0/"
WEATHER_CREDIT = [("Weather data by Open-Meteo.com", "https://open-meteo.com/"),
                  ("(CC BY 4.0)", LICENSE)]
PLACES_CREDIT = [("Places from Open-Meteo.com,", "https://open-meteo.com/"),
                 ("based on GeoNames", "https://www.geonames.org/"), ("(CC BY 4.0)", LICENSE)]
CLIMATE_CREDIT = [("Climate from Open-Meteo.com", "https://open-meteo.com/"),
                  ("(CC BY 4.0); contains modified Copernicus Climate Change Service "
                   "information", "https://climate.copernicus.eu/")]
SKY = {"clear": "clear", "partly": "partly cloudy", "cloudy": "overcast", "foggy": "fog",
       "rain": "rain", "snow": "snow", "storm": "storms"}


def credit(parent, pieces):
    """A line of credit, each piece a link that opens in the browser. Returned unpacked."""
    import webbrowser
    from tkinter import ttk
    line = ttk.Frame(parent)
    for i, (text, url) in enumerate(pieces):
        lab = ttk.Label(line, text=text, foreground="#1f5f99", cursor="hand2")
        lab.pack(side="left", padx=(0 if i == 0 else 4, 0))
        lab.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
    return line


def plain(problem):
    """A refusal from season.py, in the window's words rather than the file's."""
    def name(m):
        return m.group(2)
    p = re.sub(r"^TOGGLE_MODS\[(['\"])(.*?)\1\]:? ?", lambda m: name(m) + ": ", problem)
    p = re.sub(r"^EVENTS\[(['\"])(.*?)\1\]:? ?", lambda m: "Event %s: " % name(m), p)
    p = re.sub(r"^PERIODS\[(['\"])(.*?)\1\]:? ?", lambda m: "Period %s: " % name(m), p)
    p = re.sub(r"^OWN_SEASONS\[(['\"])(.*?)\1\](:? ?)",
               lambda m: name(m) + (": " if m.group(3).startswith(":") else " "), p)
    p = re.sub(r"^SPELLS\[(['\"])(.*?)\1\](:? ?)",
               lambda m: "Spell %s" % name(m) + (": " if m.group(3).startswith(":") else " "),
               p)
    p = re.sub(r"^LAYOUT\[(['\"])(.*?)\1\]:? ?", lambda m: "Texture set %s: " % name(m), p)
    p = re.sub(r"^NAMES\[(['\"])(.*?)\1\]:? ?",
               lambda m: "The name for %s: " % season.default_label(name(m)), p)
    p = re.sub(r"^CALENDAR\[(['\"])(.*?)\1\]:? ?",
               lambda m: season.default_label(name(m)).capitalize() + ": ", p)
    p = re.sub(r"^(CALENDAR|NAMES|OWN_SEASONS): ", "", p)
    return p[:1].upper() + p[1:]


def reason(problem):
    """A refusal without the table and name it starts with, for a line that names them."""
    p = re.sub(r"^[A-Z_]+(\[(['\"]).*?\2\])?:? ?", "", problem)
    return p[:1].upper() + p[1:]


def center(win, root):
    """Put a dialog over the middle of the window it belongs to, or of the screen while
    that window is not up yet."""
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    if root.winfo_viewable():
        x = root.winfo_rootx() + max((root.winfo_width() - w) // 2, 0)
        y = root.winfo_rooty() + max((root.winfo_height() - h) // 3, 0)
    else:
        x = max((win.winfo_screenwidth() - w) // 2, 0)
        y = max((win.winfo_screenheight() - h) // 3, 0)
    win.geometry("+%d+%d" % (x, y))


def dialog(root, title, transient=True):
    """A dialog: (window, frame to fill). Shown with present(), which puts it over the
    main window and holds the input until it closes; Escape closes it. One shown before the
    main window is up must not be `transient`: Windows hides a transient window with the
    window it belongs to, and the main window is still withdrawn."""
    import tkinter as tk
    from tkinter import ttk
    win = tk.Toplevel(root)
    win.withdraw()
    win.title(title)
    if transient:
        win.transient(root)
    win.bind("<Escape>", lambda e: win.destroy())
    f = ttk.Frame(win, padding=14)
    f.pack(fill="both", expand=True)
    return win, f


def present(win, root, focus=None):
    center(win, root)
    win.deiconify()
    win.grab_set()
    (focus or win).focus_set()


def button_row(parent, *specs):
    """Buttons at the right in reading and Tab order, the first the default. `specs` are
    (text, command)."""
    from tkinter import ttk
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=(14, 0))
    inner = ttk.Frame(row)
    inner.pack(side="right")
    made = []
    for i, (text, cmd) in enumerate(specs):
        b = ttk.Button(inner, text=text, command=cmd, default="active" if i == 0 else "normal")
        b.pack(side="left", padx=(0 if i == 0 else 6, 0))
        made.append(b)
    return made


class Scrolled(object):
    """A panel that scrolls when what it holds is taller than the room it has."""

    def __init__(self, parent, tk, ttk, width=440):
        bg = ttk.Style().lookup("TFrame", "background")
        self.canvas = tk.Canvas(parent, highlightthickness=0, borderwidth=0, width=width,
                                background=bg)
        self.bar = ttk.Scrollbar(parent, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, padding=(12, 0, 8, 10))
        self.item = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self.item, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self.wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def wheel(self, e):
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def width(self):
        w = self.canvas.winfo_width()
        return w if w > 50 else int(self.canvas.cget("width"))

    def top(self):
        self.canvas.yview_moveto(0)


class App(object):
    """The setup in a window. Mods: MO2's mods on the left, as MO2 lists them; the chosen
    one's seasons, events and what it wins over on the right. Seasons: when each starts,
    which are on, what each is called, and the dial the game draws for them. Changes are
    held until Save."""

    def __init__(self, root, cal, inst):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root, self.cal, self.inst = root, cal, inst
        self.current = None
        self.windows = ce.season_windows(cal.dates)
        self.bad_dates, self._filling = [], False
        self._anchors = {}          # what a mod taken off beat, in case it goes back on
        self._focus = None          # the checkbox to focus again after the panel is redrawn
        self._wrap = 380
        self._names_job, self._bad_rows = None, set()
        self.own = season._own_folders()
        style = ttk.Style(root)
        style.configure("Bad.TCheckbutton", foreground=RED)
        style.configure("Head.TLabel", font=("TkDefaultFont", 11, "bold"))
        root.title(TITLE)
        root.geometry("1180x720")
        root.minsize(900, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-s>", lambda e: self.save())

        # the bar first, so nothing above it can push it off the window
        bottom = ttk.Frame(root, padding=(10, 8))
        bottom.pack(side="bottom", fill="x")
        self.status = ttk.Label(bottom, text="")
        self.status.pack(side="left")
        self.unsaved = ttk.Label(bottom, text="", foreground=AMBER)
        self.unsaved.pack(side="left", padx=(10, 0))
        bar = ttk.Frame(bottom)
        bar.pack(side="right")
        for text, cmd, pad in (("Load preset...", self.load_preset, 0),
                               ("Save preset...", self.save_preset, 6),
                               ("Preview the next launch...", self.preview, 18),
                               ("Save", self.save, 6), ("Close", self.close, 6)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=(pad, 0))
        # what season.py would refuse in this setup, while there is any
        self.banner = ttk.Frame(root)
        self.banner.pack(side="top", fill="x", padx=10)

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        mods = ttk.Frame(self.tabs)
        self.tabs.add(mods, text="Mods")
        seasons = ttk.Frame(self.tabs)
        self.tabs.add(seasons, text="Seasons")
        weather = ttk.Frame(self.tabs)
        self.tabs.add(weather, text="Weather")

        top = ttk.Frame(mods, padding=(0, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Find a mod:").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.fill())
        ttk.Entry(top, textvariable=self.search, width=40).pack(side="left", padx=6)
        self.only_ours = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Only seasonal mods", variable=self.only_ours,
                        command=self.fill).pack(side="left", padx=10)

        panes = ttk.PanedWindow(mods, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        self.tree = ttk.Treeview(left, columns=("when",), show="tree headings",
                                 selectmode="browse")
        self.tree.heading("#0", text="Mods, as MO2 lists them", anchor="w")
        self.tree.heading("when", text="On in", anchor="w")
        self.tree.column("#0", width=400)
        self.tree.column("when", width=230)
        self.tree.tag_configure("off", foreground="#888888")
        self.tree.tag_configure("ours", foreground="#1f5f99")
        self.tree.tag_configure("gone", foreground=RED)
        self.tree.tag_configure("self", foreground="#888888")
        self.tree.tag_configure("sep", foreground="#888888",
                                font=("TkDefaultFont", 9, "italic"))
        bar = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.pick())
        panes.add(left, weight=3)
        side = ttk.Frame(panes)
        panes.add(side, weight=2)
        self.scroll = Scrolled(side, tk, ttk)
        self.side = self.scroll.inner
        self._side_width = 0
        self.scroll.canvas.bind("<Configure>", self.side_resized, add="+")

        self.seasons_tab(seasons)
        self.weather_tab(weather)
        self.fill()
        self.show()
        self.update_status()

    # the list

    def fill(self):
        q = self.search.get().strip().lower()
        ours_only = self.only_ours.get()
        never = set(stranded(self.cal, self.cal.dates))
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for name, on, sep in self.inst.pane_order():
            if sep:
                if not q and not ours_only:
                    self.tree.insert("", "end", iid=SEP + name,
                                     text=ce.separator_label(name), tags=("sep",))
                continue
            ours = name in self.cal.toggle
            if (ours_only and not ours) or (q and q not in name.lower()):
                continue
            if name in self.own:
                when, tag = "always on (this mod)", "self"
            elif ours:
                when = when_text(self.cal.toggle[name]["when"], self.cal)
                if name in never:
                    when += "  (never: its seasons are off)"
                tag = "ours"
            else:
                when, tag = "", ("" if on else "off")
            self.tree.insert("", "end", iid=name, text=name, values=(when,), tags=(tag,))
            shown += 1
        # seasonal but not in MO2's mod list - renamed by an update, say - so they can still
        # be picked and let go
        for name, c in self.cal.toggle.items():
            if name not in self.inst.names and (not q or q in name.lower()):
                self.tree.insert("", "end", iid=name, text=name + "   (not in MO2's mod list)",
                                 values=(when_text(c["when"], self.cal),), tags=("gone",))
                shown += 1
        if not shown:
            self.tree.insert("", "end", iid=SEP + "none", tags=("sep",), text=(
                "No mod's name has \"%s\" in it." % q if q else
                "No seasonal mods yet."))
        if self.current and self.tree.exists(self.current):
            self.tree.selection_set(self.current)
            self.tree.see(self.current)

    def pick(self):
        sel = self.tree.selection()
        if not sel:
            return
        if sel[0].startswith(SEP):
            self.tree.selection_remove(sel[0])
            return
        if sel[0] != self.current:
            self.current = sel[0]
            self.show()
            self.scroll.top()

    def select(self, name):
        """Show `name` on the right, as clicking it in the list does."""
        self.current = name
        if self.tree.exists(name):
            self.tree.selection_set(name)
            self.tree.see(name)
        self.show()

    def side_resized(self, e):
        # the panel's text wraps to its width, so a new width redraws it
        if abs(e.width - self._side_width) > 24:
            self._side_width = e.width
            self.root.after_idle(self.show)

    # the chosen mod

    def label(self, text, color=None, pad=(0, 0), indent=0, parent=None, **kw):
        return self.ttk.Label(parent or self.side, text=text, justify="left",
                              wraplength=max(self._wrap - indent, 200),
                              foreground=color, **kw)

    def show(self):
        tk, ttk = self.tk, self.ttk
        for w in self.side.winfo_children():
            w.destroy()
        self._wrap = max(self.scroll.width() - 44, 260)
        name = self.current
        if not name:
            self.welcome()
            return
        self.label(name, style="Head.TLabel").pack(anchor="w", pady=(4, 0))
        if name in self.own:
            self.label("This is Seasons of the Zone itself. It has to stay on all year, so "
                       "it isn't something to put on the calendar.").pack(anchor="w",
                                                                           pady=(6, 0))
            return
        entry = self.cal.toggle.get(name)
        when = entry["when"] if entry else []
        if name in self.inst.names:
            n = len(self.inst.files(name))
            self.label("%s in MO2 now; it has %d file%s." % (
                "Enabled" if name in self.inst.enabled else "Disabled", n, "" if n == 1 else "s"),
                GREY).pack(anchor="w", pady=(0, 8))
        else:
            self.label("Not in MO2's mod list, so play.bat can't switch it. Stop switching it "
                       "below, or put the mod back in MO2.", RED).pack(anchor="w",
                                                                          pady=(0, 8))
        self.vars, self.checks = {}, {}

        box = ttk.LabelFrame(self.side, text="On in these seasons", padding=8)
        box.pack(fill="x")
        for i, s in enumerate(season.SEASONS):
            v = tk.BooleanVar(value=s in when)
            self.vars[s] = v
            c = ttk.Checkbutton(box, text=title(s, self.cal), variable=v,
                                command=lambda p=s: self.ticked(p))
            c.grid(row=i, column=0, sticky="w")
            self.checks[s] = c
            ttk.Label(box, text=self.windows.get(s) or "off (see the Seasons tab)",
                      foreground=GREY).grid(row=i, column=1, sticky="w", padx=(12, 0))
        for i, p in enumerate(self.cal.own_order(), start=len(season.SEASONS)):
            v = tk.BooleanVar(value=p in when)
            self.vars[p] = v
            c = ttk.Checkbutton(box, text=p, variable=v, command=lambda p=p: self.ticked(p))
            c.grid(row=i, column=0, sticky="w")
            self.checks[p] = c
            ttk.Label(box, text=ce.window_text(self.cal.own[p]), foreground=GREY).grid(
                row=i, column=1, sticky="w", padx=(12, 0))
        ttk.Button(box, text="New season of your own...", command=self.new_own).grid(
            row=len(season.SEASONS) + len(self.cal.own), column=0, columnspan=2, sticky="w",
            pady=(6, 0))

        box = ttk.LabelFrame(self.side, text="And on these events", padding=8)
        box.pack(fill="x", pady=(8, 0))
        for p in sorted(self.cal.periods) + sorted(self.cal.events):
            spec = self.cal.events.get(p)
            v = tk.BooleanVar(value=p in when)
            self.vars[p] = v
            line = ttk.Frame(box)
            line.pack(fill="x")
            c = ttk.Checkbutton(line, text=p, variable=v, command=lambda p=p: self.ticked(p))
            c.pack(side="left")
            self.checks[p] = c
            if spec is not None:
                ttk.Button(line, text="Delete event", command=lambda e=p: self.delete_event(e)
                           ).pack(side="right")
                ttk.Button(line, text="Edit...", command=lambda e=p: self.new_event(e)
                           ).pack(side="right", padx=(0, 4))
            self.label(ce.window_text(spec) if spec is not None
                       else "a period of your own, set in seasons_config.py", GREY,
                       indent=48, parent=box).pack(anchor="w", padx=(22, 0))
        for p, spec in self.cal._bad_events.items():
            line = ttk.Frame(box)
            line.pack(fill="x")
            ttk.Label(line, text=p, foreground=RED).pack(side="left", padx=(22, 0))
            ttk.Button(line, text="Delete event", command=lambda e=p: self.delete_event(e)
                       ).pack(side="right")
            self.label("Can't be used. " + " ".join(
                reason(x) for x in season.event_problems(p, spec)), RED, indent=48,
                parent=box).pack(anchor="w", padx=(22, 0))
        if not (self.cal.events or self.cal.periods or self.cal._bad_events):
            ttk.Label(box, text="No events of your own yet.", foreground=GREY).pack(anchor="w")
        ttk.Button(box, text="New event...", command=self.new_event).pack(anchor="w",
                                                                         pady=(6, 0))

        box = ttk.LabelFrame(self.side, text="And during these spells", padding=8)
        box.pack(fill="x", pady=(8, 0))
        for p in sorted(self.cal.spells, key=str.casefold):
            v = tk.BooleanVar(value=p in when)
            self.vars[p] = v
            c = ttk.Checkbutton(box, text=p, variable=v, command=lambda p=p: self.ticked(p))
            c.pack(anchor="w")
            self.checks[p] = c
            self.label(spell_words(self.cal, self.cal.spells[p]), GREY, indent=48,
                       parent=box).pack(anchor="w", padx=(22, 0))
        if not self.cal.spells:
            ttk.Label(box, text="No spells yet.", foreground=GREY).pack(anchor="w")
        ttk.Button(box, text="New spell...", command=self.new_spell).pack(anchor="w",
                                                                       pady=(6, 0))

        box = ttk.LabelFrame(self.side, text="And on these kinds of weather at %s"
                             % (self.cal.place or ce.DEFAULT_PLACE)["name"],
                             padding=8)
        box.pack(fill="x", pady=(8, 0))
        for i, p in enumerate(season.WEATHER_NAMES):
            v = tk.BooleanVar(value=p in when)
            self.vars[p] = v
            c = ttk.Checkbutton(box, text=p, variable=v, command=lambda p=p: self.ticked(p))
            c.grid(row=i, column=0, sticky="nw")
            self.checks[p] = c
            self.label(WEATHER_TEXT[p], GREY, indent=110, parent=box).grid(
                row=i, column=1, sticky="w", padx=(8, 0))
        self.label("play.bat checks the real weather at each launch. Without play.bat, or "
                   "an internet connection, none of these is on.", GREY, indent=20,
                   parent=box).grid(row=len(season.WEATHER_NAMES), column=0, columnspan=2,
                                    sticky="w", pady=(4, 0))

        for p in [p for p in when if p not in self.cal.known()]:
            line = ttk.Frame(self.side)
            line.pack(fill="x", pady=(8, 0))
            self.label("seasons_config.py also has it on for \"%s\", which is not a season, "
                       "event or kind of weather." % p, RED, parent=line,
                       indent=120).pack(side="left")
            ttk.Button(line, text="Drop it", command=lambda p=p: self.set_when(
                name, [x for x in self.cal.toggle[name]["when"] if x != p])).pack(side="right")

        if entry:
            self.anchor_box(name, entry)
            ttk.Button(self.side, text="Stop switching this mod",
                       command=lambda: self.remove(name)).pack(anchor="w", pady=(10, 0))
            self.label("play.bat then leaves it as it is in MO2.", GREY).pack(anchor="w",
                                                                           pady=(2, 0))
        if self._focus in self.checks:
            self.checks[self._focus].focus_set()
        self._focus = None

    def welcome(self):
        ttk = self.ttk
        self.label("Start here", style="Head.TLabel").pack(anchor="w", pady=(4, 6))
        for n, line in enumerate((
                "Pick a mod on the left: one that changes textures, sounds or anything "
                "else for a season.",
                "Check the seasons it belongs to. play.bat switches it on in those "
                "seasons, and off the rest of the year.",
                "Save, then start the game with play.bat. It switches the mods each time it "
                "starts the game."), 1):
            self.label("%d. %s" % (n, line)).pack(anchor="w", pady=(0, 6))
        self.label("Or start from a preset. The GAMMA example sets up the seasonal mods "
                   "that come with GAMMA, where you have them installed.").pack(
                       anchor="w", pady=(10, 4))
        ttk.Button(self.side, text="Load preset...", command=self.load_preset).pack(anchor="w")
        self.label("The list runs as MO2's does. Blue mods are seasonal, grey ones are "
                   "disabled in MO2, and red ones are seasonal but gone from MO2. The Seasons "
                   "tab sets when each season starts, and the Weather tab where the real "
                   "weather comes from.", GREY).pack(anchor="w",
                                                                         pady=(16, 0))

    def anchor_box(self, name, entry):
        ttk = self.ttk
        box = ttk.LabelFrame(self.side, text="Wins over", padding=8)
        box.pack(fill="x", pady=(8, 0))
        auto, why, rivals = ce.anchor_for(self.inst, name, entry["when"], self.cal.toggle,
                                          self.cal)
        choices = [(auto, "%s  (picked for you)" % auto)] if auto else []
        for other, n in ce.overlaps(self.inst, name):
            if other != auto:
                choices.append((other, "%s  (%d shared file%s%s)" % (
                    other, n, "" if n == 1 else "s",
                    "; seasonal" if other in self.cal.toggle else
                    "; disabled in MO2" if other not in self.inst.enabled else "")))
        if entry["above"] and entry["above"] not in [c[0] for c in choices]:
            choices.append((entry["above"], entry["above"]))
        combo = ttk.Combobox(box, state="readonly", values=[c[1] for c in choices])
        cur = [i for i, c in enumerate(choices) if c[0] == entry["above"]]
        if cur:
            combo.current(cur[0])
        combo.bind("<<ComboboxSelected>>",
                   lambda e: self.set_anchor(name, choices[combo.current()][0]))
        combo.pack(fill="x")
        above = entry["above"]
        if not self.inst.listed(above):
            self.label("\"%s\" is not in MO2's mod list, so play.bat would skip this mod. "
                       "Pick another in the box above." % above, RED, indent=24,
                       parent=box).pack(
                           anchor="w", pady=(6, 0))
        else:
            self.label("play.bat keeps it just below %s in MO2's mod list, so where the two "
                       "have the same file, this one's is used." % above, indent=24,
                       parent=box).pack(anchor="w", pady=(6, 0))
            self.label(("Picked for you: %s." % why) if above == auto else "Picked by you.",
                       GREY, indent=24, parent=box).pack(anchor="w", pady=(2, 0))
        # rivals that would still win once play.bat has placed everything
        pos = ce.placed(self.inst, self.cal.toggle)
        for other, n, both in rivals:
            if other == above or pos.get(other, 1e9) > pos.get(name, -1):
                continue
            self.label("%s is on in %s too, and would still win %d file%s over this one." % (
                other, when_text(both, self.cal), n, "" if n == 1 else "s"),
                indent=24, parent=box).pack(anchor="w", pady=(8, 0))
            ttk.Button(box, text="Make this one win over it",
                       command=lambda o=other: self.set_anchor(name, o)).pack(anchor="w",
                                                                             pady=(2, 0))

    # changes

    def changed(self):
        self.fill()
        self.show()
        self.refresh_seasons()
        if getattr(self, "own_frame", None) is not None and self.own_frame.winfo_exists():
            self.own_list()

    def ticked(self, key=None):
        self._focus = key
        name = self.current
        when = [p for p, v in self.vars.items() if v.get()]
        self.set_when(name, when)

    def set_when(self, name, when):
        """Make `name` seasonal, on in `when`, or stop switching it when `when` is empty. A
        mod let go and made seasonal again this session wins over what it did before."""
        if not when:
            if name in self.cal.toggle:
                self._anchors[name] = self.cal.toggle[name]["above"]
            self.cal.take(name)
        elif name in self.cal.toggle:
            self.cal.put(name, when, self.cal.toggle[name]["above"])
        else:
            above = self._anchors.get(name)
            if not above or not self.inst.listed(above) or ce.loops(self.cal.toggle, name, above):
                above = ce.anchor_for(self.inst, name, when, self.cal.toggle)[0] or ""
            self.cal.put(name, when, above)
        self.changed()

    def set_anchor(self, name, above):
        from tkinter import messagebox
        if ce.loops(self.cal.toggle, name, above):
            messagebox.showerror("Wins over", (
                "%s already wins over this mod, so this one can't win over it as well. Pick "
                "another, or change what %s wins over first.") % (above, above),
                parent=self.root)
            self.show()
            return
        self.cal.put(name, self.cal.toggle[name]["when"], above)
        self.changed()

    def remove(self, name):
        if name in self.cal.toggle:
            self._anchors[name] = self.cal.toggle[name]["above"]
        self.cal.take(name)
        self.changed()

    def new_event(self, editing=None):
        """A window of dates, or a rule: days of the week, of the month, which week, which
        months, between which dates, every part of it holding at once. With `editing`, that
        event, to change."""
        tk, ttk = self.tk, self.ttk
        from tkinter import messagebox
        mod = self.current                  # the mod it was opened for, whatever is picked
        old = self.cal.events.get(editing) if editing else None
        win, f = dialog(self.root, "Change event %s" % editing if editing else "New event")
        name = tk.StringVar(value=editing or "")
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Name").pack(side="left")
        name_box = ttk.Entry(row, textvariable=name, width=24)
        name_box.pack(side="left", padx=(8, 0))
        if editing:
            name_box.configure(state="disabled")
        else:
            ttk.Label(row, text="like christmas or weekend", foreground=GREY).pack(
                side="left", padx=8)

        kind = tk.StringVar(value="rule" if isinstance(old, dict) else "dates")
        box = ttk.LabelFrame(f, text="When", padding=10)
        box.pack(fill="x", pady=(10, 0))
        ttk.Radiobutton(box, text="On dates, every year", variable=kind,
                        value="dates").grid(row=0, column=0, columnspan=8, sticky="w")
        start, end = tk.StringVar(), tk.StringVar()
        if isinstance(old, tuple):
            start.set("%d-%d" % old[0])
            end.set("%d-%d" % old[1] if old[1] != old[0] else "")
        ttk.Label(box, text="First day").grid(row=1, column=0, sticky="w", padx=(22, 6))
        ttk.Entry(box, textvariable=start, width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(box, text="Last day").grid(row=1, column=2, sticky="w", padx=(14, 6))
        ttk.Entry(box, textvariable=end, width=8).grid(row=1, column=3, sticky="w")
        ttk.Label(box, text="Month-day, like 12-24. Leave the last day empty for one day.",
                  foreground=GREY).grid(row=2, column=0, columnspan=8, sticky="w",
                                        padx=(22, 0))
        ttk.Radiobutton(box, text="By rule - a day must match every part you fill in",
                        variable=kind, value="rule").grid(row=3, column=0, columnspan=8,
                                                          sticky="w", pady=(12, 0))
        rf = ttk.Frame(box)
        rf.grid(row=4, column=0, columnspan=8, sticky="w", padx=(22, 0))
        rule = lambda *a: kind.set("rule")                      # noqa: E731
        spec_old = old if isinstance(old, dict) else {}
        wd = {d: tk.BooleanVar(value=d in spec_old.get("weekdays", ())) for d in season.WEEKDAYS}
        ttk.Label(rf, text="Days of the week").grid(row=0, column=0, sticky="w", pady=2)
        for i, d in enumerate(season.WEEKDAYS):
            ttk.Checkbutton(rf, text=d.capitalize(), variable=wd[d],
                            command=rule).grid(row=0, column=1 + i, sticky="w")
        words = {v: k for k, v in ce.WEEK_WORDS.items()}
        which = tk.StringVar(value=words.get((spec_old.get("weeks") or (0,))[0], "every one"))
        ttk.Label(rf, text="Which of them").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Combobox(rf, textvariable=which, state="readonly", width=10, values=(
            "every one", "first", "second", "third", "fourth", "fifth", "last")).grid(
            row=1, column=1, columnspan=3, sticky="w")
        ttk.Label(rf, text="in the month", foreground=GREY).grid(row=1, column=4,
                                                                 columnspan=3, sticky="w")
        which.trace_add("write", rule)
        mdays = tk.StringVar(value=", ".join("last" if x == -1 else str(x)
                                             for x in spec_old.get("days", ())))
        mdays.trace_add("write", rule)
        ttk.Label(rf, text="Days of the month").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(rf, textvariable=mdays, width=14).grid(row=2, column=1, columnspan=3,
                                                         sticky="w")
        ttk.Label(rf, text="like 1, 15, last", foreground=GREY).grid(
            row=2, column=4, columnspan=4, sticky="w")
        months = {m: tk.BooleanVar(value=m in spec_old.get("months", ())) for m in range(1, 13)}
        ttk.Label(rf, text="Only in").grid(row=3, column=0, sticky="nw", pady=2)
        mf = ttk.Frame(rf)
        mf.grid(row=3, column=1, columnspan=7, sticky="w")
        for i in range(12):
            ttk.Checkbutton(mf, text=ce.MONTHS[i], variable=months[i + 1],
                            command=rule).grid(row=i // 6, column=i % 6, sticky="w")
        within = spec_old.get("within")
        b1 = tk.StringVar(value="%d-%d" % within[0] if within else "")
        b2 = tk.StringVar(value="%d-%d" % within[1] if within else "")
        b1.trace_add("write", rule)
        b2.trace_add("write", rule)
        ttk.Label(rf, text="Only between").grid(row=4, column=0, sticky="w", pady=2)
        ttk.Entry(rf, textvariable=b1, width=8).grid(row=4, column=1, columnspan=2, sticky="w")
        ttk.Label(rf, text="and").grid(row=4, column=3, sticky="w")
        ttk.Entry(rf, textvariable=b2, width=8).grid(row=4, column=4, columnspan=2, sticky="w")
        start.trace_add("write", lambda *a: kind.set("dates"))
        end.trace_add("write", lambda *a: kind.set("dates"))

        def spec():
            if kind.get() == "dates":
                s = ce.parse_day(start.get())
                e = ce.parse_day(end.get()) if end.get().strip() else s
                return ((s, e), None) if s and e else (None, "Dates are month-day, like 12-24.")
            out = {}
            days = tuple(d for d in season.WEEKDAYS if wd[d].get())
            if days:
                out["weekdays"] = days
            if which.get() != "every one":
                if not days:
                    return None, "Check a day of the week for \"Which of them\" to count."
                out["weeks"] = (ce.WEEK_WORDS[which.get()],)
            if mdays.get().strip():
                md = ce.parse_month_days(re.split(r"[,\s]+", mdays.get().strip()))
                if not md:
                    return None, ("Days of the month are 1 to 31, or last, like "
                                  "1, 15, last.")
                out["days"] = md
            ms = tuple(m for m in range(1, 13) if months[m].get())
            if ms:
                out["months"] = ms
            if b1.get().strip() or b2.get().strip():
                s, e = ce.parse_day(b1.get()), ce.parse_day(b2.get())
                if not s or not e:
                    return None, "\"Only between\" takes two dates, like 12-01 and 02-28."
                out["within"] = (s, e)
            if not out:
                return None, "Give the rule at least one part."
            return out, None

        def ok():
            n = editing or re.sub(r"\s+", "_", name.get().strip().lower())
            if not editing:
                err = None
                if not n:
                    err = "Give the event a name."
                elif not EVENT_NAME.match(n):
                    err = "A name is letters, digits and underscores, like christmas_eve."
                elif n in season.SEASONS or ce.resolve(n, season.SEASONS):
                    err = "\"%s\" is a season's name. Pick another." % n
                elif n in season.WEATHER_NAMES:
                    err = "\"%s\" is a kind of weather. Pick another name." % n
                elif n in self.cal.known():
                    err = ("There is already an event called %s. Change it with its Edit "
                           "button instead." % n)
                if err:
                    messagebox.showerror(win.title(), err, parent=win)
                    return
            sp, err = spec()
            problems = [err] if err else [plain(x) for x in season.event_problems(n, sp)]
            if problems:
                messagebox.showerror(win.title(), "\n".join(problems), parent=win)
                return
            win.destroy()
            if editing:
                self.cal.events[n] = ce.norm_event(sp)
                self.changed()
            else:
                self.add_event(n, spec=sp, mod=mod)

        button_row(f, ("Save" if editing else "Add", ok), ("Cancel", win.destroy))
        win.bind("<Return>", lambda e: ok())
        present(win, self.root, name_box if not editing else None)

    def new_own(self, editing=None):
        """A season of the player's own, new or changed. A new one opened from a mod's page
        is checked for that mod."""
        mod = self.current

        def done(name):
            if editing is None and mod and mod not in self.own:
                when = self.cal.toggle[mod]["when"] if mod in self.cal.toggle else []
                self.set_when(mod, when + [name])
            else:
                self.changed()
        own_season_dialog(self.root, self.cal, editing=editing, done=done)

    def delete_own(self, name):
        if remove_own_season(self.root, self.cal, name):
            self.changed()

    def new_spell(self, editing=None):
        """A spell, new or changed. A new one opened from a mod's page is checked for that
        mod."""
        mod = self.current

        def done(name):
            if editing is None and mod and mod not in self.own:
                when = self.cal.toggle[mod]["when"] if mod in self.cal.toggle else []
                self.set_when(mod, when + [name])
            else:
                self.changed()
        spell_dialog(self.root, self.cal, editing=editing, done=done)

    def delete_spell(self, name):
        if remove_spell(self.root, self.cal, name):
            self.changed()

    def own_list(self):
        """The Seasons tab's list of the player's own seasons."""
        ttk = self.ttk
        for w in self.own_frame.winfo_children():
            w.destroy()
        if not self.cal.own:
            ttk.Label(self.own_frame, text="None yet.", foreground=GREY).pack(anchor="w")
        for n in self.cal.own_order():
            line = ttk.Frame(self.own_frame)
            line.pack(fill="x", pady=1)
            ttk.Label(line, text=n, width=26).pack(side="left")
            ttk.Label(line, text="%s, %d days" % (ce.window_text(self.cal.own[n]),
                                                  season.own_days(self.cal.own[n])),
                      foreground=GREY).pack(side="left")
            ttk.Button(line, text="Delete", command=lambda n=n: self.delete_own(n)).pack(
                side="right")
            ttk.Button(line, text="Edit...", command=lambda n=n: self.new_own(n)).pack(
                side="right", padx=(0, 4))
        for n, raw in self.cal._bad_own.items():
            line = ttk.Frame(self.own_frame)
            line.pack(fill="x", pady=1)
            ttk.Label(line, text=n, foreground=RED, width=26).pack(side="left")
            ttk.Button(line, text="Delete", command=lambda n=n: self.delete_own(n)).pack(
                side="right")
            ttk.Label(line, text="Can't be used. " + " ".join(
                reason(x) for x in season.own_problems({n: raw})), foreground=RED,
                wraplength=300, justify="left").pack(side="left")
        for w in self.spell_frame.winfo_children():
            w.destroy()
        if not (self.cal.spells or self.cal._bad_spells):
            ttk.Label(self.spell_frame, text="None yet.", foreground=GREY).pack(anchor="w")
        for n in sorted(self.cal.spells, key=str.casefold):
            line = ttk.Frame(self.spell_frame)
            line.pack(fill="x", pady=1)
            ttk.Label(line, text=n, width=26).pack(side="left")
            ttk.Button(line, text="Delete", command=lambda n=n: self.delete_spell(n)).pack(
                side="right")
            ttk.Button(line, text="Edit...", command=lambda n=n: self.new_spell(n)).pack(
                side="right", padx=(0, 4))
            ttk.Label(line, text=spell_words(self.cal, self.cal.spells[n]), foreground=GREY,
                      wraplength=330, justify="left").pack(side="left")
        for n, raw in self.cal._bad_spells.items():
            line = ttk.Frame(self.spell_frame)
            line.pack(fill="x", pady=1)
            ttk.Label(line, text=n, foreground=RED, width=26).pack(side="left")
            ttk.Button(line, text="Delete", command=lambda n=n: self.delete_spell(n)).pack(
                side="right")
            ttk.Label(line, text="Can't be used. " + " ".join(
                reason(x) for x in season.spell_problems({n: raw}, own=self.cal.own)),
                foreground=RED, wraplength=300, justify="left").pack(side="left")

    def add_event(self, name, start=None, end=None, spec=None, mod="current"):
        """Add an event, a window from `start` to `end` or a rule `spec`, and check it for
        `mod`: the mod on show when the dialog was opened."""
        self.cal.events[name] = ce.norm_event(spec if spec is not None else (start, end))
        mod = self.current if mod == "current" else mod
        if mod and mod not in self.own:
            when = self.cal.toggle[mod]["when"] if mod in self.cal.toggle else []
            self.set_when(mod, when + [name])
        else:
            self.changed()

    def delete_event(self, name, ask=True):
        """Delete an event and uncheck it everywhere. A mod with nothing else checked stops
        being seasonal, since a mod on for nothing would never be switched on."""
        from tkinter import messagebox
        users = self.cal.users_of(name)
        if ask and not messagebox.askyesno("Delete event", (
                "Delete the event %s?%s" % (name, (
                    "\n\nIt is checked for:\n\n%s\n\nIt is unchecked for each of them, and "
                    "a mod with nothing else checked stops being seasonal." % "\n".join(users))
                    if users else "")), parent=self.root):
            return
        for u in users:
            rest = [p for p in self.cal.toggle[u]["when"] if p != name]
            if rest:
                self.cal.put(u, rest, self.cal.toggle[u]["above"])
            else:
                self._anchors[u] = self.cal.toggle[u]["above"]
                self.cal.take(u)
        self.cal.events.pop(name, None)
        self.cal._bad_events.pop(name, None)
        self.changed()

    # the Seasons tab

    def seasons_tab(self, parent):
        tk, ttk = self.tk, self.ttk
        outer = ttk.Frame(parent, padding=(4, 12))
        outer.pack(fill="both", expand=True)
        right = ttk.Frame(outer)
        right.pack(side="right", fill="y", padx=(12, 0))
        f = ttk.Frame(outer)
        f.pack(side="left", fill="both", expand=True)
        self.dial_panel(right)
        ttk.Label(f, wraplength=520, justify="left", text=(
            "When each season starts, and what it is called. A season runs until the next "
            "one that is on, so a season turned off gives its days to the one before it. "
            "The default is Polesia's own year: the days the land around Chornobyl "
            "changes, not the equinoxes.")).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=(10, 8))
        ttk.Label(row, text="Start from:").pack(side="left")
        ttk.Button(row, text="Polesia (the default)",
                   command=lambda: self.use_dates(ce.polesia())).pack(side="left", padx=6)
        ttk.Button(row, text="Meteorological (month starts)",
                   command=lambda: self.use_dates(ce.meteorological())).pack(side="left")

        grid = ttk.Frame(f)
        grid.pack(anchor="w")
        for col, text in ((1, "Starts"), (3, "Runs"), (4, "Length"), (5, "Called")):
            ttk.Label(grid, text=text, foreground=GREY).grid(row=0, column=col, sticky="w",
                                                            padx=(0, 4))
        fits = root_register = self.root.register(lambda text: len(text) <= season.NAME_CHARS)
        self.srows = {}
        for i, s in enumerate(season.SEASONS, start=1):
            m, d = self.cal.dates.get(s, ce.polesia()[s])
            on = tk.BooleanVar(value=s in self.cal.dates)
            mon, day = tk.StringVar(value=ce.MONTHS[m - 1]), tk.StringVar(value=str(d))
            called = tk.StringVar(value=self.cal.names.get(s) or title(s))
            box = ttk.Checkbutton(grid, text=title(s), variable=on, width=13,
                                  command=self.dates_edited)
            box.grid(row=i, column=0, sticky="w", pady=3)
            cb = ttk.Combobox(grid, textvariable=mon, values=ce.MONTHS, state="readonly",
                              width=5)
            cb.grid(row=i, column=1, sticky="w")
            cb.bind("<<ComboboxSelected>>", lambda e: self.dates_edited())
            sp = ttk.Spinbox(grid, from_=1, to=31, textvariable=day, width=4,
                             command=self.dates_edited)
            sp.grid(row=i, column=2, sticky="w", padx=(4, 0))
            sp.bind("<KeyRelease>", lambda e: self.dates_edited())
            runs = ttk.Label(grid, text="", width=20)
            runs.grid(row=i, column=3, sticky="w", padx=(14, 0))
            days = ttk.Label(grid, text="", width=9, foreground=GREY)
            days.grid(row=i, column=4, sticky="w")
            name = ttk.Entry(grid, textvariable=called, width=22, validate="key",
                             validatecommand=(fits, "%P"))
            name.grid(row=i, column=5, sticky="w")
            name.bind("<KeyRelease>", lambda e: self.names_edited())
            self.srows[s] = (on, mon, day, cb, sp, runs, days, called, name, box)
        del root_register
        ttk.Label(f, text="A name can be up to %d letters." % season.NAME_CHARS,
                  foreground=GREY).pack(anchor="w", pady=(4, 0))
        self.cal_msg = ttk.Label(f, text="", foreground=RED, wraplength=520, justify="left")
        self.cal_msg.pack(anchor="w", pady=(10, 0))
        self.cal_note = ttk.Label(f, text="", foreground=GREY, wraplength=520,
                                  justify="left")
        self.cal_note.pack(anchor="w", pady=(6, 0))
        box = ttk.LabelFrame(f, text="Seasons of your own", padding=8)
        box.pack(fill="x", pady=(12, 0))
        ttk.Label(box, wraplength=500, justify="left", foreground=GREY, text=(
            "Stretches of the year with names of your own, each a week or longer, that run on "
            "top of the season they fall in. Up to %d." % season.OWN_MOST)).pack(anchor="w")
        self.own_frame = ttk.Frame(box)
        self.own_frame.pack(fill="x", pady=(6, 0))
        ttk.Button(box, text="New season of your own...",
                   command=lambda: self.new_own()).pack(anchor="w", pady=(6, 0))
        box = ttk.LabelFrame(f, text="Spells", padding=8)
        box.pack(fill="x", pady=(12, 0))
        ttk.Label(box, wraplength=500, justify="left", foreground=GREY, text=(
            "Short stretches, 1 to %d days, that start by chance in the seasons you pick, and "
            "can bring another season with them." % season.SPELL_MOST_DAYS)).pack(anchor="w")
        self.spell_frame = ttk.Frame(box)
        self.spell_frame.pack(fill="x", pady=(6, 0))
        ttk.Button(box, text="New spell...", command=lambda: self.new_spell()).pack(
            anchor="w", pady=(6, 0))
        self.own_list()
        self.dates_edited(user=False)

    # the dial, drawn as the game will draw it, whenever the calendar or a name changes

    DIAL_PX = 300
    PANEL = (17, 30, 19, 255)               # roughly MCM's panel, which the dial sits on

    def dial_panel(self, parent):
        tk, ttk = self.tk, self.ttk
        box = ttk.LabelFrame(parent, text="The year dial in MCM and on the PDA", padding=10)
        box.pack(anchor="n")
        self._blank = tk.PhotoImage(width=self.DIAL_PX, height=self.DIAL_PX)
        self.dial_view = tk.Label(box, image=self._blank,
                                  background="#%02x%02x%02x" % self.PANEL[:3])
        self.dial_view.pack()
        self.dial_day = tk.IntVar(value=self.today_in_dial_year())
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(8, 0))
        ttk.Scale(row, from_=1, to=365, orient="horizontal", variable=self.dial_day,
                  length=220, command=lambda v: self.dial_later()).pack(side="left")
        ttk.Button(row, text="Today", width=7, command=self.dial_today).pack(
            side="left", padx=(8, 0))
        self.dial_text = ttk.Label(box, text="", justify="center", wraplength=self.DIAL_PX)
        self.dial_text.pack(pady=(6, 0))
        ttk.Label(box, text="Drag to see another day.", foreground=GREY).pack()
        self._dial_job, self._dial_photo, self._bsd = None, None, None
        try:
            import build_season_dial
            from PIL import Image, ImageTk
            self._cols = build_season_dial.season_colors(os.path.join(
                season.MODS, season.SOTZ, "gamedata", "configs", "seasons_of_the_zone.ltx"))
            self._bsd, self._Image, self._ImageTk = build_season_dial, Image, ImageTk
        except ImportError:
            self.dial_text.configure(text="Showing the dial here needs Pillow, a Python "
                                     "package. Save offers to install it once your calendar "
                                     "or names differ from the usual.")
        except OSError:
            self.dial_text.configure(text="The mod's configs folder is missing, so the dial "
                                     "can't be drawn here.")

    @staticmethod
    def today_in_dial_year():
        today = datetime.date.today()
        return datetime.date(2026, today.month, min(today.day, 28 if today.month == 2
                                                    else today.day)).timetuple().tm_yday

    def dial_today(self):
        self.dial_day.set(self.today_in_dial_year())
        self.dial_later()

    def dial_later(self):
        """Draw the dial once the typing stops, not at every key."""
        if self._dial_job:
            self.root.after_cancel(self._dial_job)
        self._dial_job = self.root.after(120, self.draw_dial_preview)

    def draw_dial_preview(self):
        self._dial_job = None
        if self._bsd is None:
            return
        dates = self.cal.dates
        day = datetime.date(2026, 1, 1) + datetime.timedelta(
            days=int(round(float(self.dial_day.get()))) - 1)
        when = "%d %s" % (day.day, ce.MONTHS[day.month - 1])
        lines, _, _ = self.season_problems()
        if lines:
            self.dial_view.configure(image=self._blank)
            self.dial_text.configure(text="%s\nThe dial comes back when the lines in red "
                                     "are fixed." % when)
            return
        bounds = sorted((m, d, s) for s, (m, d) in dates.items())
        _, at = self._bsd.shown(day, bounds)
        im = self._bsd.render(at, self._cols, bounds, dict(self.cal.names))
        im = self._Image.alpha_composite(self._Image.new("RGBA", im.size, self.PANEL), im)
        self._dial_photo = self._ImageTk.PhotoImage(
            im.resize((self.DIAL_PX, self.DIAL_PX), self._Image.LANCZOS))
        self.dial_view.configure(image=self._dial_photo, width=self.DIAL_PX,
                                 height=self.DIAL_PX)
        self.dial_text.configure(text="%s: %s" % (when, title(self._bsd.season_on(day, bounds),
                                                              self.cal)))

    def use_dates(self, dates):
        """Every season on, at `dates`."""
        self._filling = True
        for s, row in self.srows.items():
            on, mon, day = row[:3]
            m, d = dates[s]
            on.set(True)
            mon.set(ce.MONTHS[m - 1])
            day.set(str(d))
        self._filling = False
        self.dates_edited()

    def set_dates(self, dates):
        """The Seasons tab showing `dates`: the seasons in it on, at those days, the rest
        off where they were. As typing them in would."""
        self._filling = True
        for s, row in self.srows.items():
            on, mon, day = row[:3]
            on.set(s in dates)
            if s in dates:
                mon.set(ce.MONTHS[dates[s][0] - 1])
                day.set(str(dates[s][1]))
        self._filling = False
        self.dates_edited()

    def reload_seasons(self):
        """The Seasons tab showing the setup as it now is, after a preset or a save."""
        self._filling = True
        for s, row in self.srows.items():
            on, mon, day, called = row[0], row[1], row[2], row[7]
            on.set(s in self.cal.dates)
            if s in self.cal.dates:
                mon.set(ce.MONTHS[self.cal.dates[s][0] - 1])
                day.set(str(self.cal.dates[s][1]))
            called.set(self.cal.names.get(s) or title(s))
        self._filling = False
        self.own_list()
        self.dates_edited(user=False)

    def dates_edited(self, user=True):
        if self._filling:
            return
        dates, bad = {}, []
        for s, row in self.srows.items():
            on, mon, day, cb, sp = row[:5]
            m = ce.MONTHS.index(mon.get()) + 1
            d = int(day.get()) if DAY_BOX.match(day.get()) else 0
            last = 28 if m == 2 else ce.DAYS[m - 1]
            if d > last:
                d = last
                self._filling = True
                day.set(str(d))
                self._filling = False
            cb.configure(state="readonly" if on.get() else "disabled")
            sp.configure(state="normal" if on.get() else "disabled")
            if on.get():
                if d < 1:
                    bad.append(s)
                else:
                    dates[s] = (m, d)
        self.bad_dates = [title(s, self.cal) for s in bad]
        self._bad_rows = set(bad)
        if not bad and user:
            self.cal.set_dates(dates)
        self.refresh_seasons()

    def names_edited(self):
        if self._filling:
            return
        self.cal.set_names({s: row[7].get() for s, row in self.srows.items()})
        self.refresh_seasons()
        # the mod list shows the names too: redrawn once the typing stops
        if self._names_job:
            self.root.after_cancel(self._names_job)
        self._names_job = self.root.after(400, self.names_settled)

    def names_settled(self):
        self._names_job = None
        self.fill()
        self.show()

    def season_problems(self):
        """What is wrong on the Seasons tab, in its own words: (lines, the seasons at fault,
        whether the dates are what is wrong)."""
        out, rows = [], set(getattr(self, "_bad_rows", ()))
        if self.bad_dates:
            out.append("Give %s a start day." % " and ".join(self.bad_dates))
        dates = self.cal.dates
        if not dates:
            out.append("Check at least one season.")
        elif not out:
            seen = {}
            for s, md in sorted(dates.items(), key=lambda kv: season.SEASONS.index(kv[0])):
                if md in seen:
                    out.append("%s and %s both start on %s." % (
                        title(seen[md], self.cal), title(s, self.cal), ce.day_text(md)))
                    rows |= {s, seen[md]}
                seen.setdefault(md, s)
            if not out and len(dates) > 1:
                for s, n in season.season_lengths(dates).items():
                    if n < season.MIN_SEASON_DAYS:
                        out.append("%s would last %d day%s; each season needs at least %d." % (
                            title(s, self.cal), n, "" if n == 1 else "s",
                            season.MIN_SEASON_DAYS))
                        rows.add(s)
            if not out and self.cal.calendar_bad:
                out.append("The calendar in seasons_config.py can't be used as it is. Set "
                           "the dates here to replace it.")
        dated = bool(out)
        shown = {}
        for s, n in self.cal.names.items():
            if any(ord(c) < 32 for c in n) or any(c in n for c in ";[]"):
                out.append("%s's name can't hold ; [ or ]." % season.default_label(s).capitalize())
                rows.add(s)
            else:
                try:
                    n.encode("cp1251")
                except UnicodeEncodeError:
                    out.append("%s's name has letters the game can't show. It takes English and "
                               "Cyrillic letters." % season.default_label(s).capitalize())
                    rows.add(s)
        for s in season.SEASONS:
            key = season.season_label(s, self.cal.names).casefold()
            if key in shown:
                out.append("%s and %s would both be called \"%s\"." % (
                    season.default_label(shown[key]).capitalize(),
                    season.default_label(s).capitalize(), season.season_label(s, self.cal.names)))
                rows |= {s, shown[key]}
            shown.setdefault(key, s)
        if not out and dates:
            # anything else season.py's own rules refuse, in their words
            out += [plain(p) for p in season.calendar_problems(dates)
                    + season.names_problems(self.cal.names)]
        return out, rows, dated

    def refresh_seasons(self):
        dates = self.cal.dates
        lines, rows, dated = self.season_problems()
        wins = ce.season_windows(dates) if dates and not dated else {}
        days = season.season_lengths(dates) if dates and not dated else {}
        for s, row in self.srows.items():
            runs, dl, box = row[5], row[6], row[9]
            runs.configure(text=wins.get(s, "") if s in dates else "off",
                           foreground="#000000" if s in dates else "#888888")
            dl.configure(text="%d days" % days[s] if s in days else "")
            box.configure(style="Bad.TCheckbutton" if s in rows else "TCheckbutton")
        self.cal_msg.configure(text="\n".join(lines))
        notes = []
        mine = self.cal.custom() or self.cal.names
        if not mine:
            notes.append("These are Polesia's dates, with the usual names.")
        elif have_pillow():
            notes.append("Saving sends these dates and names to the game and redraws the "
                         "year dial in MCM and on the PDA.")
        else:
            notes.append("Saving sends these dates and names to the game. The year dial in "
                         "MCM and on the PDA stays hidden until Pillow is installed; Save "
                         "offers to install it.")
        lost = stranded(self.cal, dates)
        if lost:
            notes.append("These seasonal mods are on only in seasons that are off, so they "
                         "never switch on: " + ", ".join(lost))
        self.cal_note.configure(text="\n\n".join(notes))
        if not dated and wins != self.windows:
            self.windows = wins
            self.fill()
            self.show()
        self.dial_later()
        self.update_status()

    # the Weather tab: where the real weather comes from

    def weather_tab(self, parent):
        tk, ttk = self.tk, self.ttk
        try:
            import fetch_weather as fw
        except ImportError:
            fw = None           # an old _tools: the rest of the window works without it
        self._fw, self._found = fw, []
        f = ttk.Frame(parent, padding=(4, 12))
        f.pack(fill="both", expand=True)
        ttk.Label(f, wraplength=760, justify="left", text=(
            "The PDA's temperature, its Forecast page and the freezing, thaw and heat days "
            "all follow the real weather at one place. play.bat asks open-meteo.com for that "
            "place's day at each launch, sending its coordinates and nothing else. The "
            "seasons don't move with it: set those on the Seasons tab.")).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(14, 0))
        ttk.Label(row, text="Weather from:").pack(side="left")
        self.place_now = ttk.Label(row, text="", style="Head.TLabel")
        self.place_now.pack(side="left", padx=(8, 0))
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Today's weather there", command=self.check_place).pack(
            side="left")
        self.place_back = ttk.Button(row, text="Back to Chornobyl",
                                     command=lambda: self.use_place(None))
        self.place_back.pack(side="left", padx=(6, 0))
        self.place_check = ttk.Label(f, text="", justify="left")
        self.place_check.pack(anchor="w", pady=(8, 0))
        self.place_check_credit = credit(f, WEATHER_CREDIT)

        box = ttk.LabelFrame(f, text="Find a place", padding=10)
        box.pack(fill="x", pady=(16, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.place_query = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.place_query, width=34)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.find_place())
        ttk.Button(row, text="Search", command=self.find_place).pack(side="left", padx=(6, 0))
        ttk.Label(row, text="a town or city, like Kyiv or New York", foreground=GREY).pack(
            side="left", padx=(10, 0))
        self.place_found = tk.Listbox(box, height=6, width=80, exportselection=False,
                                      activestyle="dotbox")
        self.place_found.pack(anchor="w", pady=(8, 0))
        self.place_found.bind("<Double-Button-1>", lambda e: self.use_found())
        self.place_found.bind("<Return>", lambda e: self.use_found())
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Use this place", command=self.use_found).pack(side="left")
        self.place_msg = ttk.Label(row, text="", foreground=GREY)
        self.place_msg.pack(side="left", padx=(10, 0))
        credit(box, PLACES_CREDIT).pack(anchor="w", pady=(6, 0))

        box = ttk.LabelFrame(f, text="Or give its coordinates", padding=10)
        box.pack(fill="x", pady=(10, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.place_lat, self.place_lon, self.place_name = (tk.StringVar(), tk.StringVar(),
                                                           tk.StringVar())
        for text, var, width in (("Latitude", self.place_lat, 9),
                                 ("Longitude", self.place_lon, 9),
                                 ("Name", self.place_name, 26)):
            ttk.Label(row, text=text).pack(side="left", padx=(0 if text == "Latitude" else 12,
                                                              6))
            ttk.Entry(row, textvariable=var, width=width).pack(side="left")
        ttk.Button(row, text="Use these", command=self.use_coords).pack(side="left",
                                                                         padx=(12, 0))
        ttk.Label(box, text="In degrees, north and east positive: 51.28 and 30.22 is "
                  "Chornobyl.", foreground=GREY).pack(anchor="w", pady=(6, 0))

        ttk.Label(f, wraplength=760, justify="left", foreground=GREY, text=(
            "For a place of your own, saving also looks up its climate once - its last ten "
            "years of highs and lows - so the game can model a day there without a "
            "connection.")).pack(anchor="w", pady=(14, 0))
        credit(f, CLIMATE_CREDIT).pack(anchor="w", pady=(4, 0))
        self.show_place()

    def show_place(self):
        """The Weather tab showing the place as it now is, saved or not."""
        self.place_now.configure(text=ce.place_text(self.cal.place)
                                 + ("" if self.cal.place else ", the default"))
        self.place_back.configure(state="normal" if self.cal.place else "disabled")
        self.place_check.configure(text="")
        self.place_check_credit.pack_forget()

    def use_place(self, place):
        self.cal.set_place(place)
        self.show_place()
        self.changed()

    def in_background(self, work, done):
        """Run `work` off the window's thread - a web request, say - and `done(result,
        error)` on it once it is back, so the window keeps answering meanwhile."""
        import queue
        import threading
        q = queue.Queue()

        def run():
            try:
                q.put((work(), None))
            except Exception as e:
                q.put((None, e))

        def poll():
            try:
                result, error = q.get_nowait()
            except queue.Empty:
                self.root.after(80, poll)
                return
            done(result, error)

        threading.Thread(target=run, daemon=True).start()
        self.root.after(80, poll)

    def missing_fetcher(self, label):
        """Say so when _tools has no fetch_weather.py, which looks places up."""
        if self._fw is None:
            label.configure(text="_tools\\fetch_weather.py is missing. Copy _tools from the "
                            "mod's folder again.", foreground=RED)
        return self._fw is None

    def find_place(self):
        if self.missing_fetcher(self.place_msg):
            return
        text = self.place_query.get().strip()
        if not text:
            self.place_msg.configure(text="Type a place to look for.", foreground=RED)
            return
        self.place_msg.configure(text="Looking it up...", foreground=GREY)
        self.place_found.delete(0, "end")
        self._found = []

        def done(found, error):
            if error is not None:
                self.place_msg.configure(text="Couldn't reach open-meteo.com (%s). Give the "
                                         "coordinates below instead." % type(error).__name__,
                                         foreground=RED)
                return
            self._found = found
            for p in found:
                self.place_found.insert("end", found_text(p))
            if found:
                self.place_found.selection_set(0)
                self.place_found.focus_set()
            self.place_msg.configure(
                text=("%d found. Pick one and press Use this place." % len(found)) if found
                else "Nothing by that name. Try another spelling.",
                foreground=GREY if found else RED)

        self.in_background(lambda: self._fw.search(text), done)

    def use_found(self):
        sel = self.place_found.curselection()
        if not sel or sel[0] >= len(self._found):
            self.place_msg.configure(text="Pick a place in the list first.", foreground=RED)
            return
        f = self._found[sel[0]]
        self.use_place({"name": f["name"][:season.PLACE_CHARS].strip(), "lat": f["lat"],
                        "lon": f["lon"]})
        self.place_msg.configure(text="Now %s - not saved yet." % f["name"],
                                 foreground=GREY)

    def use_coords(self):
        from tkinter import messagebox

        def number(v):
            try:
                return float(v.strip().replace(",", "."))
            except ValueError:
                return None

        lat, lon = number(self.place_lat.get()), number(self.place_lon.get())
        if lat is None or lon is None:
            messagebox.showerror("Weather", "Give the latitude and longitude as numbers, "
                                 "like 50.45 and 30.52.", parent=self.root)
            return
        place = {"name": self.place_name.get().strip() or "%.2f, %.2f" % (lat, lon),
                 "lat": lat, "lon": lon}
        problems = season.place_problems(place)
        if problems:
            messagebox.showerror("Weather", "\n".join(plain(p) for p in problems),
                                 parent=self.root)
            return
        self.use_place(place)

    def check_place(self):
        if self.missing_fetcher(self.place_check):
            return
        place = self.cal.place or ce.DEFAULT_PLACE
        self.place_check.configure(text="Asking open-meteo.com...", foreground=GREY)
        self.place_check_credit.pack_forget()

        def done(rows, error):
            if error is not None or not rows:
                self.place_check.configure(text="Couldn't reach open-meteo.com (%s)."
                                           % type(error).__name__, foreground=RED)
                return
            t = rows[0]
            self.place_check.configure(foreground="#000000", text=(
                "Today in %s: high %.0f\u00b0C (%.0f\u00b0F), low %.0f\u00b0C (%.0f\u00b0F), "
                "%s." % (place["name"], t["high"], t["high"] * 9 / 5 + 32, t["low"],
                         t["low"] * 9 / 5 + 32, SKY.get(t["cycle"], t["cycle"]))))
            self.place_check_credit.pack(anchor="w", after=self.place_check)

        self.in_background(lambda: self._fw.to_rows(self._fw.fetch(place)), done)

    # saving

    def refused(self):
        return refused_lines(self.cal)

    def update_status(self):
        n = len(self.cal.toggle)
        text = "%d seasonal mod%s" % (n, "" if n == 1 else "s")
        if self.cal.custom():
            on = len(self.cal.dates)
            text += ", own dates (%d season%s on)" % (on, "" if on == 1 else "s")
        if self.cal.names:
            text += ", %d renamed" % len(self.cal.names)
        if self.cal.place:
            text += ", weather from %s" % self.cal.place["name"]
        self.status.configure(text=text)
        dirty = self.cal.dirty() or bool(self.bad_dates)
        self.unsaved.configure(text="Unsaved changes" if dirty else "")
        self.root.title(("* " if dirty else "") + TITLE)
        self.show_banner()

    def show_banner(self):
        """What holds Save back, each with a way to it: a mod's problem shows the mod, an
        event that can't be used can be deleted from here."""
        ttk = self.ttk
        for w in self.banner.winfo_children():
            w.destroy()
        raw = [] if self.cal.error else self.cal.check(self.cal.render()[0])
        if not raw:
            return
        box = ttk.LabelFrame(self.banner, text="Save is held back until these are fixed",
                             padding=8)
        box.pack(fill="x", pady=(8, 0))
        for p in raw[:4]:
            line = ttk.Frame(box)
            line.pack(fill="x")
            m = re.match(r"^([A-Z_]+)(?:\[(['\"])(.*?)\2\])?", p)
            table, key = (m.group(1), m.group(3)) if m else (None, None)
            if table == "EVENTS" and key in self.cal._bad_events:
                ttk.Button(line, text="Delete event",
                           command=lambda k=key: self.delete_event(k)).pack(side="right")
            elif table == "TOGGLE_MODS" and key in self.cal.toggle:
                ttk.Button(line, text="Show the mod",
                           command=lambda k=key: self.show_mod(k)).pack(side="right")
            elif table in ("CALENDAR", "NAMES"):
                ttk.Button(line, text="Show the seasons",
                           command=lambda: self.tabs.select(1)).pack(side="right")
            ttk.Label(line, text="- " + plain(p), foreground=RED, wraplength=900,
                      justify="left").pack(side="left", anchor="w")
        if len(raw) > 4:
            ttk.Label(box, text="and %d more" % (len(raw) - 4), foreground=RED).pack(
                anchor="w")

    def show_mod(self, name):
        """The Mods tab, with `name` picked, whatever the list was filtered to."""
        self.tabs.select(0)
        if not self.tree.exists(name):
            self.search.set("")
            self.only_ours.set(False)
            self.fill()
        self.select(name)

    def save(self, quiet=False):
        from tkinter import messagebox
        if self.bad_dates:
            if not quiet:
                messagebox.showerror("Save", "Give %s a start day first, on the Seasons tab."
                                     % " and ".join(self.bad_dates), parent=self.root)
            return False
        moved = calendar_moved(self.cal)
        placed = self.cal.place_changed()
        saved, lines = self.cal.save()
        if saved and lines != ["Nothing to save."]:
            self.root.configure(cursor="watch")
            self.root.update()
            if moved:
                ok, out = draw_dial()
                lines = lines + [""] + (dial_sentence(self.cal) if ok else out)
            if placed:
                lines = lines + ["", "The weather now comes from %s:"
                                 % ce.place_text(self.cal.place)] + fetch_now()
            self.root.configure(cursor="")
            lines = lines + ["", "play.bat applies it the next time it starts the game."]
        if not saved:
            lines = [plain(l) for l in lines]
        if not quiet:
            if saved and moved and self._dial_photo is not None:
                self.saved_with_dial(lines)
            else:
                (messagebox.showinfo if saved else messagebox.showerror)(
                    "Save", "\n".join(lines), parent=self.root)
            if saved and moved and (self.cal.custom() or self.cal.names) and not have_pillow():
                self.offer_pillow()
        self.reload_seasons()
        self.show_place()
        self.fill()
        self.show()
        self.update_status()
        return saved

    def saved_with_dial(self, lines):
        """The save message with the dial the game now has: the calendar or a name changed."""
        tk, ttk = self.tk, self.ttk
        win, f = dialog(self.root, "Saved")
        tk.Label(f, image=self._dial_photo, background="#%02x%02x%02x" % self.PANEL[:3]).pack()
        ttk.Label(f, text="The dial the game shows from its next start.",
                  foreground=GREY).pack(pady=(6, 0))
        ttk.Label(f, text="\n".join(lines), justify="left", wraplength=420).pack(
            anchor="w", pady=(10, 0))
        ok, = button_row(f, ("OK", win.destroy))
        win.bind("<Return>", lambda e: win.destroy())
        present(win, self.root, ok)
        self.root.wait_window(win)

    def offer_pillow(self):
        offer_pillow(self.root)
        self.refresh_seasons()

    # presets

    def load_preset(self):
        tk, ttk = self.tk, self.ttk
        from tkinter import messagebox
        files = ce.preset_files()
        if not files:
            messagebox.showinfo("Load preset", "There are no presets yet. Save one, or put a "
                                "preset file in _tools\\presets.", parent=self.root)
            return
        win, f = dialog(self.root, "Load preset")
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True)
        box = tk.Listbox(body, height=12, width=28, exportselection=False,
                         activestyle="dotbox")
        box.grid(row=0, column=0, rowspan=4, sticky="ns")
        for n in files:
            box.insert("end", n)
        about = ttk.Label(body, text="", wraplength=400, justify="left")
        about.grid(row=0, column=1, sticky="nw", padx=(14, 0))
        pick = {p: tk.BooleanVar(value=True) for p in ce.PARTS}
        checks = ttk.Frame(body)
        checks.grid(row=1, column=1, sticky="nw", padx=(14, 0), pady=(10, 0))
        ttk.Label(checks, text="Load these parts. Each replaces the same part of your "
                  "setup:", wraplength=400, justify="left").pack(anchor="w")
        boxes = {p: ttk.Checkbutton(checks, text=ce.PART_TEXT[p], variable=pick[p],
                                    command=lambda: show())
                 for p in ce.PARTS}
        for b in boxes.values():
            b.pack(anchor="w")
        what = ttk.Label(body, text="", wraplength=400, justify="left", foreground=GREY)
        what.grid(row=2, column=1, sticky="nw", padx=(14, 0), pady=(10, 0))
        lose = ttk.Label(body, text="", wraplength=400, justify="left", foreground=AMBER)
        lose.grid(row=4, column=1, sticky="nw", padx=(14, 0), pady=(8, 0))
        note = ttk.Label(body, text="", foreground=RED, wraplength=400, justify="left")
        note.grid(row=3, column=1, sticky="nw", padx=(14, 0), pady=(8, 0))
        held = {}

        def show(e=None):
            sel = box.curselection()
            if not sel:
                return
            name = box.get(sel[0])
            if held.get("name") != name:
                p, problems = ce.read_preset(files[name])
                held.update(name=name, preset=p, problems=problems)
                have = ce.preset_parts(p) if p else []
                for part, b in boxes.items():
                    b.configure(state="normal" if part in have else "disabled")
                    pick[part].set(part in have)
            p, problems = held["preset"], held["problems"]
            about.configure(text=(p["about"] if p and p["about"] else name))
            parts = [x for x in ce.PARTS if pick[x].get() and p and x in ce.preset_parts(p)]
            lines, losses = (ce.preset_effect(self.cal, self.inst, p, parts)
                             if p and not problems and parts else ([], []))
            what.configure(text="\n".join(lines))
            lose.configure(text="It takes the place of %s." % " and ".join(losses)
                           if losses else "")
            note.configure(text="\n".join(["This preset can't be used:"]
                                          + [plain(x) for x in problems]) if problems else "")

        box.bind("<<ListboxSelect>>", show)

        def load():
            p = held.get("preset")
            if not p or held.get("problems"):
                return
            parts = [x for x in ce.PARTS if pick[x].get() and x in ce.preset_parts(p)]
            if not parts:
                messagebox.showerror("Load preset", "Check at least one part to load.",
                                     parent=win)
                return
            said = ce.apply_preset(self.cal, self.inst, p, parts)
            win.destroy()
            self.reload_seasons()
            self.changed()
            messagebox.showinfo("Load preset", "\n".join(
                ["Loaded %s. It is not saved yet." % held["name"], ""] + said
                + ["", "Click Save to keep it, or close without saving to leave your setup "
                       "as it was."]), parent=self.root)

        box.bind("<Double-Button-1>", lambda e: load())
        button_row(f, ("Load", load), ("Cancel", win.destroy))
        win.bind("<Return>", lambda e: load())
        box.selection_set(0)
        show()
        present(win, self.root, box)

    def save_preset(self):
        from tkinter import messagebox
        if self.bad_dates:
            messagebox.showerror("Save preset", "Give %s a start day first, on the Seasons tab."
                                 % " and ".join(self.bad_dates), parent=self.root)
            return
        save_preset_dialog(self.root, self.cal)

    def preview(self):
        show_preview(self.root, self.cal)

    def close(self):
        from tkinter import messagebox
        if self.cal.dirty() or self.bad_dates:
            ans = messagebox.askyesnocancel("Close", "Save your changes?", parent=self.root)
            if ans is None:
                return
            if ans and not self.save():
                return
        self.root.destroy()


def refused_lines(cal):
    """What season.py would refuse in the setup `cal` holds, in the window's words."""
    if cal.error:
        return []
    return [plain(p) for p in cal.check(cal.render()[0])]


def offer_pillow(root):
    """Offer to install Pillow, which drawing a dial of your own needs, and draw it."""
    from tkinter import messagebox
    if not messagebox.askyesno("The year dial", (
            "The dial in MCM and on the PDA shows Polesia's dates and names, so it is "
            "hidden while your own are in use. Drawing one for them needs Pillow, a "
            "Python package.\n\nInstall it now? This runs:\n\n"
            "    py -m pip install pillow"), parent=root):
        return
    root.configure(cursor="watch")
    root.update()
    r = subprocess.run([sys.executable, "-m", "pip", "install", "pillow"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    root.configure(cursor="")
    if r.returncode != 0:
        messagebox.showerror("The year dial", "pip could not install Pillow. The dial "
                             "stays hidden; everything else is saved. pip said:\n\n"
                             + "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:]),
                             parent=root)
        return
    ok, out = draw_dial()
    (messagebox.showinfo if ok else messagebox.showerror)(
        "The year dial", "\n".join(["Pillow is installed.", ""] + out
                                   + ["", "Close and open configure.bat again to see "
                                          "the dial here too."]), parent=root)


def own_window_words(cal, win):
    """A season of the player's own in words: how long it runs, and on top of what."""
    year = [datetime.date(2026, 1, 1) + datetime.timedelta(days=i) for i in range(365)]
    days = [d for d in year if season._in_window(d, *win)]
    under = [s for s in season.SEASONS if s in cal.dates and cal.days(s) & set(days)]
    return "Runs %d days, %s, on top of %s." % (
        len(days), ce.window_text(win), season._and(label(s, cal) for s in under)
        if under else "no season")


def own_season_dialog(root, cal, editing=None, done=None):
    """Add a season of the player's own to `cal`, or change the one called `editing`: its
    name and its first and last day, checked as they are typed. `done(name)` runs once it
    is in `cal`; nothing is saved here."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    if editing is None and len(cal.own) >= season.OWN_MOST:
        messagebox.showinfo(TITLE, "You have %d seasons of your own, as many as the year has "
                            "room for, a week each. Remove one to add another."
                            % len(cal.own), parent=root)
        return
    old = cal.own.get(editing) if editing else None
    if old is None:
        # the whole of next month, to start from
        t = datetime.date.today()
        m = t.month % 12 + 1
        old = ((m, 1), (m, 28 if m == 2 else ce.DAYS[m - 1]))
    win, f = dialog(root, "Change %s" % editing if editing else "A season of your own")
    ttk.Label(f, wraplength=470, justify="left", text=(
        "A stretch of the year with a name of your own, a week or longer. It runs on top of "
        "the season it falls in: the mods you put on in it come on for those days, and the "
        "season's own mods stay on.")).pack(anchor="w")
    grid = ttk.Frame(f)
    grid.pack(anchor="w", pady=(12, 0))
    fits = root.register(lambda text: len(text) <= season.OWN_NAME_CHARS)
    name = tk.StringVar(value=editing or "")
    ttk.Label(grid, text="Name").grid(row=0, column=0, sticky="w", pady=3)
    box = ttk.Entry(grid, textvariable=name, width=28, validate="key",
                    validatecommand=(fits, "%P"))
    box.grid(row=0, column=1, columnspan=3, sticky="w", padx=(10, 0))
    ttk.Label(grid, text="like Wormhole season", foreground=GREY).grid(
        row=0, column=4, sticky="w", padx=(10, 0))
    ends = []
    for r, (text, md) in enumerate((("First day", old[0]), ("Last day", old[1])), start=1):
        mon, day = tk.StringVar(value=ce.MONTHS[md[0] - 1]), tk.StringVar(value=str(md[1]))
        ttk.Label(grid, text=text).grid(row=r, column=0, sticky="w", pady=3)
        cb = ttk.Combobox(grid, textvariable=mon, values=ce.MONTHS, state="readonly",
                          width=5)
        cb.grid(row=r, column=1, sticky="w", padx=(10, 0))
        sp = ttk.Spinbox(grid, from_=1, to=31, textvariable=day, width=4)
        sp.grid(row=r, column=2, sticky="w", padx=(4, 0))
        ends.append((mon, day, cb, sp))
    words = ttk.Label(f, text="", wraplength=470, justify="left")
    words.pack(anchor="w", pady=(12, 0))

    def read():
        """(name, window, problems) as the dialog stands."""
        n = name.get().strip()
        md = []
        for mon, day, _, _ in ends:
            m = ce.MONTHS.index(mon.get()) + 1
            d = int(day.get()) if DAY_BOX.match(day.get()) else 0
            md.append((m, min(d, 28 if m == 2 else ce.DAYS[m - 1])))
        w = (md[0], md[1])
        if not n:
            return n, w, ["Give it a name."]
        if not all(d for _, d in md):
            return n, w, ["Give it a first and a last day."]
        if any(o.casefold() == n.casefold() and o != editing for o in cal.own):
            return n, w, ["You have a season called %s already." % n]
        trial = {o: x for o, x in cal.own.items() if o != editing}
        trial[n] = w
        return n, w, [plain(p) for p in season.own_problems(trial, cal.periods, cal.events,
                                                             cal.names)]

    def show(*a):
        n, w, problems = read()
        if problems and not (problems == ["Give it a name."] and not name.get()):
            words.configure(text="\n".join(problems), foreground=RED)
        else:
            words.configure(text=own_window_words(cal, w), foreground=GREY)

    def ok():
        n, w, problems = read()
        if problems:
            messagebox.showerror(win.title(), "\n".join(problems), parent=win)
            return
        cal.put_own(n, w, was=editing)
        win.destroy()
        if done:
            done(n)

    name.trace_add("write", show)
    for mon, day, _, _ in ends:
        mon.trace_add("write", show)
        day.trace_add("write", show)
    show()
    button_row(f, ("Save" if editing else "Add", ok), ("Cancel", win.destroy))
    win.bind("<Return>", lambda e: ok())
    present(win, root, box)
    return win


def spell_dialog(root, cal, editing=None, done=None):
    """Add a spell to `cal`, or change the one called `editing`: where it can start, the
    chance each day, how long it runs and the season it brings, checked as they are set.
    `done(name)` runs once it is in `cal`; nothing is saved here."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    old = cal.spells.get(editing) if editing else None
    old = old or {"in": ("summer",) if "summer" in cal.dates else (sorted(cal.dates)[:1]),
                  "chance": 3, "days": (1, 2),
                  "as": "winter" if "winter" in cal.dates else None}
    win, f = dialog(root, "Change %s" % editing if editing else "A spell")
    ttk.Label(f, wraplength=500, justify="left", text=(
        "A short stretch that starts by chance. On each day of the seasons you check, there "
        "is a chance it starts; then it runs a day or a few. It can bring another season with "
        "it - winter for a day or two in summer - or leave the season as it is and switch on "
        "only the mods you put on during it. The date decides, so every launch that day "
        "agrees.")).pack(anchor="w")
    grid = ttk.Frame(f)
    grid.pack(anchor="w", pady=(12, 0))
    fits = root.register(lambda text: len(text) <= season.OWN_NAME_CHARS)
    name = tk.StringVar(value=editing or "")
    ttk.Label(grid, text="Name").grid(row=0, column=0, sticky="w", pady=3)
    box = ttk.Entry(grid, textvariable=name, width=28, validate="key",
                    validatecommand=(fits, "%P"))
    box.grid(row=0, column=1, columnspan=5, sticky="w", padx=(10, 0))
    ttk.Label(grid, text="Can start in").grid(row=1, column=0, sticky="nw", pady=3)
    starts = ttk.Frame(grid)
    starts.grid(row=1, column=1, columnspan=5, sticky="w", padx=(10, 0))
    places = [s for s in season.SEASONS if s in cal.dates] + cal.own_order()
    start_vars = {}
    for i, p in enumerate(places):
        v = tk.BooleanVar(value=p in old["in"])
        start_vars[p] = v
        ttk.Checkbutton(starts, text=title(p, cal) if p in season.SEASONS else p,
                        variable=v).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 12))
    chance = tk.StringVar(value="%g" % old["chance"])
    ttk.Label(grid, text="Chance each day").grid(row=2, column=0, sticky="w", pady=3)
    odds = ttk.Frame(grid)
    odds.grid(row=2, column=1, columnspan=5, sticky="w", padx=(10, 0))
    ttk.Spinbox(odds, from_=0.5, to=100, increment=0.5, textvariable=chance, width=6).pack(
        side="left")
    ttk.Label(odds, text="%").pack(side="left", padx=(4, 0))
    lo, hi = tk.StringVar(value=str(old["days"][0])), tk.StringVar(value=str(old["days"][1]))
    ttk.Label(grid, text="Runs").grid(row=3, column=0, sticky="w", pady=3)
    lasts = ttk.Frame(grid)
    lasts.grid(row=3, column=1, columnspan=5, sticky="w", padx=(10, 0))
    ttk.Spinbox(lasts, from_=1, to=season.SPELL_MOST_DAYS, textvariable=lo, width=4).pack(
        side="left")
    ttk.Label(lasts, text="to").pack(side="left", padx=6)
    ttk.Spinbox(lasts, from_=1, to=season.SPELL_MOST_DAYS, textvariable=hi, width=4).pack(
        side="left")
    ttk.Label(lasts, text="days").pack(side="left", padx=(6, 0))
    stays = "no other season"
    choices = [stays] + [title(s, cal) for s in season.SEASONS if s in cal.dates]
    keys = [None] + [s for s in season.SEASONS if s in cal.dates]
    brings = tk.StringVar(value=choices[keys.index(old["as"])] if old["as"] in keys
                          else stays)
    ttk.Label(grid, text="Brings").grid(row=4, column=0, sticky="w", pady=3)
    ttk.Combobox(grid, textvariable=brings, values=choices, state="readonly", width=16).grid(
        row=4, column=1, columnspan=4, sticky="w", padx=(10, 0))
    words = ttk.Label(f, text="", wraplength=500, justify="left")
    words.pack(anchor="w", pady=(12, 0))

    def number(text, whole=False):
        try:
            v = float(text.strip().rstrip("%"))
        except ValueError:
            return None
        return int(v) if (whole or v == int(v)) and v == int(v) else (None if whole else v)

    def read():
        """(name, spec, problems) as the dialog stands."""
        n = name.get().strip()
        spec = {"in": tuple(p for p in places if start_vars[p].get()),
                "chance": number(chance.get()),
                "days": (number(lo.get(), True), number(hi.get(), True)),
                "as": keys[choices.index(brings.get())]}
        if not n:
            return n, spec, ["Give it a name."]
        if not spec["in"]:
            return n, spec, ["Check a season it can start in."]
        if spec["chance"] is None or None in spec["days"]:
            return n, spec, ["The chance and the days are numbers."]
        if any(o.casefold() == n.casefold() and o != editing for o in cal.spells):
            return n, spec, ["You have a spell called %s already." % n]
        trial = {o: x for o, x in cal.spells.items() if o != editing}
        trial[n] = spec
        return n, spec, [plain(p) for p in season.spell_problems(
            trial, list(cal.dates), cal.own, cal.periods, cal.events, cal.names)]

    def show(*a):
        n, spec, problems = read()
        if problems and not (problems == ["Give it a name."] and not name.get()):
            words.configure(text="\n".join(problems), foreground=RED)
            return
        text = spell_words(cal, ce.norm_spell(spec))
        words.configure(text=text[:1].upper() + text[1:] + ".", foreground=GREY)

    def ok():
        n, spec, problems = read()
        if problems:
            messagebox.showerror(win.title(), "\n".join(problems), parent=win)
            return
        cal.put_spell(n, spec, was=editing)
        win.destroy()
        if done:
            done(n)

    name.trace_add("write", show)
    for v in list(start_vars.values()) + [chance, lo, hi, brings]:
        v.trace_add("write", show)
    show()
    button_row(f, ("Save" if editing else "Add", ok), ("Cancel", win.destroy))
    win.bind("<Return>", lambda e: ok())
    present(win, root, box)
    return win


def remove_spell(root, cal, name):
    """Take a spell off `cal` and off the mods on during it, once the player says so when
    there are any. True when it was taken off; nothing is saved here."""
    from tkinter import messagebox
    users = cal.users_of(name)
    if users:
        only = [u for u in users if all(p == name for p in cal.toggle[u]["when"])]
        text = ("Remove %s? These mods are on during it:\n\n%s\n\nIt comes off each of them."
                % (name, "\n".join(users)))
        if only:
            text += " %s %s on in nothing else, so play.bat stops switching %s." % (
                ce.few(only, 6), "is" if len(only) == 1 else "are",
                "it" if len(only) == 1 else "them")
        if not messagebox.askyesno("Remove %s" % name, text, parent=root):
            return False
    cal.take_spell(name)
    return True


def remove_own_season(root, cal, name):
    """Take a season of the player's own off `cal` and off the mods on in it, once the
    player says so when there are any. A mod on in nothing else comes off the calendar.
    True when it was taken off; nothing is saved here."""
    from tkinter import messagebox
    users = cal.users_of(name)
    spells = cal.spells_only_in(name)
    if users or spells:
        text = "Remove %s?" % name
        if users:
            only = [u for u in users if all(p == name for p in cal.toggle[u]["when"])]
            text += (" These mods are on in it:\n\n%s\n\nIt comes off each of them."
                     % "\n".join(users))
            if only:
                text += " %s %s on in nothing else, so play.bat stops switching %s." % (
                    ce.few(only, 6), "is" if len(only) == 1 else "are",
                    "it" if len(only) == 1 else "them")
        if spells:
            text += ("\n\n%s can start only in it, so %s too." % (
                ce.few(spells, 6), "it goes" if len(spells) == 1 else "they go"))
        if not messagebox.askyesno("Remove %s" % name, text, parent=root):
            return False
    cal.take_own(name)
    return True


def save_preset_dialog(root, cal):
    """Keep parts of the setup `cal` holds as a preset of the player's own."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    problems = refused_lines(cal)
    if problems:
        messagebox.showerror("Save preset", "\n".join(
            ["Fix these before saving a preset:"] + problems), parent=root)
        return
    win, f = dialog(root, "Save preset")
    name, about = tk.StringVar(), tk.StringVar()
    grid = ttk.Frame(f)
    grid.pack(fill="x")
    ttk.Label(grid, text="Name").grid(row=0, column=0, sticky="w")
    name_box = ttk.Entry(grid, textvariable=name, width=32)
    name_box.grid(row=0, column=1, sticky="w", padx=8)
    ttk.Label(grid, text="About it").grid(row=1, column=0, sticky="w", pady=(6, 0))
    ttk.Entry(grid, textvariable=about, width=50).grid(row=1, column=1, sticky="w", padx=8,
                                                       pady=(6, 0))
    full = ce.parts_with_content(cal)
    pick = {p: tk.BooleanVar(value=p in full) for p in ce.PARTS}
    checks = ttk.Frame(f)
    checks.pack(fill="x", pady=(12, 0))
    ttk.Label(checks, text="Keep these parts of your setup in it:").pack(anchor="w")
    for p in ce.PARTS:
        ttk.Checkbutton(checks, text=ce.PART_TEXT[p], variable=pick[p]).pack(anchor="w")
    ttk.Label(f, text="It goes in _tools\\presets, as a file you can share. Where your "
              "weather comes from is never in it.", foreground=GREY).pack(anchor="w",
                                                                         pady=(10, 0))

    def ok():
        n = name.get().strip()
        if not ce.PRESET_NAME.match(n):
            messagebox.showerror("Save preset", "A preset name is up to 40 letters, "
                                 "digits, spaces and - _ . , ' ( ).", parent=win)
            return
        parts = [p for p in ce.PARTS if pick[p].get()]
        if not parts:
            messagebox.showerror("Save preset", "Check at least one part to keep.",
                                 parent=win)
            return
        files = ce.preset_files()
        same = next((x for x in files if x.lower() == n.lower()), None)
        if same:
            old, _ = ce.read_preset(files[same])
            if old and old["shipped"]:
                messagebox.showerror("Save preset", "\"%s\" comes with the tool. Save "
                                     "yours under another name." % same, parent=win)
                return
            if not messagebox.askyesno("Save preset", "Replace your preset \"%s\"?"
                                       % same, parent=win):
                return
            n = same
        path = ce.write_preset(n, about.get().strip(), ce.preset_from(cal, parts))
        win.destroy()
        messagebox.showinfo("Save preset", "Saved %s:\n\n%s" % (n, path), parent=root)

    button_row(f, ("Save", ok), ("Cancel", win.destroy))
    win.bind("<Return>", lambda e: ok())
    present(win, root, name_box)


def show_preview(root, cal):
    """What play.bat would switch at the next launch - today, or in another season - for
    the setup `cal` holds, saved or not."""
    import tempfile
    import tkinter as tk
    from tkinter import ttk
    win, f = dialog(root, "The next launch")
    row = ttk.Frame(f)
    row.pack(fill="x")
    ttk.Label(row, text="Show what play.bat would do").pack(side="left")
    choices = ["today"] + [title(s, cal) for s in season.SEASONS if s in cal.dates]
    keys = [None] + [s for s in season.SEASONS if s in cal.dates]
    which = tk.StringVar(value="today")
    combo = ttk.Combobox(row, textvariable=which, values=choices, state="readonly",
                         width=16)
    combo.pack(side="left", padx=8)
    ttk.Label(row, text="Nothing is changed, and unsaved changes are included.",
              foreground=GREY).pack(side="left", padx=(8, 0))
    box = ttk.Frame(f)
    box.pack(fill="both", expand=True, pady=(10, 0))
    text = tk.Text(box, width=108, height=30, wrap="none", font=("Consolas", 9))
    ys = ttk.Scrollbar(box, orient="vertical", command=text.yview)
    xs = ttk.Scrollbar(box, orient="horizontal", command=text.xview)
    text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
    text.grid(row=0, column=0, sticky="nsew")
    ys.grid(row=0, column=1, sticky="ns")
    xs.grid(row=1, column=0, sticky="ew")
    box.rowconfigure(0, weight=1)
    box.columnconfigure(0, weight=1)

    def run(e=None):
        problems = refused_lines(cal)
        if problems:
            out = "\n".join(["Fix these first:"] + problems)
        else:
            fd, path = tempfile.mkstemp(suffix=".py", prefix="seasons_config_preview_")
            os.close(fd)
            try:
                with open(path, "w", encoding="utf-8") as h:
                    h.write(cal.render()[0])
                args = [sys.executable, os.path.join(ce.HERE, "season.py"), "apply",
                        "--dry-run"]
                key = keys[choices.index(which.get())]
                if key:
                    args += ["--season", key]
                r = subprocess.run(args, capture_output=True, text=True, cwd=season.ROOT,
                                   encoding="utf-8", errors="replace",
                                   env=dict(os.environ, SEASONS_CONFIG=path))
                out = r.stdout + r.stderr
            finally:
                os.remove(path)
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("end", out)
        text.configure(state="disabled")

    combo.bind("<<ComboboxSelected>>", run)
    button_row(f, ("Close", win.destroy))
    run()
    present(win, root, combo)


def unreadable(root, cal):
    """The file can't be edited here. Returns what the player chose: "open" it in Notepad,
    start a "new" one, or None to close."""
    import tkinter as tk
    from tkinter import ttk
    chose = {"what": None}
    win, f = dialog(root, "seasons_config.py", transient=False)
    lines = [l for l in cal.error if l.strip() != "^"]
    ttk.Label(f, text="seasons_config.py can't be edited here:", justify="left").pack(anchor="w")
    ttk.Label(f, text="\n".join(lines), justify="left", foreground=RED, wraplength=560,
              font=("Consolas", 9)).pack(anchor="w", pady=(8, 0))
    ttk.Label(f, text=("It is %s. Open it in Notepad and fix it there, then open "
                       "configure.bat again. Or start a new, empty one: your seasonal mods, "
                       "events and dates start over, and the old file is kept next to it with "
                       "the date in its name." % cal.path),
              justify="left", wraplength=560).pack(anchor="w", pady=(10, 0))

    def choose(what):
        chose["what"] = what
        win.destroy()

    first, _, _ = button_row(f, ("Open it in Notepad", lambda: choose("open")),
                             ("Start a new one", lambda: choose("new")),
                             ("Close", win.destroy))
    win.bind("<Return>", lambda e: choose("open"))
    present(win, root, first)
    win.lift()
    win.focus_force()
    root.wait_window(win)
    return chose["what"]


def window(advanced=False):
    """configure.bat's window: the guided setup, or its summary once there is a setup to
    sum up. `advanced` opens the tabbed editor instead."""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        fail("The window needs tkinter, which this Python does not have. Reinstall Python "
             "from python.org with \"tcl/tk and IDLE\" checked. Until then the commands work, "
             "like:", "  " + season.command("configure.py", "add \"<mod>\" --when winter"))
    season._check_install()
    cal = ce.Calendar()
    root = tk.Tk()
    root.withdraw()
    if cal.error:
        what = unreadable(root, cal)
        if what == "open":
            subprocess.Popen(["notepad.exe", ce.CONFIG])
        if what != "new":
            root.destroy()
            return
        kept = cal.start_over()
        if kept:
            messagebox.showinfo("seasons_config.py", "Started a new, empty one. The old file "
                                "is kept as %s, in %s." % (kept, ce.HERE))
    print("  Reading your mods...")
    inst = ce.Install()
    for n in inst.names:
        inst.files(n)
    root.deiconify()
    if advanced:
        App(root, cal, inst)
    else:
        import guide
        guide.Guide(root, cal, inst)
    if cal.fixes:
        messagebox.showinfo("seasons_config.py", "Saving from here also fixes:\n\n- "
                            + "\n- ".join(cal.fixes), parent=root)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(
        description="Set up Seasons of the Zone. With no command, opens the window.",
        epilog=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--advanced", action="store_true",
                    help="open the tabbed editor rather than the guided setup")
    sub = ap.add_subparsers(dest="cmd", metavar="command")
    sub.add_parser("list", help="show the seasonal mods, events and calendar")
    p = sub.add_parser("add", help="make a mod seasonal, or change when it is on")
    p.add_argument("mod", help="the mod as MO2's mod list names it, in quotes if it has spaces")
    p.add_argument("--when", nargs="+", required=True, metavar="WHEN",
                   help="the seasons, events or weather it is on in, like winter "
                        "\"deep winter\" christmas")
    p.add_argument("--above", metavar="MOD",
                   help="the mod it wins over; worked out from shared files if left out")
    p = sub.add_parser("remove", help="stop switching a mod by season")
    p.add_argument("mod", help="the seasonal mod to stop switching")
    p = sub.add_parser("event", help="add, change or remove an event")
    p.add_argument("name", help="lowercase letters, digits and underscores, like new_year")
    p.add_argument("start", nargs="?", help="the first day, month-day, like 12-24")
    p.add_argument("end", nargs="?", help="the last day, month-day; left out for one day")
    p.add_argument("--weekdays", nargs="+", metavar="DAY",
                   help="days of the week: sat sun, weekends, workdays")
    p.add_argument("--days", nargs="+", metavar="N", help="days of the month: 1 15 last")
    p.add_argument("--weeks", nargs="+", metavar="WHICH",
                   help="with --weekdays, which of them in the month: first last")
    p.add_argument("--months", nargs="+", metavar="MONTH", help="only in these months")
    p.add_argument("--between", nargs=2, metavar=("FROM", "TO"),
                   help="only between these dates, month-day")
    p.add_argument("--remove", action="store_true", help="delete the event")
    p = sub.add_parser("season", help="show, add, change or remove a season of your own")
    p.add_argument("name", nargs="?", help="its name, in quotes if it has spaces")
    p.add_argument("start", nargs="?", help="the first day, month-day, like 08-01")
    p.add_argument("end", nargs="?", help="the last day, month-day, at least a week on")
    p.add_argument("--rename", metavar="NEW", help="give it another name")
    p.add_argument("--remove", action="store_true",
                   help="delete it, and take it off the mods on in it")
    p = sub.add_parser("spell", help="show, add, change or remove a spell: a short stretch "
                       "that starts by chance")
    p.add_argument("name", nargs="?", help="its name, in quotes if it has spaces")
    p.add_argument("--in", dest="start", nargs="+", metavar="SEASON",
                   help="the seasons it can start in, yours included")
    p.add_argument("--chance", type=float, metavar="PERCENT",
                   help="the percent chance it starts on each of those days, like 3")
    p.add_argument("--days", type=int, nargs="+", metavar="N",
                   help="how long it runs: a number, or the fewest and the most, 1 to %d"
                        % season.SPELL_MOST_DAYS)
    p.add_argument("--as", dest="brings", metavar="SEASON",
                   help="the season it brings, or none to leave the season as it is")
    p.add_argument("--rename", metavar="NEW", help="give it another name")
    p.add_argument("--remove", action="store_true",
                   help="delete it, and take it off the mods on during it")
    p = sub.add_parser("calendar", help="show or change when each season starts")
    p.add_argument("starts", nargs="*", metavar="SEASON=MM-DD",
                   help="move a season's start, turning it on if it was off")
    p.add_argument("--only", action="store_true",
                   help="the seasons named are the only ones on")
    p.add_argument("--off", nargs="+", metavar="SEASON", help="turn seasons off")
    p.add_argument("--on", nargs="+", metavar="SEASON",
                   help="turn seasons back on, at Polesia's date")
    p.add_argument("--dates", choices=["polesia", "met"],
                   help="start from Polesia's dates or the meteorological ones (month starts), "
                        "all six seasons on")
    p.add_argument("--preset", dest="dates", choices=["polesia", "met"],
                   help=argparse.SUPPRESS)          # its name before 1.9's presets
    p.add_argument("--reset", action="store_true", help="back to Polesia's dates")
    p = sub.add_parser("name", help="show or change what the seasons are called")
    p.add_argument("season", nargs="?", help="a season, like winter or \"deep winter\"")
    p.add_argument("name", nargs="?", help="the name to show in the game, in quotes")
    p.add_argument("--reset", action="store_true", help="back to its usual name")
    p = sub.add_parser("place", help="show or change where the real weather comes from")
    p.add_argument("text", nargs="?", metavar="PLACE",
                   help="a place to look up on open-meteo.com, like Kyiv or \"New York\"")
    p.add_argument("--pick", type=int, metavar="N",
                   help="which of the places found, when there are several")
    p.add_argument("--at", nargs=2, type=float, metavar=("LAT", "LON"),
                   help="the place's coordinates in degrees, north and east positive")
    p.add_argument("--name", help="with --at, what to call the place")
    p.add_argument("--reset", action="store_true", help="back to Chornobyl")
    p = sub.add_parser("install", help="copy the tools from the mod's folder into the "
                       "GAMMA folder, or update them there; configure.bat does this when "
                       "opened from the mod's folder")
    p.add_argument("--yes", action="store_true",
                   help="in the console, without asking")
    p = sub.add_parser("preset", help="save your setup under a name, or load one")
    p.add_argument("action", nargs="?", choices=["list", "save", "load", "show"],
                   help="list (the default), save, load or show")
    p.add_argument("name", nargs="?", help="the preset's name, in quotes if it has spaces")
    p.add_argument("--about", default="", help="a line saying what the preset is")
    p.add_argument("--parts", nargs="+", choices=list(ce.PARTS),
                   help="which parts to save or load; all of them by default")
    p.add_argument("--force", action="store_true",
                   help="save over a preset of that name, or load over your own setup")
    a = ap.parse_args()
    {"list": cmd_list, "add": cmd_add, "remove": cmd_remove, "event": cmd_event,
     "season": cmd_season, "spell": cmd_spell, "calendar": cmd_calendar, "name": cmd_name, "preset": cmd_preset, "place": cmd_place,
     "install": lambda a: __import__("installer").main(a),
     None: lambda a: window(a.advanced)}[a.cmd](a)


if __name__ == "__main__":
    main()
