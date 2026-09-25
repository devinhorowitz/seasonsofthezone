#!/usr/bin/env python3
"""Put mods on the calendar, and set the calendar, without editing seasons_config.py by hand.

  python _tools/configure.py                   the window (what configure.bat opens)
  python _tools/configure.py list              what is on the calendar
  python _tools/configure.py add "<mod>" --when winter winter_snow [--above "<mod>"]
  python _tools/configure.py remove "<mod>"
  python _tools/configure.py event <name> <MM-DD> [<MM-DD>]
  python _tools/configure.py event <name> --remove
  python _tools/configure.py calendar          when each season starts
  python _tools/configure.py calendar summer=5-1 winter_snow=11-15 [--only]
  python _tools/configure.py calendar --off late_winter | --on late_winter
  python _tools/configure.py calendar --preset met | --reset

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


def label(p):
    return season.season_label(p)


def when_text(when):
    return ", ".join(label(p) for p in when) or "-"


def fail(*lines):
    for l in lines:
        print("  " + l)
    raise SystemExit(1)


def loaded():
    season._check_install()
    cal = ce.Calendar()
    if cal.error:
        fail(*(["seasons_config.py can't be read, so nothing was changed:"]
               + ["  " + l for l in cal.error]
               + ["Fix it by hand, or open configure.bat to start a new one (the old one "
                  "is kept as seasons_config.py.bak)."]))
    return cal


def report(saved, lines):
    for l in lines:
        print("  " + l)
    if not saved:
        raise SystemExit(1)


def have_pillow():
    """Whether Pillow imports, which a broken install does not."""
    try:
        import PIL                                  # noqa: F401
        return True
    except ImportError:
        return False


def draw_dial():
    """season.py dial: hands the saved calendar to the game and draws a dial for it.
    Returns (ok, lines). A process of its own, so it reads the file just saved."""
    r = subprocess.run([sys.executable, os.path.join(ce.HERE, "season.py"), "dial"],
                       capture_output=True, text=True, cwd=season.ROOT, encoding="utf-8",
                       errors="replace")
    return r.returncode == 0, [l.strip() for l in (r.stdout + r.stderr).splitlines()
                               if l.strip()]


def calendar_lines(dates):
    """One line per season that is on, and one for those that are off."""
    wins = ce.season_windows(dates)
    days = season.season_lengths(dates)
    out = ["%-12s %-17s %3d days" % (label(s).capitalize(), wins[s], days[s])
           for s in season.SEASONS if s in dates]
    off = [label(s) for s in season.SEASONS if s not in dates]
    if off:
        out.append("off: " + ", ".join(off))
    return out


# --- commands -------------------------------------------------------------------------

def cmd_list(a):
    cal = loaded()
    inst = ce.Install()
    if not cal.toggle:
        print("  Nothing is on the calendar yet.")
    width = max([len(n) for n in cal.toggle] + [10])
    for name, c in cal.toggle.items():
        print("  %-*s  %s" % (width, name, when_text(c["when"])))
        mark = "" if c["above"] in inst.names else "   <-- not in your MO2 list"
        print("  %-*s  above %s%s" % (width, "", c["above"] or "(nothing)", mark))
    if cal.events:
        print()
        for name, win in cal.events.items():
            print("  event %-18s %s" % (name, ce.window_text(win)))
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
        if not above:
            fail("No mod named \"%s\" in MO2's list to put it above." % a.above,
                 *(["Did you mean one of these?"] + ["  " + c for c in close] if close else []))
        why = "as you asked"
    elif name in cal.toggle and cal.toggle[name]["above"] in inst.names:
        above, why = cal.toggle[name]["above"], "as it was"
    else:
        above, why, _ = ce.anchor_for(inst, name, when, cal.toggle)
        if not above:
            fail("Nothing to place it by: %s." % why)
    had = name in cal.toggle
    cal.put(name, when, above)
    saved, lines = cal.save()
    if saved:
        print("  %-7s %s" % ("changed" if had else "added", name))
        print("  %-7s %s" % ("when", when_text(cal.toggle[name]["when"])))
        print("  %-7s %s  (%s)" % ("above", above, why))
        for other, n, both in rivals:
            if other != above:
                print("  note    %s is also on in %s and ships %d of the same files. To make"
                      % (other, when_text(both), n))
                print("          sure this one wins them: --above \"%s\"" % other)
    report(saved, lines)
    if saved:
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
    saved, lines = cal.save()
    if saved:
        print("  removed %s" % hit)
    report(saved, lines)


def cmd_event(a):
    cal = loaded()
    name = a.name.strip().lower()
    if a.remove:
        if name not in cal.events:
            fail("There is no event called \"%s\"." % name)
        users = cal.users_of(name)
        if users:
            fail("These mods are still scoped to %s; take it off them first:" % name,
                 *["  " + u for u in users])
        del cal.events[name]
    else:
        if not EVENT_NAME.match(name):
            fail("An event name is lower-case letters, digits and underscores, like "
                 "christmas or new_year.")
        if name in season.SEASONS or name in cal.periods:
            fail("\"%s\" is already a season or a period." % name)
        if not a.start:
            fail("Give the day it starts, like 12-24, and the day it ends if it is longer "
                 "than one.")
        start = ce.parse_day(a.start)
        end = ce.parse_day(a.end) if a.end else start
        if not start or not end:
            fail("Dates are month-day, like 12-24.")
        cal.events[name] = (start, end)
    saved, lines = cal.save()
    if saved:
        print("  %s event %s%s" % ("removed" if a.remove else "saved", name,
                                   "" if a.remove else "  " + ce.window_text(cal.events[name])))
    report(saved, lines)


def cmd_calendar(a):
    cal = loaded()
    dates = dict(cal.dates)
    if a.reset:
        dates = ce.polesia()
    elif a.preset:
        dates = ce.meteorological() if a.preset == "met" else ce.polesia()

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
        moves[name(n)] = md
    if a.only:
        if not moves:
            fail("--only needs the seasons to keep, like summer=5-20 winter_snow=12-1.")
        dates = {}
    for n in a.on or []:
        s = name(n)
        dates.setdefault(s, ce.polesia()[s])
    for n in a.off or []:
        dates.pop(name(n), None)
    dates.update(moves)

    if not (a.reset or a.preset or moves or a.on or a.off):
        print("  %s" % ("Your own calendar:" if cal.custom()
                        else "Polesia's calendar, the default:"))
        for l in calendar_lines(cal.dates):
            print("  " + l)
        return
    problems = season.calendar_problems(dates)
    if problems:
        fail(*(["Not saved:"] + problems))
    changed = dates != cal.dates or cal.dates_changed()
    cal.dates = dates
    saved, lines = cal.save()
    if saved:
        for l in calendar_lines(dates):
            print("  " + l)
    report(saved, lines)
    if saved and changed:
        ok, out = draw_dial()
        for l in out:
            print("  " + l)


# --- the window -----------------------------------------------------------------------

class App(object):
    """The calendar in a window. Mods: MO2's mods on the left, the chosen one's seasons,
    events and anchor on the right. Seasons: when each starts, and which are on. Changes
    are held until Save."""

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
            when = when_text(self.cal.toggle[name]["when"]) if ours else ""
            tag = "ours" if ours else ("" if on else "off")
            self.tree.insert("", "end", iid=name, text=name, values=(when,), tags=(tag,))
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
        n = len(self.inst.files(name))
        ttk.Label(self.side, text="%s in MO2, ships %d file%s" % (
            "Enabled" if name in self.inst.enabled else "Disabled", n,
            "" if n == 1 else "s")).pack(anchor="w", pady=(0, 8))

        self.vars = {}
        box = ttk.LabelFrame(self.side, text="On in these seasons", padding=8)
        box.pack(fill="x")
        for s in season.SEASONS:
            v = tk.BooleanVar(value=s in when)
            self.vars[s] = v
            row = ttk.Frame(box)
            row.pack(fill="x")
            ttk.Checkbutton(row, text=label(s).capitalize(), variable=v, width=14,
                            command=self.ticked).pack(side="left")
            ttk.Label(row, text=self.windows.get(s) or "off - see the Seasons tab",
                      foreground="#666666").pack(side="left")

        box = ttk.LabelFrame(self.side, text="And on these days", padding=8)
        box.pack(fill="x", pady=(8, 0))
        extra = sorted(self.cal.periods) + sorted(self.cal.events)
        for p in extra:
            v = tk.BooleanVar(value=p in when)
            self.vars[p] = v
            row = ttk.Frame(box)
            row.pack(fill="x")
            ttk.Checkbutton(row, text=p, variable=v, width=14,
                            command=self.ticked).pack(side="left")
            win = self.cal.events.get(p)
            ttk.Label(row, text=ce.window_text(win) if win else "your own period",
                      foreground="#666666").pack(side="left")
            if win:
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
        if entry["above"] not in self.inst.names:
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
                    other, when_text(both), n))).pack(anchor="w", pady=(6, 0))
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
        self.update_status()

    def set_anchor(self, name, above):
        self.cal.put(name, self.cal.toggle[name]["when"], above)
        self.show()
        self.update_status()

    def remove(self, name):
        self.cal.take(name)
        self.fill()
        self.show()
        self.update_status()

    def new_event(self):
        tk, ttk = self.tk, self.ttk
        from tkinter import messagebox
        win = tk.Toplevel(self.root)
        win.title("New event")
        win.transient(self.root)
        f = ttk.Frame(win, padding=12)
        f.pack()
        vals = {}
        for i, (key, text, hint) in enumerate((
                ("name", "Name", "lower-case, like christmas"),
                ("start", "First day", "month-day, like 12-24"),
                ("end", "Last day", "leave empty for one day"))):
            ttk.Label(f, text=text).grid(row=i, column=0, sticky="w", pady=3)
            vals[key] = tk.StringVar()
            ttk.Entry(f, textvariable=vals[key], width=22).grid(row=i, column=1, padx=6)
            ttk.Label(f, text=hint, foreground="#666666").grid(row=i, column=2, sticky="w")

        def ok():
            name = vals["name"].get().strip().lower()
            start = ce.parse_day(vals["start"].get())
            end = ce.parse_day(vals["end"].get()) if vals["end"].get().strip() else start
            if not EVENT_NAME.match(name) or name in self.cal.known():
                messagebox.showerror("New event", "Use a new name of lower-case letters, "
                                     "digits and underscores.", parent=win)
                return
            if not start or not end:
                messagebox.showerror("New event", "Dates are month-day, like 12-24.",
                                     parent=win)
                return
            self.add_event(name, start, end)
            win.destroy()

        row = ttk.Frame(f)
        row.grid(row=3, column=0, columnspan=3, pady=(10, 0), sticky="e")
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(row, text="Add", command=ok).pack(side="right", padx=6)

    def add_event(self, name, start, end):
        """Add an event, and tick it for the mod on show."""
        self.cal.events[name] = (start, end)
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
        self.update_status()

    # the Seasons tab

    def seasons_tab(self, parent):
        tk, ttk = self.tk, self.ttk
        f = ttk.Frame(parent, padding=(4, 12))
        f.pack(fill="both", expand=True)
        ttk.Label(f, wraplength=860, justify="left", text=(
            "When each season starts. A season runs until the next one that is on, so a "
            "season turned off gives its days to the one before it. The default is Polesia's "
            "own year: the days the land around Chernobyl turns, not the equinoxes.")
            ).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=(10, 8))
        ttk.Label(row, text="Start from:").pack(side="left")
        ttk.Button(row, text="Polesia (the default)",
                   command=lambda: self.use_dates(ce.polesia())).pack(side="left", padx=6)
        ttk.Button(row, text="Meteorological (month starts)",
                   command=lambda: self.use_dates(ce.meteorological())).pack(side="left")

        grid = ttk.Frame(f)
        grid.pack(anchor="w")
        for col, text in ((1, "Starts"), (3, "Runs"), (4, "Length")):
            ttk.Label(grid, text=text, foreground="#666666").grid(row=0, column=col,
                                                                  sticky="w", padx=(0, 4))
        self.srows = {}
        for i, s in enumerate(season.SEASONS, start=1):
            m, d = self.cal.dates.get(s, ce.polesia()[s])
            on = tk.BooleanVar(value=s in self.cal.dates)
            mon, day = tk.StringVar(value=ce.MONTHS[m - 1]), tk.StringVar(value=str(d))
            ttk.Checkbutton(grid, text=label(s).capitalize(), variable=on, width=14,
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
            runs = ttk.Label(grid, text="", width=24)
            runs.grid(row=i, column=3, sticky="w", padx=(14, 0))
            days = ttk.Label(grid, text="", width=10, foreground="#666666")
            days.grid(row=i, column=4, sticky="w")
            self.srows[s] = (on, mon, day, cb, sp, runs, days)
        self.cal_msg = ttk.Label(f, text="", foreground="#b03020", wraplength=860,
                                 justify="left")
        self.cal_msg.pack(anchor="w", pady=(12, 0))
        self.cal_note = ttk.Label(f, text="", foreground="#666666", wraplength=860,
                                  justify="left")
        self.cal_note.pack(anchor="w", pady=(6, 0))
        self.dates_edited()

    def use_dates(self, dates):
        """Every season on, at `dates`."""
        self._filling = True
        for s, (on, mon, day, cb, sp, runs, days) in self.srows.items():
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
        for s, (on, mon, day, cb, sp, runs, days) in self.srows.items():
            on.set(s in dates)
            if s in dates:
                mon.set(ce.MONTHS[dates[s][0] - 1])
                day.set(str(dates[s][1]))
        self._filling = False
        self.dates_edited()

    def dates_edited(self):
        if self._filling:
            return
        dates, bad = {}, []
        for s, (on, mon, day, cb, sp, runs, days) in self.srows.items():
            m = ce.MONTHS.index(mon.get()) + 1
            try:
                d = int(day.get())
            except ValueError:
                d = 0
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
                    bad.append(label(s))
                else:
                    dates[s] = (m, d)
        self.bad_dates = bad
        if not bad:
            self.cal.dates = dates
        self.refresh_seasons()

    def refresh_seasons(self):
        dates = self.cal.dates
        problems = (["Give %s a start day." % ", ".join(self.bad_dates)]
                    if self.bad_dates else []) + season.calendar_problems(dates)
        wins = ce.season_windows(dates) if dates else {}
        days = season.season_lengths(dates) if dates and not problems else {}
        for s, (on, mon, day, cb, sp, runs, dl) in self.srows.items():
            runs.configure(text=wins.get(s, "off"),
                           foreground="#000000" if s in dates else "#888888")
            dl.configure(text="%d days" % days[s] if s in days else "")
        self.cal_msg.configure(text="\n".join(problems))
        notes = []
        if not self.cal.custom():
            notes.append("This is Polesia's calendar, the default.")
        elif have_pillow():
            notes.append("Saving hands these dates to the game and draws the year dial in "
                         "MCM and on the PDA for them.")
        else:
            notes.append("Saving hands these dates to the game. The year dial in MCM and on "
                         "the PDA is drawn for Polesia's; drawing one for yours needs Pillow, "
                         "which Save offers to install. Without it the dial is hidden.")
        stranded = [n for n, c in self.cal.toggle.items() if c["when"] and all(
            p in season.SEASONS and p not in dates for p in c["when"])]
        if stranded:
            notes.append("On only in seasons that are off, so never switched on: "
                         + ", ".join(stranded))
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
        if self.cal.dirty():
            text += "  -  unsaved changes"
        self.status.configure(text=text)

    def save(self, quiet=False):
        from tkinter import messagebox
        if self.bad_dates:
            if not quiet:
                messagebox.showerror("Save", "Give %s a start day first."
                                     % ", ".join(self.bad_dates), parent=self.root)
            return False
        changed = self.cal.dates_changed()
        saved, lines = self.cal.save()
        if saved and changed:
            ok, out = draw_dial()
            lines = lines + [""] + out
        if not quiet:
            (messagebox.showinfo if saved else messagebox.showerror)(
                "Save", "\n".join(lines), parent=self.root)
            if saved and changed and self.cal.custom() and not have_pillow():
                self.offer_pillow()
        self.fill()
        self.show()
        self.update_status()
        return saved

    def offer_pillow(self):
        from tkinter import messagebox
        if not messagebox.askyesno("The year dial", (
                "The dial in MCM and on the PDA shows Polesia's dates, so it is hidden "
                "while your own are in use. Drawing one for them needs Pillow, a Python "
                "package.\n\nInstall it now? This runs:\n\n"
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
        if self.cal.dirty():
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
                ["seasons_config.py can't be read:", ""] + cal.error + [
                    "", "Start a new one? The old file is kept as seasons_config.py.bak."])):
            root.destroy()
            return
        cal.start_over()
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
    ap = argparse.ArgumentParser(description="Put mods on the calendar.")
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
    p.add_argument("start", nargs="?")
    p.add_argument("end", nargs="?")
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
                   help="start from Polesia's dates or the meteorological ones")
    p.add_argument("--reset", action="store_true", help="back to Polesia's calendar")
    a = ap.parse_args()
    {"list": cmd_list, "add": cmd_add, "remove": cmd_remove, "event": cmd_event,
     "calendar": cmd_calendar, None: lambda a: window()}[a.cmd](a)


if __name__ == "__main__":
    main()
