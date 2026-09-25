#!/usr/bin/env python3
"""Set up Seasons of the Zone without editing seasons_config.py by hand.

  python _tools/configure.py                   the window (what configure.bat opens)
  python _tools/configure.py list              what is on the calendar
  python _tools/configure.py add "<mod>" --when winter winter_snow [--above "<mod>"]
  python _tools/configure.py remove "<mod>"
  python _tools/configure.py event <name> <MM-DD> [<MM-DD>]
  python _tools/configure.py event <name> --weekdays sat sun
  python _tools/configure.py event <name> --days 1 15 last [--months dec jan]
  python _tools/configure.py event <name> --weekdays mon --weeks first [--between 12-01 02-28]
  python _tools/configure.py event <name> --remove
  python _tools/configure.py calendar          when each season starts
  python _tools/configure.py calendar summer=5-1 winter_snow=11-15 [--only]
  python _tools/configure.py calendar --off late_winter | --on late_winter
  python _tools/configure.py calendar --preset met | --reset
  python _tools/configure.py name              the seasons' names
  python _tools/configure.py name "deep winter" "The Long Cold" | name "deep winter" --reset
  python _tools/configure.py preset            the presets there are
  python _tools/configure.py preset save "<name>" [--about "..."] [--parts calendar mods]
  python _tools/configure.py preset load "<name>" [--parts calendar events mods textures]
  python _tools/configure.py preset show "<name>"

Mod names come from MO2's own list, and `above` - the mod yours has to outrank - is
worked out from the files the mods share. The config is checked with season.py's rules
before it is written, and the previous one is kept as seasons_config.py.bak.
"""
import argparse
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
               + ["Fix it by hand, or open configure.bat to start a new one (the old one "
                  "is kept, dated, beside it)."]))
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


def calendar_moved(cal):
    """Would saving change what the game is told: the dates, the names, or a repair that
    changes which CALENDAR or NAMES is in force?"""
    return (cal.dates_changed() or cal.names_changed()
            or any("CALENDAR" in f or "NAMES" in f for f in cal.fixes))


def save(cal):
    """Save from a command: say what happened, stop on a refusal, and hand a changed
    calendar to the game."""
    moved = calendar_moved(cal)
    saved, lines = cal.save()
    for l in lines:
        print("  " + l)
    if not saved:
        raise SystemExit(1)
    if moved and lines != ["Nothing to save."]:
        ok, out = draw_dial()
        for l in out:
            print("  " + l)


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
    if not cal.toggle:
        print("  Nothing is on the calendar yet.")
    width = max([len(n) for n in cal.toggle] + [10])
    for name, c in cal.toggle.items():
        mark = "" if name in inst.names else "   <-- not in your MO2 list"
        print("  %-*s  %s%s" % (width, name, when_text(c["when"], cal), mark))
        mark = "" if inst.listed(c["above"]) else "   <-- not in your MO2 list"
        print("  %-*s  above %s%s" % (width, "", c["above"] or "(nothing)", mark))
    if cal.events or cal._bad_events:
        print()
        for name, spec in cal.events.items():
            print("  event %-18s %s" % (name, ce.window_text(spec)))
        for name in cal._bad_events:
            print("  event %-18s can't be used - see below" % name)
    for p in cal.problems:
        print("  ! " + p)
    for f in cal.fixes:
        print("  - " + f)


def cmd_add(a):
    cal = loaded()
    inst = ce.Install()
    name, close = inst.match(a.mod)
    if not name:
        fail("No mod named \"%s\" in MO2's list." % a.mod,
             *(["Did you mean one of these?"] + ["  " + c for c in close] if close else
               ["Copy the name exactly as MO2's left pane shows it."]))
    if name in season._own_folders():
        fail("That is Seasons of the Zone itself, which has to stay on.")
    known = cal.known()
    when = []
    for w in a.when:
        p = ce.resolve(w, known)
        if not p:
            fail("\"%s\" is not a season or an event. These are: %s" % (w, ", ".join(known)))
        when.append(p)
    rivals = ce.anchor_for(inst, name, when, cal.toggle)[2]
    if a.above:
        above, close = inst.match(a.above)
        if not above and a.above in inst.separators:
            above = a.above
        if not above:
            fail("No mod named \"%s\" in MO2's list to put it above." % a.above,
                 *(["Did you mean one of these?"] + ["  " + c for c in close] if close else []))
        if above == name:
            fail("A mod can't be placed above itself. Name the mod it has to outrank: "
                 "season.py whowins <a file it ships> --for \"%s\" finds it." % name)
        why = "as you asked"
    elif name in cal.toggle and inst.listed(cal.toggle[name]["above"]):
        above, why = cal.toggle[name]["above"], "as it was"
    else:
        above, why, _ = ce.anchor_for(inst, name, when, cal.toggle)
        if not above:
            fail("Nothing to place it by: %s." % why)
    had = name in cal.toggle
    cal.put(name, when, above)
    print("  %-7s %s" % ("changed" if had else "added", name))
    print("  %-7s %s" % ("when", when_text(cal.toggle[name]["when"], cal)))
    print("  %-7s %s  (%s)" % ("above", above, why))
    save(cal)
    for other, n, both in rivals:
        if other != above:
            print("  note    %s is also on in %s and ships %d of the same files. To make"
                  % (other, when_text(both, cal), n))
            print("          sure this one wins them: --above \"%s\"" % other)
    off = [p for p in when if p in season.SEASONS and p not in cal.dates]
    if off:
        print("  note    %s %s off in your calendar, so the mod is not switched on then"
              % (season.seasons_text(off), "is" if len(off) == 1 else "are"))
    print("  Launch with play.bat to stage it.")


def cmd_remove(a):
    cal = loaded()
    names = list(cal.toggle)
    hit = next((n for n in names if n == a.mod), None) or next(
        (n for n in names if n.lower() == a.mod.lower()), None)
    if not hit:
        import difflib
        close = difflib.get_close_matches(a.mod, names, n=5, cutoff=0.5)
        fail("\"%s\" is not on the calendar." % a.mod,
             *(["Did you mean one of these?"] + ["  " + c for c in close] if close else []))
    cal.take(hit)
    print("  removed %s" % hit)
    save(cal)


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
            fail("There is no event called \"%s\"." % a.name.strip())
        users = cal.users_of(have)
        if users:
            fail("These mods are still scoped to %s; take it off them first:" % have,
                 *["  " + u for u in users])
        cal.events.pop(have, None)
        cal._bad_events.pop(have, None)
        print("  removed event %s" % have)
        save(cal)
        return
    if not EVENT_NAME.match(name):
        fail("An event name is lower-case letters, digits and underscores, like "
             "christmas or new_year.")
    if (name in season.SEASONS or name in cal.periods or name in season.WEATHER_NAMES
            or ce.resolve(name, season.SEASONS)):
        fail("\"%s\" is already the name of a season, or another name for one, a period or "
             "a kind of weather." % name)
    rule = event_rule(a)
    if rule:
        if a.start:
            fail("With a rule, give dates as --between MM-DD MM-DD.")
        spec = rule
    else:
        if not a.start:
            fail("Give the day it starts, like 12-24, and the day it ends if it is longer "
                 "than one - or a rule, like --weekdays sat sun.")
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
    print("  saved event %s  %s" % (key, ce.window_text(spec)))
    save(cal)
    if isinstance(spec, tuple) and spec[0] > spec[1]:
        print("  note    it runs over the year end")
    if (2, 29) in (spec if isinstance(spec, tuple) else ()):
        print("  note    February 29 comes only in leap years")


def cmd_calendar(a):
    cal = loaded()
    # argparse files "summer=5-1" after --off or --on under that option
    for opt in (a.off, a.on):
        for x in list(opt or []):
            if "=" in x:
                opt.remove(x)
                a.starts.append(x)
    if a.reset and a.preset:
        fail("--reset and --preset each set the whole calendar; give one.")
    if a.preset and a.only:
        fail("--preset turns every season on and --only turns some off; give one.")

    def name(n):
        s = ce.resolve(n, season.SEASONS)
        if not s:
            fail("\"%s\" is not a season. These are: %s" % (n, ", ".join(season.SEASONS)))
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

    if not (a.reset or a.preset or moves or on or off):
        print("  %s" % ("Your own calendar:" if cal.custom()
                        else "Polesia's calendar, the default:"))
        for l in calendar_lines(cal.dates, cal):
            print("  " + l)
        for p in cal.calendar_bad + cal.names_bad:
            print("  ! " + p)
        return
    dates = dict(cal.dates)
    if a.reset:
        dates = ce.polesia()
    elif a.preset:
        dates = ce.meteorological() if a.preset == "met" else ce.polesia()
    if a.only:
        if not moves:
            fail("--only needs the seasons to keep, like summer=5-20 winter_snow=12-1.")
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
    for l in calendar_lines(dates, cal):
        print("  " + l)
    save(cal)
    for n in stranded(cal, dates):
        print("  note    %s is on only in seasons that are off, so it is never switched on"
              % n)


def cmd_name(a):
    cal = loaded()
    if not a.season:
        for s in season.SEASONS:
            print("  %-12s %s" % (season.default_label(s),
                                  cal.names.get(s, "(its usual name)")))
        for p in cal.names_bad:
            print("  ! " + p)
        return
    s = ce.resolve(a.season, season.SEASONS)
    if not s:
        fail("\"%s\" is not a season. These are: %s" % (a.season, ", ".join(season.SEASONS)))
    names = dict(cal.names)
    if a.reset:
        names.pop(s, None)
    elif not a.name or not a.name.strip():
        fail("Give the name in quotes, like: configure.py name \"deep winter\" \"The Long Cold\"")
    else:
        names[s] = a.name.strip()
    problems = season.names_problems(names)
    if problems:
        fail(*(["Not saved:"] + problems))
    cal.set_names(names)
    print("  %s is called %s" % (season.default_label(s),
                                 "\"%s\"" % cal.names[s] if s in cal.names
                                 else "by its usual name"))
    save(cal)


def cmd_preset(a):
    files = ce.preset_files()
    if not a.action or a.action == "list":
        if not files:
            print("  No presets yet. Save one with: configure.py preset save \"<name>\"")
            return
        for name, path in files.items():
            p, problems = ce.read_preset(path)
            parts = ce.preset_parts(p) if p else []
            print("  %-26s %s%s" % (name, ", ".join(parts) or "-",
                                    "   (can't be used - see preset show)" if problems else ""))
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
            fail(*(["Your setup has something season.py refuses, so it is not saved as a "
                    "preset:"] + cal.problems))
        parts = a.parts or ce.parts_with_content(cal)
        path = ce.write_preset(name, a.about, ce.preset_from(cal, parts))
        print("  saved preset %s: %s" % (name, ", ".join(ce.PART_TEXT[p] for p in parts)))
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
        print("  holds: %s" % ", ".join(ce.PART_TEXT[x] for x in have))
        if "calendar" in have:
            for l in calendar_lines(p["calendar"] or ce.polesia()):
                print("    " + l)
            for s, n in (p.get("names") or {}).items():
                print("    %s is called \"%s\"" % (season.default_label(s), n))
        if "events" in have:
            for n, spec in p.get("events", {}).items():
                print("    event %-18s %s" % (n, ce.window_text(spec)))
        if "mods" in have:
            for n, c in p["mods"].items():
                print("    %s  (%s)" % (n, ", ".join(c["when"])))
        if "textures" in have:
            for n in p.get("layout") or {}:
                print("    texture set %s" % n)
            print("    ambient sound: %s" % (p.get("sound_src") or "off"))
        return
    parts = [x for x in (a.parts or have) if x in have]
    if not parts:
        fail("\"%s\" holds none of those parts; it holds %s." % (name, ", ".join(have)))
    cal = loaded()
    for l in ce.apply_preset(cal, ce.Install(), p, parts):
        print("  " + l)
    save(cal)


# --- the window -----------------------------------------------------------------------

WEATHER_TEXT = {"freezing": "a day that freezes in the real Zone",
                "thaw": "freezing overnight, above zero by afternoon",
                "heat": "a day that reaches 28 C"}


class App(object):
    """The setup in a window. Mods: MO2's mods on the left, the chosen one's seasons,
    events and anchor on the right. Seasons: when each starts, which are on, and what each
    is called. Changes are held until Save."""

    def __init__(self, root, cal, inst):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root, self.cal, self.inst = root, cal, inst
        self.current = None
        self.windows = ce.season_windows(cal.dates)
        self.bad_dates, self._filling = [], False
        root.title("Seasons of the Zone - the calendar")
        root.geometry("1180x700")
        root.minsize(900, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        mods = ttk.Frame(self.tabs)
        self.tabs.add(mods, text="Mods")
        seasons = ttk.Frame(self.tabs)
        self.tabs.add(seasons, text="Seasons")

        top = ttk.Frame(mods, padding=(0, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Find a mod:").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.fill())
        ttk.Entry(top, textvariable=self.search, width=40).pack(side="left", padx=6)
        self.only_ours = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Only mods on the calendar", variable=self.only_ours,
                        command=self.fill).pack(side="left", padx=10)

        panes = ttk.PanedWindow(mods, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        self.tree = ttk.Treeview(left, columns=("when",), show="tree headings",
                                 selectmode="browse")
        self.tree.heading("#0", text="Mod, in MO2's order")
        self.tree.heading("when", text="On the calendar")
        self.tree.column("#0", width=420)
        self.tree.column("when", width=190)
        self.tree.tag_configure("off", foreground="#888888")
        self.tree.tag_configure("ours", foreground="#1f5f99")
        self.tree.tag_configure("gone", foreground="#b03020")
        bar = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.pick())
        panes.add(left, weight=3)

        self.side = ttk.Frame(panes, padding=(12, 0))
        panes.add(self.side, weight=2)

        bottom = ttk.Frame(root, padding=(10, 8))
        bottom.pack(fill="x")
        self.status = ttk.Label(bottom, text="")
        self.status.pack(side="left")
        ttk.Button(bottom, text="Close", command=self.close).pack(side="right")
        ttk.Button(bottom, text="Save", command=self.save).pack(side="right", padx=6)
        ttk.Button(bottom, text="Preview the next launch",
                   command=self.preview).pack(side="right")
        ttk.Button(bottom, text="Save preset...",
                   command=self.save_preset).pack(side="right", padx=(0, 16))
        ttk.Button(bottom, text="Load preset...",
                   command=self.load_preset).pack(side="right", padx=6)

        self.seasons_tab(seasons)
        self.fill()
        self.show()
        self.update_status()

    # the list

    def fill(self):
        q = self.search.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for name, on in self.inst.order:
            ours = name in self.cal.toggle
            if self.only_ours.get() and not ours:
                continue
            if q and q not in name.lower():
                continue
            when = when_text(self.cal.toggle[name]["when"], self.cal) if ours else ""
            tag = "ours" if ours else ("" if on else "off")
            self.tree.insert("", "end", iid=name, text=name, values=(when,), tags=(tag,))
        # on the calendar but not in MO2's list - renamed by an update, say - so they can
        # still be picked and taken off
        for name, c in self.cal.toggle.items():
            if name not in self.inst.names and not self.tree.exists(name) and (
                    not q or q in name.lower()):
                self.tree.insert("", "end", iid=name, text=name + "   (not in MO2's list)",
                                 values=(when_text(c["when"], self.cal),), tags=("gone",))
        if self.current and self.tree.exists(self.current):
            self.tree.selection_set(self.current)
            self.tree.see(self.current)

    def pick(self):
        sel = self.tree.selection()
        if sel and sel[0] != self.current:
            self.current = sel[0]
            self.show()

    def select(self, name):
        """Show `name` on the right, as clicking it in the list does."""
        self.current = name
        if self.tree.exists(name):
            self.tree.selection_set(name)
            self.tree.see(name)
        self.show()

    # the chosen mod

    def show(self):
        tk, ttk = self.tk, self.ttk
        for w in self.side.winfo_children():
            w.destroy()
        name = self.current
        if not name:
            ttk.Label(self.side, wraplength=420, justify="left", text=(
                "Pick a mod on the left, then tick the seasons it belongs to. It is "
                "switched on in those seasons and off the rest of the year, and placed "
                "above the mods it has to beat.")).pack(anchor="w", pady=12)
            return
        entry = self.cal.toggle.get(name)
        when = entry["when"] if entry else []
        ttk.Label(self.side, text=name, font=("TkDefaultFont", 11, "bold"),
                  wraplength=440).pack(anchor="w", pady=(4, 0))
        if name in self.inst.names:
            n = len(self.inst.files(name))
            ttk.Label(self.side, text="%s in MO2, ships %d file%s" % (
                "Enabled" if name in self.inst.enabled else "Disabled", n,
                "" if n == 1 else "s")).pack(anchor="w", pady=(0, 8))
        else:
            ttk.Label(self.side, foreground="#b03020", wraplength=440, text=(
                "Not in MO2's list, so play.bat skips it. Take it off the calendar, or put "
                "the mod back.")).pack(anchor="w", pady=(0, 8))

        self.vars = {}
        box = ttk.LabelFrame(self.side, text="On in these seasons", padding=8)
        box.pack(fill="x")
        for s in season.SEASONS:
            v = tk.BooleanVar(value=s in when)
            self.vars[s] = v
            row = ttk.Frame(box)
            row.pack(fill="x")
            ttk.Checkbutton(row, text=title(s, self.cal), variable=v, width=16,
                            command=self.ticked).pack(side="left")
            ttk.Label(row, text=self.windows.get(s) or "off - see the Seasons tab",
                      foreground="#666666").pack(side="left")

        box = ttk.LabelFrame(self.side, text="And on these days", padding=8)
        box.pack(fill="x", pady=(8, 0))
        extra = sorted(self.cal.periods) + sorted(self.cal.events)
        for p in extra + list(season.WEATHER_NAMES):
            v = tk.BooleanVar(value=p in when)
            self.vars[p] = v
            row = ttk.Frame(box)
            row.pack(fill="x")
            ttk.Checkbutton(row, text=p, variable=v, width=14,
                            command=self.ticked).pack(side="left")
            spec = self.cal.events.get(p)
            ttk.Label(row, text=(ce.window_text(spec) if spec else WEATHER_TEXT[p]
                                 if p in WEATHER_TEXT else "your own period"),
                      foreground="#666666").pack(side="left")
            if spec:
                ttk.Button(row, text="Delete", width=7,
                           command=lambda e=p: self.delete_event(e)).pack(side="right")
        if not extra:
            ttk.Label(box, text="No events yet.", foreground="#666666").pack(anchor="w")
        ttk.Button(box, text="New event...", command=self.new_event).pack(anchor="w", pady=(6, 0))
        unknown = [p for p in when if p not in self.cal.known()]
        if unknown:
            ttk.Label(self.side, foreground="#b03020", wraplength=440, text=(
                "The config also names %s, which is no season or event. Changing the ticks "
                "above drops it." % ", ".join(unknown))).pack(anchor="w", pady=(6, 0))

        if entry:
            self.anchor_box(name, entry)
            ttk.Button(self.side, text="Take it off the calendar",
                       command=lambda: self.remove(name)).pack(anchor="w", pady=(10, 0))

    def anchor_box(self, name, entry):
        ttk = self.ttk
        box = ttk.LabelFrame(self.side, text="Placed above", padding=8)
        box.pack(fill="x", pady=(8, 0))
        auto, why, rivals = ce.anchor_for(self.inst, name, entry["when"], self.cal.toggle)
        choices = [(auto, "automatic: %s" % auto)] if auto else []
        for other, n in ce.overlaps(self.inst, name):
            if other != auto:
                choices.append((other, "%s  (%d shared file%s)" % (other, n, "" if n == 1 else "s")))
        if entry["above"] and entry["above"] not in [c[0] for c in choices]:
            choices.append((entry["above"], entry["above"]))
        self.choices = choices
        combo = ttk.Combobox(box, state="readonly", width=58,
                             values=[c[1] for c in choices])
        cur = [i for i, c in enumerate(choices) if c[0] == entry["above"]]
        if cur:
            combo.current(cur[0])
        combo.bind("<<ComboboxSelected>>",
                   lambda e: self.set_anchor(name, choices[combo.current()][0]))
        combo.pack(anchor="w")
        if not self.inst.listed(entry["above"]):
            ttk.Label(box, foreground="#b03020", wraplength=440, text=(
                "\"%s\" is not in your MO2 list, so play.bat would skip this mod. Pick one "
                "above." % entry["above"])).pack(anchor="w", pady=(4, 0))
        elif entry["above"] == auto:
            ttk.Label(box, text="It %s." % why if why.startswith("ships") else why.capitalize() + ".",
                      foreground="#666666", wraplength=440).pack(anchor="w", pady=(4, 0))
        for other, n, both in rivals:
            if other == entry["above"]:
                continue
            ttk.Label(box, wraplength=440, text=(
                "%s is also on in %s and ships %d of the same files." % (
                    other, when_text(both, self.cal), n))).pack(anchor="w", pady=(6, 0))
            ttk.Button(box, text="Make this one win them",
                       command=lambda o=other: self.set_anchor(name, o)).pack(anchor="w")

    # changes

    def ticked(self):
        name = self.current
        when = [p for p, v in self.vars.items() if v.get()]
        self.set_when(name, when)

    def set_when(self, name, when):
        """Put `name` on the calendar in `when`, or take it off when `when` is empty."""
        if not when:
            self.cal.take(name)
        elif name in self.cal.toggle:
            self.cal.put(name, when, self.cal.toggle[name]["above"])
        else:
            above = ce.anchor_for(self.inst, name, when, self.cal.toggle)[0] or ""
            self.cal.put(name, when, above)
        self.fill()
        self.show()
        self.refresh_seasons()

    def set_anchor(self, name, above):
        self.cal.put(name, self.cal.toggle[name]["when"], above)
        self.show()
        self.update_status()

    def remove(self, name):
        self.cal.take(name)
        self.fill()
        self.show()
        self.refresh_seasons()

    def new_event(self):
        """A window of dates, or a rule: days of the week, of the month, which week, which
        months, between which dates. Every part of a rule has to hold at once."""
        tk, ttk = self.tk, self.ttk
        from tkinter import messagebox
        win = tk.Toplevel(self.root)
        win.title("New event")
        win.transient(self.root)
        f = ttk.Frame(win, padding=12)
        f.pack(fill="both")
        name = tk.StringVar()
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Name", width=8).pack(side="left")
        ttk.Entry(row, textvariable=name, width=24).pack(side="left")
        ttk.Label(row, text="lower-case, like christmas or weekend",
                  foreground="#666666").pack(side="left", padx=8)

        kind = tk.StringVar(value="dates")
        box = ttk.LabelFrame(f, text="When", padding=8)
        box.pack(fill="x", pady=(10, 0))
        ttk.Radiobutton(box, text="On dates, every year", variable=kind,
                        value="dates").grid(row=0, column=0, columnspan=6, sticky="w")
        start, end = tk.StringVar(), tk.StringVar()
        ttk.Label(box, text="first day").grid(row=1, column=0, sticky="w", padx=(20, 4))
        ttk.Entry(box, textvariable=start, width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(box, text="last day").grid(row=1, column=2, sticky="w", padx=(12, 4))
        ttk.Entry(box, textvariable=end, width=8).grid(row=1, column=3, sticky="w")
        ttk.Label(box, text="month-day, like 12-24; no last day for a single day",
                  foreground="#666666").grid(row=2, column=0, columnspan=8, sticky="w",
                                             padx=(20, 0))
        ttk.Radiobutton(box, text="On a rule - every part given has to hold", variable=kind,
                        value="rule").grid(row=3, column=0, columnspan=8, sticky="w",
                                           pady=(12, 0))
        rf = ttk.Frame(box)
        rf.grid(row=4, column=0, columnspan=8, sticky="w", padx=(20, 0))
        rule = lambda *a: kind.set("rule")                      # noqa: E731
        wd = {d: tk.BooleanVar() for d in season.WEEKDAYS}
        ttk.Label(rf, text="days of the week").grid(row=0, column=0, sticky="w")
        for i, d in enumerate(season.WEEKDAYS):
            ttk.Checkbutton(rf, text=d.capitalize(), variable=wd[d],
                            command=rule).grid(row=0, column=1 + i, sticky="w")
        which = tk.StringVar(value="every")
        ttk.Label(rf, text="which of them").grid(row=1, column=0, sticky="w")
        ttk.Combobox(rf, textvariable=which, state="readonly", width=9, values=(
            "every", "first", "second", "third", "fourth", "last")).grid(
            row=1, column=1, columnspan=3, sticky="w")
        which.trace_add("write", rule)
        mdays = tk.StringVar()
        mdays.trace_add("write", rule)
        ttk.Label(rf, text="days of the month").grid(row=2, column=0, sticky="w")
        ttk.Entry(rf, textvariable=mdays, width=14).grid(row=2, column=1, columnspan=3,
                                                         sticky="w")
        ttk.Label(rf, text="like 1, 15, last", foreground="#666666").grid(
            row=2, column=4, columnspan=4, sticky="w")
        months = {m: tk.BooleanVar() for m in range(1, 13)}
        ttk.Label(rf, text="only in").grid(row=3, column=0, sticky="nw")
        mf = ttk.Frame(rf)
        mf.grid(row=3, column=1, columnspan=7, sticky="w")
        for i in range(12):
            ttk.Checkbutton(mf, text=ce.MONTHS[i], variable=months[i + 1],
                            command=rule).grid(row=i // 6, column=i % 6, sticky="w")
        b1, b2 = tk.StringVar(), tk.StringVar()
        b1.trace_add("write", rule)
        b2.trace_add("write", rule)
        ttk.Label(rf, text="only between").grid(row=4, column=0, sticky="w")
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
            if which.get() != "every":
                if not days:
                    return None, "Tick the days of the week that \"which of them\" counts."
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
            n = name.get().strip().lower()
            if (not EVENT_NAME.match(n) or n in self.cal.known()
                    or ce.resolve(n, season.SEASONS)):
                messagebox.showerror("New event", "Use a new name of lower-case letters, "
                                     "digits and underscores - not a season's name, or "
                                     "another name for one.", parent=win)
                return
            sp, err = spec()
            problems = [err] if err else season.event_problems(n, sp)
            if problems:
                messagebox.showerror("New event", "\n".join(problems), parent=win)
                return
            self.add_event(n, spec=sp)
            win.destroy()

        row = ttk.Frame(f)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(row, text="Add", command=ok).pack(side="right", padx=6)

    def add_event(self, name, start=None, end=None, spec=None):
        """Add an event, a window from `start` to `end` or a rule `spec`, and tick it for
        the mod on show."""
        self.cal.events[name] = ce.norm_event(spec if spec is not None else (start, end))
        if self.current:
            when = (self.cal.toggle[self.current]["when"]
                    if self.current in self.cal.toggle else [])
            self.set_when(self.current, when + [name])
        self.update_status()

    def delete_event(self, name, ask=True):
        """Delete an event and untick it everywhere. A mod with nothing else ticked comes
        off the calendar, since a mod scoped to nothing would never be switched on."""
        from tkinter import messagebox
        users = self.cal.users_of(name)
        if ask and users and not messagebox.askyesno("Delete event", (
                "%s is ticked for:\n\n%s\n\nDelete it and untick it there? A mod with "
                "nothing else ticked comes off the calendar.") % (name, "\n".join(users)),
                parent=self.root):
            return
        for u in users:
            rest = [p for p in self.cal.toggle[u]["when"] if p != name]
            if rest:
                self.cal.put(u, rest, self.cal.toggle[u]["above"])
            else:
                self.cal.take(u)
        del self.cal.events[name]
        self.fill()
        self.show()
        self.refresh_seasons()

    # the Seasons tab

    def seasons_tab(self, parent):
        tk, ttk = self.tk, self.ttk
        f = ttk.Frame(parent, padding=(4, 12))
        f.pack(fill="both", expand=True)
        ttk.Label(f, wraplength=900, justify="left", text=(
            "When each season starts, and what it is called. A season runs until the next "
            "one that is on, so a season turned off gives its days to the one before it. "
            "The default is Polesia's own year: the days the land around Chernobyl turns, "
            "not the equinoxes.")).pack(anchor="w")
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
            ttk.Label(grid, text=text, foreground="#666666").grid(row=0, column=col,
                                                                  sticky="w", padx=(0, 4))
        self.srows = {}
        for i, s in enumerate(season.SEASONS, start=1):
            m, d = self.cal.dates.get(s, ce.polesia()[s])
            on = tk.BooleanVar(value=s in self.cal.dates)
            mon, day = tk.StringVar(value=ce.MONTHS[m - 1]), tk.StringVar(value=str(d))
            called = tk.StringVar(value=self.cal.names.get(s) or title(s))
            ttk.Checkbutton(grid, text=title(s), variable=on, width=14,
                            command=self.dates_edited).grid(row=i, column=0, sticky="w",
                                                            pady=3)
            cb = ttk.Combobox(grid, textvariable=mon, values=ce.MONTHS, state="readonly",
                              width=5)
            cb.grid(row=i, column=1, sticky="w")
            cb.bind("<<ComboboxSelected>>", lambda e: self.dates_edited())
            sp = ttk.Spinbox(grid, from_=1, to=31, textvariable=day, width=4,
                             command=self.dates_edited)
            sp.grid(row=i, column=2, sticky="w", padx=(4, 0))
            sp.bind("<KeyRelease>", lambda e: self.dates_edited())
            runs = ttk.Label(grid, text="", width=22)
            runs.grid(row=i, column=3, sticky="w", padx=(14, 0))
            days = ttk.Label(grid, text="", width=9, foreground="#666666")
            days.grid(row=i, column=4, sticky="w")
            name = ttk.Entry(grid, textvariable=called, width=24)
            name.grid(row=i, column=5, sticky="w")
            name.bind("<KeyRelease>", lambda e: self.names_edited())
            self.srows[s] = (on, mon, day, cb, sp, runs, days, called, name)
        self.cal_msg = ttk.Label(f, text="", foreground="#b03020", wraplength=900,
                                 justify="left")
        self.cal_msg.pack(anchor="w", pady=(12, 0))
        self.cal_note = ttk.Label(f, text="", foreground="#666666", wraplength=900,
                                  justify="left")
        self.cal_note.pack(anchor="w", pady=(6, 0))
        self.dates_edited(user=False)

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
        """The Seasons tab showing the setup as it now is, after a preset."""
        self._filling = True
        for s, row in self.srows.items():
            on, mon, day, called = row[0], row[1], row[2], row[7]
            on.set(s in self.cal.dates)
            if s in self.cal.dates:
                mon.set(ce.MONTHS[self.cal.dates[s][0] - 1])
                day.set(str(self.cal.dates[s][1]))
            called.set(self.cal.names.get(s) or title(s))
        self._filling = False
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
                    bad.append(title(s, self.cal))
                else:
                    dates[s] = (m, d)
        self.bad_dates = bad
        if not bad and user:
            self.cal.set_dates(dates)
        self.refresh_seasons()

    def names_edited(self):
        if self._filling:
            return
        self.cal.set_names({s: row[7].get() for s, row in self.srows.items()})
        self.fill()
        self.show()
        self.refresh_seasons()

    def refresh_seasons(self):
        dates = self.cal.dates
        problems = (["Give %s a start day." % ", ".join(self.bad_dates)]
                    if self.bad_dates else [])
        if not dates:
            problems.append("Tick at least one season.")
        else:
            problems += self.cal.calendar_bad or season.calendar_problems(dates)
        problems += season.names_problems(self.cal.names)
        wins = ce.season_windows(dates) if dates else {}
        days = season.season_lengths(dates) if dates and not problems else {}
        for s, row in self.srows.items():
            runs, dl = row[5], row[6]
            runs.configure(text=(wins.get(s, "") if not problems else "") if s in dates
                           else "off", foreground="#000000" if s in dates else "#888888")
            dl.configure(text="%d days" % days[s] if s in days else "")
        self.cal_msg.configure(text="\n".join(problems))
        notes = []
        mine = self.cal.custom() or self.cal.names
        if not mine:
            notes.append("This is Polesia's calendar, with the usual names.")
        elif have_pillow():
            notes.append("Saving hands this calendar to the game and draws the year dial in "
                         "MCM and on the PDA for it.")
        else:
            notes.append("Saving hands this calendar to the game. The year dial in MCM and on "
                         "the PDA is drawn for Polesia's; drawing one for yours needs Pillow, "
                         "which Save offers to install. Without it the dial is hidden.")
        lost = stranded(self.cal, dates)
        if lost:
            notes.append("On only in seasons that are off, so never switched on: "
                         + ", ".join(lost))
        self.cal_note.configure(text="\n\n".join(notes))
        if not problems and wins != self.windows:
            self.windows = wins
            self.show()
        self.update_status()

    # saving

    def update_status(self):
        n = len(self.cal.toggle)
        text = "%d mod%s on the calendar" % (n, "" if n == 1 else "s")
        if self.cal.custom():
            on = len(self.cal.dates)
            text += ", your own calendar (%d season%s)" % (on, "" if on == 1 else "s")
        if self.cal.names:
            text += ", %d season%s renamed" % (len(self.cal.names),
                                              "" if len(self.cal.names) == 1 else "s")
        if self.cal.dirty() or self.bad_dates:
            text += "  -  unsaved changes"
        self.status.configure(text=text)

    def save(self, quiet=False):
        from tkinter import messagebox
        if self.bad_dates:
            if not quiet:
                messagebox.showerror("Save", "Give %s a start day first."
                                     % ", ".join(self.bad_dates), parent=self.root)
            return False
        moved = calendar_moved(self.cal)
        saved, lines = self.cal.save()
        if saved and moved and lines != ["Nothing to save."]:
            ok, out = draw_dial()
            lines = lines + [""] + out
        if not quiet:
            (messagebox.showinfo if saved else messagebox.showerror)(
                "Save", "\n".join(lines), parent=self.root)
            if saved and moved and (self.cal.custom() or self.cal.names) and not have_pillow():
                self.offer_pillow()
        self.reload_seasons()
        self.fill()
        self.show()
        self.update_status()
        return saved

    def offer_pillow(self):
        from tkinter import messagebox
        if not messagebox.askyesno("The year dial", (
                "The dial in MCM and on the PDA shows Polesia's dates and names, so it is "
                "hidden while your own are in use. Drawing one for them needs Pillow, a "
                "Python package.\n\nInstall it now? This runs:\n\n"
                "    python -m pip install pillow"), parent=self.root):
            return
        self.root.configure(cursor="watch")
        self.root.update()
        r = subprocess.run([sys.executable, "-m", "pip", "install", "pillow"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.root.configure(cursor="")
        if r.returncode != 0:
            messagebox.showerror("The year dial", "pip could not install Pillow:\n\n"
                                 + "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:]),
                                 parent=self.root)
            return
        ok, out = draw_dial()
        (messagebox.showinfo if ok else messagebox.showerror)(
            "The year dial", "\n".join(["Pillow is installed.", ""] + out), parent=self.root)
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
        win = tk.Toplevel(self.root)
        win.title("Load a preset")
        win.transient(self.root)
        f = ttk.Frame(win, padding=12)
        f.pack(fill="both", expand=True)
        box = tk.Listbox(f, height=12, width=30, exportselection=False)
        box.grid(row=0, column=0, rowspan=4, sticky="ns")
        for n in files:
            box.insert("end", n)
        about = ttk.Label(f, text="", wraplength=380, justify="left")
        about.grid(row=0, column=1, sticky="nw", padx=(12, 0))
        pick = {p: tk.BooleanVar(value=True) for p in ce.PARTS}
        checks = ttk.Frame(f)
        checks.grid(row=1, column=1, sticky="nw", padx=(12, 0), pady=(8, 0))
        ttk.Label(checks, text="Load these parts, in place of yours:").pack(anchor="w")
        buttons = {p: ttk.Checkbutton(checks, text=ce.PART_TEXT[p], variable=pick[p])
                   for p in ce.PARTS}
        for b in buttons.values():
            b.pack(anchor="w")
        note = ttk.Label(f, text="", foreground="#b03020", wraplength=380, justify="left")
        note.grid(row=2, column=1, sticky="nw", padx=(12, 0), pady=(8, 0))
        held = {}

        def show(e=None):
            sel = box.curselection()
            if not sel:
                return
            name = box.get(sel[0])
            p, problems = ce.read_preset(files[name])
            held["name"], held["preset"], held["problems"] = name, p, problems
            about.configure(text=(p["about"] if p and p["about"] else name))
            have = ce.preset_parts(p) if p else []
            for part, b in buttons.items():
                b.configure(state="normal" if part in have else "disabled")
                pick[part].set(part in have)
            note.configure(text="\n".join(["It can't be used:"] + problems) if problems
                           else "")

        box.bind("<<ListboxSelect>>", show)

        def load():
            p = held.get("preset")
            if not p or held.get("problems"):
                return
            parts = [x for x in ce.PARTS if pick[x].get() and x in ce.preset_parts(p)]
            if not parts:
                return
            said = ce.apply_preset(self.cal, self.inst, p, parts)
            win.destroy()
            self.reload_seasons()
            self.fill()
            self.show()
            self.refresh_seasons()
            messagebox.showinfo("Load preset", "\n".join(
                ["Loaded %s - not saved yet." % held["name"], ""] + said
                + ["", "Save writes it. Close without saving leaves your setup as it was."]),
                parent=self.root)

        row = ttk.Frame(f)
        row.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(row, text="Load", command=load).pack(side="right", padx=6)
        box.selection_set(0)
        show()

    def save_preset(self):
        tk, ttk = self.tk, self.ttk
        from tkinter import messagebox
        if self.bad_dates:
            messagebox.showerror("Save preset", "Give %s a start day first."
                                 % ", ".join(self.bad_dates), parent=self.root)
            return
        problems = self.cal.check(self.cal.render()[0])
        if problems:
            messagebox.showerror("Save preset", "\n".join(
                ["This setup has something season.py refuses:"] + problems),
                parent=self.root)
            return
        win = tk.Toplevel(self.root)
        win.title("Save a preset")
        win.transient(self.root)
        f = ttk.Frame(win, padding=12)
        f.pack(fill="both")
        name, about = tk.StringVar(), tk.StringVar()
        ttk.Label(f, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=name, width=32).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(f, text="About it").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(f, textvariable=about, width=48).grid(row=1, column=1, sticky="w", padx=6,
                                                        pady=(6, 0))
        full = ce.parts_with_content(self.cal)
        pick = {p: tk.BooleanVar(value=p in full) for p in ce.PARTS}
        checks = ttk.Frame(f)
        checks.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(checks, text="Keep these parts of your setup in it:").pack(anchor="w")
        for p in ce.PARTS:
            ttk.Checkbutton(checks, text=ce.PART_TEXT[p], variable=pick[p]).pack(anchor="w")

        def ok():
            n = name.get().strip()
            if not ce.PRESET_NAME.match(n):
                messagebox.showerror("Save preset", "A preset name is up to 40 letters, "
                                     "digits, spaces and - _ . , ' ( ).", parent=win)
                return
            parts = [p for p in ce.PARTS if pick[p].get()]
            if not parts:
                return
            files = ce.preset_files()
            same = next((x for x in files if x.lower() == n.lower()), None)
            if same:
                old, _ = ce.read_preset(files[same])
                if old and old["shipped"]:
                    messagebox.showerror("Save preset", "\"%s\" comes with the tool; save "
                                         "yours under another name." % same, parent=win)
                    return
                if not messagebox.askyesno("Save preset", "Replace the preset \"%s\"?"
                                           % same, parent=win):
                    return
                n = same
            path = ce.write_preset(n, about.get().strip(), ce.preset_from(self.cal, parts))
            win.destroy()
            messagebox.showinfo("Save preset", "Saved %s:\n\n%s" % (n, path),
                                parent=self.root)

        row = ttk.Frame(f)
        row.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(row, text="Save", command=ok).pack(side="right", padx=6)

    def preview(self):
        tk = self.tk
        from tkinter import messagebox
        if self.cal.dirty():
            if not messagebox.askyesno("Preview", "Save your changes first? The preview "
                                       "reads the saved file.", parent=self.root):
                return
            if not self.save():
                return
        r = subprocess.run([sys.executable, os.path.join(ce.HERE, "season.py"), "apply",
                            "--dry-run"], capture_output=True, text=True,
                           cwd=season.ROOT, encoding="utf-8", errors="replace")
        win = tk.Toplevel(self.root)
        win.title("The next launch (nothing has been changed)")
        text = tk.Text(win, width=110, height=32, wrap="none", font=("Consolas", 9))
        text.insert("end", r.stdout + r.stderr)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

    def close(self):
        from tkinter import messagebox
        if self.cal.dirty() or self.bad_dates:
            ans = messagebox.askyesnocancel("Close", "Save your changes?", parent=self.root)
            if ans is None:
                return
            if ans and not self.save():
                return
        self.root.destroy()


def window():
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        fail("The window needs tkinter, which this Python does not have. The commands work "
             "without it:", "  python _tools\\configure.py add \"<mod>\" --when winter")
    season._check_install()
    cal = ce.Calendar()
    root = tk.Tk()
    root.withdraw()
    if cal.error:
        if not messagebox.askyesno("seasons_config.py", "\n".join(
                ["seasons_config.py can't be edited here:", ""] + cal.error + [
                    "", "Start a new one? The old file is kept, dated, beside it."])):
            root.destroy()
            return
        kept = cal.start_over()
        if kept:
            messagebox.showinfo("seasons_config.py", "The old file is kept as %s." % kept)
    print("  Reading your mods...")
    inst = ce.Install()
    for n in inst.names:
        inst.files(n)
    root.deiconify()
    App(root, cal, inst)
    if cal.fixes:
        messagebox.showinfo("seasons_config.py", "Saving from here also fixes:\n\n- "
                            + "\n- ".join(cal.fixes), parent=root)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description="Set up Seasons of the Zone.")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="what is on the calendar")
    p = sub.add_parser("add", help="put a mod on the calendar, or change its seasons")
    p.add_argument("mod")
    p.add_argument("--when", nargs="+", required=True, metavar="SEASON")
    p.add_argument("--above", metavar="MOD")
    p = sub.add_parser("remove", help="take a mod off the calendar")
    p.add_argument("mod")
    p = sub.add_parser("event", help="add, change or remove an event")
    p.add_argument("name")
    p.add_argument("start", nargs="?", help="the first day, month-day")
    p.add_argument("end", nargs="?", help="the last day, month-day")
    p.add_argument("--weekdays", nargs="+", metavar="DAY",
                   help="days of the week: sat sun, weekends, workdays")
    p.add_argument("--days", nargs="+", metavar="N", help="days of the month: 1 15 last")
    p.add_argument("--weeks", nargs="+", metavar="WHICH",
                   help="with --weekdays, which of them in the month: first last")
    p.add_argument("--months", nargs="+", metavar="MONTH", help="only in these months")
    p.add_argument("--between", nargs=2, metavar=("FROM", "TO"),
                   help="only between these dates, month-day")
    p.add_argument("--remove", action="store_true")
    p = sub.add_parser("calendar", help="show or change when each season starts")
    p.add_argument("starts", nargs="*", metavar="SEASON=MM-DD",
                   help="move a season's start, turning it on if it was off")
    p.add_argument("--only", action="store_true",
                   help="the seasons named are the only ones on")
    p.add_argument("--off", nargs="+", metavar="SEASON", help="turn seasons off")
    p.add_argument("--on", nargs="+", metavar="SEASON",
                   help="turn seasons back on, at Polesia's date")
    p.add_argument("--preset", choices=["polesia", "met"],
                   help="Polesia's dates or the meteorological ones, all six on")
    p.add_argument("--reset", action="store_true", help="back to Polesia's calendar")
    p = sub.add_parser("name", help="show or change what the seasons are called")
    p.add_argument("season", nargs="?")
    p.add_argument("name", nargs="?")
    p.add_argument("--reset", action="store_true", help="back to its usual name")
    p = sub.add_parser("preset", help="save your setup under a name, or load one")
    p.add_argument("action", nargs="?", choices=["list", "save", "load", "show"])
    p.add_argument("name", nargs="?")
    p.add_argument("--about", default="", help="a line saying what the preset is")
    p.add_argument("--parts", nargs="+", choices=list(ce.PARTS),
                   help="which parts to save or load; all of them by default")
    p.add_argument("--force", action="store_true", help="replace a preset of that name")
    a = ap.parse_args()
    {"list": cmd_list, "add": cmd_add, "remove": cmd_remove, "event": cmd_event,
     "calendar": cmd_calendar, "name": cmd_name, "preset": cmd_preset,
     None: lambda a: window()}[a.cmd](a)


if __name__ == "__main__":
    main()
