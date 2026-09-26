"""configure.bat's window: a guided setup, and the summary it opens to once there is one.

The setup goes in steps - where to start from, the seasonal mods, the seasons, the
weather, a review, and how to play - on one copy of seasons_config.py held in memory, which
the review saves. Once there is a setup, the window opens to a summary instead, and each
Change there opens one step on its own and saves from it.

A seasonal mod can be installed from its archive on the Seasonal mods step: simple
installer options become checkboxes, a fix file from its author goes where its name says,
and when it shares files with another seasonal mod on in the same season, the player is
asked which one's the game should use. mod_install.py does the archive side.

What the steps leave out - making events, periods, and fine control of which mod wins over
which - is in the tabbed editor, configure.App, a button away on every page.
"""
import datetime
import importlib.util
import io
import json
import os
import tempfile

import config_edit as ce
import configure as cf
import installer
import lang
import season
from lang import _, ngettext, pgettext

STEPS = ("start", "mods", "seasons", "weather", "review", "done")
GREEN = "#2e7d32"


def step_title(key):
    """A step's name, as the row of steps at the top shows it. Made when it is shown, so it
    follows a change of language."""
    return {"start": _("Start"), "mods": _("Seasonal mods"), "seasons": _("Seasons"),
            "weather": _("Weather"), "review": _("Review"), "done": _("How to play")}[key]


def comma_list(words):
    """Words one after another, the way a list runs them rather than a sentence: "a, b, c"."""
    return pgettext("between words in a list", ", ").join(words)


def usual_title(s):
    """A season's usual name in the player's language, for the start of a line: "Deep
    winter"."""
    v = season.usual_name(s)
    return v[:1].upper() + v[1:]


def is_set_up(cal):
    """Is there a setup to sum up? A first run - no file, or one with nothing in it - opens
    to the steps instead."""
    return bool(cal.toggle or cal.layout or cal.sound_src or cal.events or cal.periods
                or cal.own or cal.spells or cal.custom() or cal.names or cal.place)


def preset_from_data(data):
    """A preset made in memory, read the way a preset file is: (preset, problems)."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data))
        return ce.read_preset(path)
    finally:
        os.remove(path)


def shipped_default():
    """The GAMMA example: the setup these tools were made on. From its preset, or from
    seasons_config.example.py when the preset isn't there; None when neither is."""
    for name, path in ce.preset_files().items():
        if name.lower() == "gamma example":
            p, problems = ce.read_preset(path)
            if p and not problems:
                return p
    example = os.path.join(ce.HERE, "seasons_config.example.py")
    if os.path.isfile(example):
        c = ce.Calendar(example)
        if not c.error and not c.problems:
            data = ce.preset_from(c, [x for x in ce.parts_with_content(c) if x != "calendar"])
            p, problems = preset_from_data(data)
            if p and not problems:
                return p
    return None


def calendar_presets():
    """The calendars that come with the tool, Polesia's first: [(name, about, dates)]."""
    out = []
    for name, path in ce.preset_files().items():
        p, problems = ce.read_preset(path)
        if p and not problems and p["shipped"] and "calendar" in p:
            dates = ({s: tuple(md) for s, md in p["calendar"].items()} if p["calendar"]
                     else ce.polesia())
            out.append((name, p["about"], dates))
    if not any(d == ce.polesia() for _, _, d in out):
        out.append(("Polesia", "The Zone's own year, the default.", ce.polesia()))
    out.sort(key=lambda x: (x[2] != ce.polesia(), x[0]))
    return out


def season_on(day, dates):
    """The season `dates` has running on `day`."""
    starts = sorted((m, d, s) for s, (m, d) in dates.items())
    now = starts[-1][2]
    for m, d, s in starts:
        if (m, d) <= (day.month, day.day):
            now = s
    return now


def on_today(cal):
    """(the season today, the seasonal mods on today) for the setup `cal` holds, by its
    own calendar and events. Weather days are left out: they come with play.bat's fetch."""
    today = datetime.date.today()
    now = season_on(today, cal.dates)
    names = ({now} | {e for e, spec in cal.events.items() if season.event_on(today, spec)}
             | {o for o, win in cal.own.items() if season._in_window(today, *win)})
    spell = [(n, cal.spells[n]["as"]) for n, _, _ in cal.spells_on(today)]
    names |= {n for n, _ in spell}
    brings = next((b for _, b in spell if b), None)
    if brings:
        names = (names - {now}) | {brings}
        now = brings
    return now, sorted((n for n, c in cal.toggle.items() if names & set(c["when"])),
                       key=str.casefold)


def dates_words(dates):
    """A calendar as the seasons it has on and the day each starts, in season order."""
    return comma_list(
        pgettext("a season and the day it starts: spring Apr 15", "%(season)s %(day)s")
        % {"season": season.usual_name(s), "day": ce.day_text(dates[s])}
        for s in season.SEASONS if s in dates)


def seasons_words(cal):
    """The calendar and names `cal` holds, in a few words."""
    match = [n for n, __, d in calendar_presets() if d == cal.dates]
    names = comma_list(
        # translators: a season's usual name, then the name the player gave it
        _("%(season)s is \"%(name)s\"") % {"season": season.usual_name(s), "name": n}
        for s, n in sorted(cal.names.items(), key=lambda x: season.SEASONS.index(x[0])))
    if not cal.custom():
        return _("Polesia's dates; %s") % names if names else _("Polesia's dates")
    if match and names:
        # translators: %(calendar)s is the name of a calendar that comes with the tool
        return _("the %(calendar)s calendar; %(names)s") % {"calendar": match[0],
                                                            "names": names}
    if match:
        # translators: %s is the name of a calendar that comes with the tool
        return _("the %s calendar") % match[0]
    return _("your own dates; %s") % names if names else _("your own dates")


def own_words(cal, most=3):
    """The player's own seasons in a few words, in the order they come."""
    names = cal.own_order()
    text = comma_list("%s (%s)" % (n, ce.window_text(cal.own[n])) for n in names[:most])
    if len(names) > most:
        return ngettext("%(seasons)s and %(n)d more", "%(seasons)s and %(n)d more",
                        len(names) - most) % {"seasons": text, "n": len(names) - most}
    return text


def setup_words(cal):
    """A setup in one line: its mods, calendar and weather."""
    n = len(cal.toggle)
    return ngettext("%(n)d seasonal mod, %(seasons)s, weather from %(place)s.",
                    "%(n)d seasonal mods, %(seasons)s, weather from %(place)s.", n) % {
        "n": n, "seasons": seasons_words(cal),
        "place": (cal.place or ce.DEFAULT_PLACE)["name"]}


def parts_words(preset):
    return _("Holds its %s.") % comma_list(_(ce.PART_TEXT[p])
                                            for p in ce.preset_parts(preset))


def raw_problems(cal):
    """What season.py would refuse in the setup `cal` holds, as season.py says it."""
    return [] if cal.error else cal.check(cal.render()[0])


def step_for(problem):
    """The step where a refusal can be fixed, or None for the advanced editor."""
    if problem.startswith(("TOGGLE_MODS", "LAYOUT", "SOUND_SRC")):
        return "mods"
    if problem.startswith(("CALENDAR", "NAMES", "OWN_SEASONS", "SPELLS")):
        return "seasons"
    if problem.startswith("WEATHER_PLACE"):
        return "weather"
    return None


class Guide(object):
    """The guided setup and the summary, in one window. `cal` is what the steps edit; the
    review saves it."""

    def __init__(self, root, cal, inst):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root, self.cal, self.inst = root, cal, inst
        self.gamma = season.ROOT
        self.default = shipped_default()
        self.mode, self.step, self.editing = None, 0, None
        self.start_choice, self.applied = None, None
        self.kept, self.kept_layout = {}, {}    # unchecked this time round, to check again
        self.saved_lines = []
        self.seasons_bad, self.names_bad, self._fw, self._found = [], [], None, []
        style = ttk.Style(root)
        style.configure("Big.TLabel", font=("TkDefaultFont", 15, "bold"))
        style.configure("Head.TLabel", font=("TkDefaultFont", 10, "bold"))
        style.configure("Step.TLabel", foreground="#888888")
        style.configure("Now.TLabel", font=("TkDefaultFont", 9, "bold"))
        root.title(cf.TITLE)
        root.geometry("980x700")
        root.minsize(840, 600)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-s>", lambda e: self.ctrl_s())
        self.bar = ttk.Frame(root, padding=(18, 10))
        self.bar.pack(side="bottom", fill="x")
        ttk.Separator(root).pack(side="bottom", fill="x")
        self.top = ttk.Frame(root, padding=(18, 12, 18, 0))
        self.top.pack(side="top", fill="x")
        self.body = ttk.Frame(root, padding=(18, 10, 18, 6))
        self.body.pack(fill="both", expand=True)
        if is_set_up(cal):
            self.summary()
        else:
            self.steps()

    # --- pieces every page is built from ------------------------------------------------

    def clear(self):
        """Empty the window, and start a page that scrolls when it is taller than the
        window. Its text wraps to the window's width as it is now."""
        for frame in (self.top, self.body, self.bar):
            for w in frame.winfo_children():
                w.destroy()
        self.scroll = cf.Scrolled(self.body, self.tk, self.ttk, width=900)
        self.page = self.scroll.inner
        self.root.update_idletasks()
        self.wrap = max(self.root.winfo_width() - 130, 600)

    def heading(self, text):
        self.ttk.Label(self.page, text=text, style="Big.TLabel").pack(anchor="w")

    def para(self, text, parent=None, color=None, pad=(6, 0), indent=0, wrap=None):
        label = self.ttk.Label(parent or self.page, text=text,
                               wraplength=(wrap or self.wrap) - indent,
                               justify="left", foreground=color)
        label.pack(anchor="w", pady=pad, padx=(indent, 0))
        return label

    def subhead(self, text, parent=None, pad=(16, 4)):
        self.ttk.Label(parent or self.page, text=text, style="Head.TLabel").pack(
            anchor="w", pady=pad)

    def button(self, parent, text, command, default=False, side="left", pad=6):
        b = self.ttk.Button(parent, text=text, command=command,
                            default="active" if default else "normal")
        b.pack(side=side, padx=(pad, 0) if side == "left" else (0, pad))
        return b

    def language_box(self, parent):
        """A choice of the languages there is a translation for, which redraws the window in
        the one picked and keeps it for next time. None while English is all there is."""
        langs = lang.available()
        if len(langs) < 2:
            return None
        codes, names = [c for c, _n, _k in langs], [n for _c, n, _k in langs]
        now = lang.language()
        var = self.tk.StringVar(value=names[codes.index(now)] if now in codes else names[0])
        box = self.ttk.Combobox(parent, textvariable=var, values=names, state="readonly",
                                width=max(len(n) for n in names) + 2)
        box.pack(side="left", padx=(10, 0))

        def pick(e=None):
            code = codes[names.index(var.get())]
            if code == lang.language():
                return
            lang.save_choice(code)
            lang.use(code)
            if self.mode == "summary":
                self.summary()
            else:
                self.render()
        box.bind("<<ComboboxSelected>>", pick)
        self.lang_box = box
        return box

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

    # --- the steps ------------------------------------------------------------------------

    def steps(self, at="start"):
        """The guided setup, from `at`."""
        self.mode, self.editing = "steps", None
        self.step = STEPS.index(at)
        if self.start_choice is None:
            self.start_choice = self.default_start()
        self.render()

    def current(self):
        return STEPS[self.step] if self.mode == "steps" else self.editing

    def render(self):
        self.clear()
        key = self.current()
        if self.mode == "steps":
            for i, k in enumerate(STEPS):
                if i:
                    self.ttk.Label(self.top, text="  >  ", style="Step.TLabel").pack(
                        side="left")
                text = pgettext("a step's number and name: 1. Start",
                                "%(n)d. %(step)s") % {"n": i + 1, "step": step_title(k)}
                self.ttk.Label(self.top, text=text,
                               style="Now.TLabel" if i == self.step else "Step.TLabel").pack(
                    side="left")
        getattr(self, "step_" + key)()
        left, right = self.ttk.Frame(self.bar), self.ttk.Frame(self.bar)
        left.pack(side="left")
        right.pack(side="right")
        self.button(left, _("Advanced editor..."), self.advanced, pad=0)
        self.language_box(left)
        if self.mode == "edit":
            self.button(right, _("Save"), self.save_edit, default=True, side="right", pad=0)
            self.button(right, _("Cancel"), self.summary, side="right")
        elif key == "done":
            self.button(right, _("Close"), self.close, default=True, side="right", pad=0)
            self.button(right, _("Go to the summary"), self.summary, side="right")
        else:
            nxt = self.button(right, _("Save") if key == "review" else _("Next >"), self.next,
                              default=True, side="right", pad=0)
            if key == "review" and raw_problems(self.cal):
                nxt.configure(state="disabled")
            if self.step:
                self.button(right, _("< Back"), self.back, side="right")
        self.root.update_idletasks()

    def next(self):
        key = self.current()
        if not self.leave(key):
            return
        if key == "review" and not self.save_now():
            return
        self.step += 1
        self.render()

    def back(self):
        if self.current() == "start" or not self.leave(self.current(), going_back=True):
            return
        self.step -= 1
        self.render()

    def leave(self, key, going_back=False):
        """Can the step `key` be left as it stands? Says why not when it can't."""
        from tkinter import messagebox
        if key == "start":
            self.apply_start()
        elif key == "seasons" and (self.seasons_bad or self.names_bad) and not going_back:
            messagebox.showerror(cf.TITLE, "\n".join([_("Fix the seasons first:")]
                                                     + self.seasons_bad + self.names_bad),
                                 parent=self.root)
            return False
        elif key == "weather" and self.where.get() == "elsewhere" and not self.cal.place \
                and not going_back:
            messagebox.showerror(cf.TITLE, _("Pick a place from the search, or choose "
                                             "Chornobyl."), parent=self.root)
            return False
        return True

    # 1. where to start from

    def default_start(self):
        if is_set_up(ce.Calendar()):
            return "now"
        if self.default and any(m in self.inst.names for m in self.default.get("mods", {})):
            return "default"
        return "clean"

    def start_options(self):
        """[(key, title, about)] for where the setup can start from."""
        out = []
        now = ce.Calendar()
        if is_set_up(now):
            out.append(("now", _("What you have set up now"), setup_words(now)))
        for name, path in ce.preset_files().items():
            p, problems = ce.read_preset(path)
            if p and not problems and not p["shipped"]:
                out.append(("preset:" + name, _("Your preset \"%s\"") % name,
                            p["about"] or parts_words(p)))
        if self.default:
            mods = self.default.get("mods", {})
            have = [m for m in mods if m in self.inst.names]
            out.append(("default", _("The GAMMA example"), (
                ngettext("The seasonal mods these tools were made with - INVERNO's snow, C "
                         "Consciousness' grass and trees, and more - set up for the %(have)d "
                         "of %(all)d you have installed.",
                         "The seasonal mods these tools were made with - INVERNO's snow, C "
                         "Consciousness' grass and trees, and more - set up for the %(have)d "
                         "of %(all)d you have installed.", len(have))
                % {"have": len(have), "all": len(mods)} if have else
                _("The seasonal mods these tools were made with. None of them is installed "
                  "here."))))
        out.append(("clean", _("A clean start"), _("No seasonal mods yet: you pick them in the "
                                                   "next step. The seasons and the weather "
                                                   "stay as they are.")))
        return out

    def step_start(self):
        tk, ttk = self.tk, self.ttk
        self.heading(_("Set up Seasons of the Zone"))
        self.para(_("Light, color, fog, wind and wetness already follow the real calendar in "
                    "game; that needs no setup. This sets up the rest: the mods that switch "
                    "with the seasons, when the seasons turn, and where the real weather comes "
                    "from. It takes a couple of minutes, and you can change any of it later."))
        self.subhead(_("Start from"))
        self.start_var = tk.StringVar(value=self.start_choice)
        best = self.default_start()
        for key, name, about in self.start_options():
            ttk.Radiobutton(self.page, text=_("%s  (recommended)") % name if key == best
                            else name, value=key, variable=self.start_var,
                            command=lambda: setattr(self, "start_choice",
                                                    self.start_var.get())).pack(
                anchor="w", pady=(8, 0))
            self.para(about, color=cf.GREY, pad=(0, 0), indent=24)
        # translators: Review is the name of the fifth step
        self.para(_("Nothing is saved until the Review step, and every step shows what this "
                    "fills in, for you to change."), color=cf.GREY, pad=(18, 0))

    def apply_start(self):
        """Fill the setup in from where it starts. Only a new choice does anything, so going
        back to this step and on again keeps what the later steps changed."""
        choice = self.start_choice
        if choice == self.applied:
            return
        self.cal = ce.Calendar()
        self.kept, self.kept_layout = {}, {}
        if choice == "default":
            ce.apply_preset(self.cal, self.inst, self.default, ce.preset_parts(self.default))
        elif choice.startswith("preset:"):
            p, _ = ce.read_preset(ce.preset_files()[choice[len("preset:"):]])
            ce.apply_preset(self.cal, self.inst, p, ce.preset_parts(p))
        elif choice == "clean":
            self.cal.toggle, self.cal.layout, self.cal.sound_src = {}, {}, None
        self.applied = choice

    # 2. the seasonal mods

    def default_entry(self, name):
        """How the GAMMA example has `name` on, placed for this install, or None."""
        c = (self.default or {}).get("mods", {}).get(name)
        if not c:
            return None
        when = [p for p in c["when"] if p in self.cal.known()]
        above = c["above"] if self.inst.listed(c["above"]) else (
            ce.anchor_for(self.inst, name, when, self.cal.toggle)[0] or "")
        return {"when": when, "above": above}

    def step_mods(self):
        tk, ttk = self.tk, self.ttk
        self.heading(_("Which mods should change with the seasons?"))
        self.para(_("play.bat switches each checked mod on in its seasons and off the rest of "
                    "the year, before the game starts. Nothing is copied: MO2 just doesn't "
                    "load a mod while it's off."))
        box = self.page
        chosen = sorted(set(self.cal.toggle) | set(self.kept), key=str.casefold)
        known = (self.default or {}).get("mods", {})
        suggest = sorted((n for n in known if n in self.inst.names and n not in chosen),
                         key=str.casefold)
        grid = ttk.Frame(box)
        grid.pack(fill="x", pady=(8, 0))
        row = 0
        if not chosen and not suggest:
            ttk.Label(grid, text=_("None yet. Add the mods that should follow the seasons."),
                      foreground=cf.GREY).grid(row=0, column=0, sticky="w")
            row = 1
        for group, names in (("", chosen), (_("Also installed, and in the GAMMA example:"),
                                             suggest)):
            if not names:
                continue
            if group:
                ttk.Label(grid, text=group, style="Head.TLabel").grid(
                    row=row, column=0, columnspan=4, sticky="w", pady=(14, 4))
                row += 1
            for name in names:
                entry = (self.cal.toggle.get(name) or self.kept.get(name)
                         or self.default_entry(name))
                var = tk.BooleanVar(value=name in self.cal.toggle)
                ttk.Checkbutton(grid, text=name, variable=var, command=lambda n=name, v=var:
                                self.check_mod(n, v.get())).grid(row=row, column=0,
                                                                 sticky="w", pady=1)
                ttk.Label(grid, text=cf.when_text(entry["when"], self.cal) if entry else "",
                          foreground=cf.GREY).grid(row=row, column=1, sticky="w",
                                                   padx=(14, 0))
                ttk.Button(grid, text=_("Change..."), command=lambda n=name:
                           ModDialog(self, n)).grid(row=row, column=2, padx=(14, 0))
                if name not in self.inst.names:
                    new = os.path.isdir(os.path.join(season.MODS, name))
                    ttk.Label(grid, text=_("new: play.bat adds it to MO2's mod list") if new
                              else _("not in MO2's mod list"),
                              foreground=cf.GREY if new else cf.RED).grid(
                        row=row, column=3, sticky="w", padx=(10, 0))
                row += 1
        grid.columnconfigure(1, weight=1)
        row = ttk.Frame(box)
        row.pack(anchor="w", pady=(10, 0))
        self.button(row, _("Add another mod..."), lambda: ModDialog(self), pad=0)
        self.button(row, _("Install one from an archive..."), self.pick_archive)
        self.found_archives(box)
        self.mods_extras(box)
        self.mods_count = ttk.Label(box, text="", foreground=cf.GREY)
        self.mods_count.pack(anchor="w", pady=(12, 0))
        self.count_mods()

    def found_archives(self, box):
        """Archives in the GAMMA and downloads folders whose names say a season, not yet
        installed: one click from being seasonal mods."""
        mi = archives()
        if mi is None:
            return
        try:
            found = mi.found(self.gamma, set(os.listdir(season.MODS)))
        except OSError:
            return
        if not found:
            return
        self.subhead(_("Found in your GAMMA folder, not installed yet"), parent=box)
        for f in found:
            line = self.ttk.Frame(box)
            line.pack(anchor="w", fill="x", pady=1)
            self.ttk.Label(line, text=os.path.basename(f["path"])).pack(side="left")
            self.ttk.Label(line, text="  %s" % cf.when_text(f["seasons"], self.cal),
                           foreground=cf.GREY).pack(side="left")
            self.button(line, _("Install..."), lambda a=f["path"]: InstallDialog(self, a),
                        pad=12)

    def pick_archive(self):
        from tkinter import filedialog, messagebox
        if archives() is None:
            # translators: %s is a file in the tools' folder, _tools
            messagebox.showerror(cf.TITLE, _("%s is missing. Copy _tools from the mod's "
                                             "folder again.") % "_tools\\mod_install.py",
                                 parent=self.root)
            return
        path = filedialog.askopenfilename(
            parent=self.root, title=_("Install a mod from its archive"),
            initialdir=self.gamma, filetypes=[(_("Mod archives"), "*.7z *.zip *.rar"),
                                              (_("All files"), "*.*")])
        if path:
            InstallDialog(self, path)

    def mods_extras(self, box):
        """Texture sets swapped from their archives, and the ambient sound: the parts of a
        setup that aren't a mod switched on or off."""
        tk, ttk = self.tk, self.ttk
        layouts = dict(self.kept_layout, **self.cal.layout)
        for name, c in ((self.default or {}).get("layout") or {}).items():
            if name in self.inst.names and name not in layouts:
                layouts[name] = c
        src = self.cal.sound_src or (self.default or {}).get("sound_src")
        if src and not self.inst.listed(src):
            src = None
        if not layouts and not src:
            return
        self.subhead(_("Texture sets and ambient sound"), parent=box)
        for name in sorted(layouts, key=str.casefold):
            var = tk.BooleanVar(value=name in self.cal.layout)
            ttk.Checkbutton(box, text=_("%s: its seasonal sets, swapped from its archive")
                            % name, variable=var, command=lambda n=name, v=var, c=layouts[name]:
                            self.check_layout(n, c, v.get())).pack(anchor="w", pady=1)
            archive = layouts[name]["archive"]
            if not os.path.isfile(os.path.join(season.DOWNLOADS, archive)):
                self.para(_("Its archive, %s, isn't in MO2's downloads folder, so it can't be "
                            "swapped.") % archive, parent=box, color=cf.RED, pad=(0, 0),
                          indent=24)
            elif archive.lower().endswith(".7z") and not importlib.util.find_spec("py7zr"):
                # translators: %s is the command that installs it
                self.para(_("Swapping it needs py7zr, a Python package: %s")
                          % "py -m pip install py7zr", parent=box, color=cf.AMBER, pad=(0, 0),
                          indent=24)
        if src:
            var = tk.BooleanVar(value=bool(self.cal.sound_src))
            ttk.Checkbutton(box, text=_("Ambient sound follows the season, from %s") % src,
                            variable=var, command=lambda v=var, s=src:
                            setattr(self.cal, "sound_src", s if v.get() else None)).pack(
                anchor="w", pady=(6, 1))

    def check_mod(self, name, on):
        if on:
            entry = self.kept.pop(name, None) or self.default_entry(name)
            if entry is None:
                ModDialog(self, name)
                return
            self.cal.put(name, entry["when"], entry["above"])
        elif name in self.cal.toggle:
            self.kept[name] = self.cal.toggle[name]
            self.cal.take(name)
        self.count_mods()

    def check_layout(self, name, c, on):
        if on:
            self.cal.layout[name] = self.kept_layout.pop(name, c)
        elif name in self.cal.layout:
            self.kept_layout[name] = self.cal.layout.pop(name)

    def count_mods(self):
        n = len(self.cal.toggle)
        if getattr(self, "mods_count", None) and self.mods_count.winfo_exists():
            self.mods_count.configure(text=ngettext("%d seasonal mod checked.",
                                                    "%d seasonal mods checked.", n) % n)

    # 3. the seasons

    def step_seasons(self):
        tk, ttk = self.tk, self.ttk
        self.heading(_("When do the seasons turn?"))
        self.para(_("Polesia's dates follow the land around Chornobyl: the days it changes, "
                    "not the equinoxes. You can pick another calendar, set your own dates - a "
                    "season turned off gives its days to the one before it - or rename the "
                    "seasons."))
        cols = ttk.Frame(self.page)
        cols.pack(fill="both", expand=True, pady=(10, 0))
        right = ttk.Frame(cols)
        right.pack(side="right", fill="y", padx=(18, 0))
        left = ttk.Frame(cols)
        left.pack(side="left", fill="both", expand=True)
        self.dial = DialView(right, tk, ttk)
        presets = calendar_presets()
        match = [n for n, __, d in presets if d == self.cal.dates]
        self.cal_var = tk.StringVar(value=match[0] if match else "own")
        self.cal_dates = {n: d for n, __, d in presets}
        for name, about, dates in presets:
            ttk.Radiobutton(left, text=_("%s  (recommended)") % name if dates == ce.polesia()
                            else name, value=name, variable=self.cal_var,
                            command=self.pick_calendar).pack(anchor="w", pady=(6, 0))
            self.para(dates_words(dates), parent=left, color=cf.GREY, pad=(0, 0), indent=24,
                      wrap=560)
        ttk.Radiobutton(left, text=_("My own dates"), value="own", variable=self.cal_var,
                        command=self.pick_calendar).pack(anchor="w", pady=(6, 0))
        self.own_box = ttk.Frame(left)
        self.own_grid(self.own_box)
        self.names_on = tk.BooleanVar(value=bool(self.cal.names))
        self.names_check = ttk.Checkbutton(left, text=_("Give the seasons names of my own"),
                                           variable=self.names_on, command=self.show_names)
        self.names_check.pack(anchor="w", pady=(14, 0))
        self.names_box = ttk.Frame(left)
        self.names_grid(self.names_box)
        self.season_msg = ttk.Label(left, text="", foreground=cf.RED, wraplength=560,
                                    justify="left")
        self.season_msg.pack(anchor="w", pady=(8, 0))
        self.subhead(_("Seasons of your own"), parent=left)
        self.para(ngettext("A stretch of the year with a name of your own, a week or longer, "
                           "that runs on top of the season it falls in: the mods you put on in "
                           "it come on for those days, and the season's own mods stay on. You "
                           "can have up to %d.",
                           "A stretch of the year with a name of your own, a week or longer, "
                           "that runs on top of the season it falls in: the mods you put on in "
                           "it come on for those days, and the season's own mods stay on. You "
                           "can have up to %d.", season.OWN_MOST) % season.OWN_MOST,
                  parent=left, color=cf.GREY, pad=(0, 0), wrap=560)
        self.own_box_list = ttk.Frame(left)
        self.own_box_list.pack(anchor="w", fill="x", pady=(6, 0))
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=(6, 0))
        self.button(row, _("Add a season of your own..."), self.add_own, pad=0)
        self.subhead(_("Spells"), parent=left)
        self.para(ngettext("A short stretch, 1 to %d day, that starts by chance: on each day of "
                           "the seasons you pick there is a chance of it. It can bring another "
                           "season with it - winter for a day or two in summer - or switch on "
                           "only the mods you put on during it.",
                           "A short stretch, 1 to %d days, that starts by chance: on each day "
                           "of the seasons you pick there is a chance of it. It can bring "
                           "another season with it - winter for a day or two in summer - or "
                           "switch on only the mods you put on during it.",
                           season.SPELL_MOST_DAYS) % season.SPELL_MOST_DAYS,
                  parent=left, color=cf.GREY, pad=(0, 0), wrap=560)
        self.spell_box_list = ttk.Frame(left)
        self.spell_box_list.pack(anchor="w", fill="x", pady=(6, 0))
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=(6, 0))
        self.button(row, _("Add a spell..."), self.add_spell, pad=0)
        self.show_own()
        self.seasons_bad, self.names_bad = [], []
        self.pick_calendar(keep=True)
        self.show_names()

    def show_own(self):
        """The player's own seasons, each with a way to change it or take it off."""
        ttk = self.ttk
        for w in self.own_box_list.winfo_children():
            w.destroy()
        cal = self.cal
        if not cal.own:
            ttk.Label(self.own_box_list, text=_("None yet."), foreground=cf.GREY).pack(
                anchor="w")
        for n in cal.own_order():
            line = ttk.Frame(self.own_box_list)
            line.pack(anchor="w", fill="x", pady=1)
            ttk.Label(line, text=n, style="Head.TLabel", width=26).pack(side="left")
            users, days = len(cal.users_of(n)), season.own_days(cal.own[n])
            mods = (ngettext("on for %d mod", "on for %d mods", users) % users if users
                    else _("no mods on in it yet"))
            # translators: %(mods)s is "on for 2 mods" or "no mods on in it yet"
            text = ngettext("%(dates)s, %(days)d day; %(mods)s",
                            "%(dates)s, %(days)d days; %(mods)s", days) % {
                "dates": ce.window_text(cal.own[n]), "days": days, "mods": mods}
            ttk.Label(line, text=text, foreground=cf.GREY).pack(side="left")
            self.button(line, _("Remove"), lambda n=n: self.remove_own(n), side="right",
                        pad=0)
            self.button(line, _("Change..."), lambda n=n: cf.own_season_dialog(
                self.root, self.cal, editing=n, done=lambda name: self.show_own()),
                side="right")
        for w in self.spell_box_list.winfo_children():
            w.destroy()
        if not cal.spells:
            ttk.Label(self.spell_box_list, text=_("None yet."), foreground=cf.GREY).pack(
                anchor="w")
        for n in sorted(cal.spells, key=str.casefold):
            line = ttk.Frame(self.spell_box_list)
            line.pack(anchor="w", fill="x", pady=1)
            ttk.Label(line, text=n, style="Head.TLabel", width=26).pack(side="left")
            self.button(line, _("Remove"), lambda n=n: self.remove_spell(n), side="right",
                        pad=0)
            self.button(line, _("Change..."), lambda n=n: cf.spell_dialog(
                self.root, self.cal, editing=n, done=lambda name: self.show_own()),
                side="right")
            ttk.Label(line, text=cf.spell_words(cal, cal.spells[n]), foreground=cf.GREY,
                      wraplength=340, justify="left").pack(side="left")

    def add_own(self):
        cf.own_season_dialog(self.root, self.cal, done=lambda name: self.show_own())

    def remove_own(self, name):
        if cf.remove_own_season(self.root, self.cal, name):
            self.show_own()

    def add_spell(self):
        cf.spell_dialog(self.root, self.cal, done=lambda name: self.show_own())

    def remove_spell(self, name):
        if cf.remove_spell(self.root, self.cal, name):
            self.show_own()

    def pick_calendar(self, keep=False):
        name = self.cal_var.get()
        if name == "own":
            self.own_box.pack(anchor="w", padx=(24, 0), pady=(4, 0), before=self.names_check)
            if not keep:
                self.own_edited()
        else:
            self.own_box.pack_forget()
            self.cal.set_dates(self.cal_dates[name])
            self.fill_own(self.cal.dates)
            self.seasons_bad = []
            self.show_msgs()
        self.redraw()

    def own_grid(self, parent):
        tk, ttk = self.tk, self.ttk
        self.own_rows = {}
        for i, s in enumerate(season.SEASONS):
            m, d = self.cal.dates.get(s, ce.polesia()[s])
            on = tk.BooleanVar(value=s in self.cal.dates)
            mon, day = tk.StringVar(value=lang.month(m)), tk.StringVar(value=str(d))
            ttk.Checkbutton(parent, text=usual_title(s), variable=on,
                            width=13, command=self.own_edited).grid(row=i, column=0,
                                                                    sticky="w", pady=2)
            cb = ttk.Combobox(parent, textvariable=mon, values=lang.months(), state="readonly",
                              width=5)
            cb.grid(row=i, column=1, sticky="w")
            cb.bind("<<ComboboxSelected>>", lambda e: self.own_edited())
            sp = ttk.Spinbox(parent, from_=1, to=31, textvariable=day, width=4,
                             command=self.own_edited)
            sp.grid(row=i, column=2, sticky="w", padx=(4, 0))
            sp.bind("<KeyRelease>", lambda e: self.own_edited())
            runs = ttk.Label(parent, text="", foreground=cf.GREY)
            runs.grid(row=i, column=3, sticky="w", padx=(14, 0))
            self.own_rows[s] = (on, mon, day, runs)
        self.fill_own(self.cal.dates)

    def fill_own(self, dates):
        wins = ce.season_windows(dates) if not season.calendar_problems(dates) else {}
        off = pgettext("a season, turned off", "off")
        for s, (on, mon, day, runs) in self.own_rows.items():
            if s in dates:
                on.set(True)
                mon.set(lang.month(dates[s][0]))
                day.set(str(dates[s][1]))
            else:
                on.set(False)
            runs.configure(text=wins.get(s, off) if s in dates else off)

    def own_edited(self):
        dates, bad = {}, []
        for s, (on, mon, day, runs) in self.own_rows.items():
            if not on.get():
                continue
            m = lang.months().index(mon.get()) + 1
            d = int(day.get()) if cf.DAY_BOX.match(day.get()) else 0
            last = 28 if m == 2 else ce.DAYS[m - 1]
            if d > last:
                d = last
                day.set(str(d))
            if d < 1:
                bad.append(season.usual_name(s))
            else:
                dates[s] = (m, d)
        problems = ([_("Give %s a start day.") % lang.and_list(bad)] if bad else
                    [_("Check at least one season.")] if not dates else
                    [cf.plain(p) for p in season.calendar_problems(dates)])
        if not problems:
            self.cal.set_dates(dates)
        wins = ce.season_windows(dates) if not problems else {}
        off = pgettext("a season, turned off", "off")
        for s, (on, mon, day, runs) in self.own_rows.items():
            runs.configure(text=wins.get(s, "") if on.get() else off)
        self.seasons_bad = problems
        self.show_msgs()
        self.redraw()

    def names_grid(self, parent):
        tk, ttk = self.tk, self.ttk
        fits = self.root.register(lambda text: len(text) <= season.NAME_CHARS)
        self.name_vars = {}
        for i, s in enumerate(season.SEASONS):
            ttk.Label(parent, text=usual_title(s), width=13).grid(
                row=i, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=self.cal.names.get(s, ""))
            e = ttk.Entry(parent, textvariable=v, width=24, validate="key",
                          validatecommand=(fits, "%P"))
            e.grid(row=i, column=1, sticky="w")
            e.bind("<KeyRelease>", lambda ev: self.names_edited())
            self.name_vars[s] = v
        ttk.Label(parent, text=ngettext("Up to %d letter. Leave one empty for its usual name.",
                                        "Up to %d letters. Leave one empty for its usual name.",
                                        season.NAME_CHARS) % season.NAME_CHARS,
                  foreground=cf.GREY).grid(row=6, column=0, columnspan=2, sticky="w",
                                           pady=(4, 0))

    def show_names(self):
        if self.names_on.get():
            self.names_box.pack(anchor="w", padx=(24, 0), pady=(4, 0), before=self.season_msg)
        else:
            self.names_box.pack_forget()
            for v in self.name_vars.values():
                v.set("")
            self.names_edited()

    def names_edited(self):
        names = {s: v.get() for s, v in self.name_vars.items() if v.get().strip()}
        self.names_bad = [cf.plain(p) for p in season.names_problems(names)]
        if not self.names_bad:
            self.cal.set_names(names)
        self.show_msgs()
        self.redraw()

    def show_msgs(self):
        self.season_msg.configure(text="\n".join(self.seasons_bad + self.names_bad))

    def redraw(self):
        if getattr(self, "dial", None):
            self.dial.draw(self.cal.dates, self.cal.names,
                           bad=bool(self.seasons_bad or self.names_bad))

    # 4. the weather

    def step_weather(self):
        tk, ttk = self.tk, self.ttk
        self.heading(_("Where should the real weather come from?"))
        self.para(_("The PDA's temperature, its Forecast page and the freezing, thaw and heat "
                    "days follow the real weather at one place. play.bat asks Open-Meteo for "
                    "that place's day at each launch, sending its coordinates and nothing "
                    "else."))
        self.where = tk.StringVar(value="elsewhere" if self.cal.place else "chornobyl")
        ttk.Radiobutton(self.page, text=_("Chornobyl, the real Zone  (recommended)"),
                        value="chornobyl", variable=self.where,
                        command=self.pick_where).pack(anchor="w", pady=(12, 0))
        ttk.Radiobutton(self.page, text=_("Somewhere else"), value="elsewhere",
                        variable=self.where, command=self.pick_where).pack(anchor="w",
                                                                           pady=(6, 0))
        self.where_box = ttk.Frame(self.page)
        row = ttk.Frame(self.where_box)
        row.pack(fill="x")
        self.query = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.query, width=34)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.find_place())
        self.button(row, _("Search"), self.find_place)
        ttk.Label(row, text=_("a town or city, like Kyiv or New York"),
                  foreground=cf.GREY).pack(side="left", padx=(10, 0))
        self.found = tk.Listbox(self.where_box, height=5, width=80, exportselection=False,
                                activestyle="dotbox")
        self.found.pack(anchor="w", pady=(6, 0))
        self.found.bind("<Double-Button-1>", lambda e: self.use_found())
        row = ttk.Frame(self.where_box)
        row.pack(fill="x", pady=(6, 0))
        self.button(row, _("Use this place"), self.use_found, pad=0)
        self.found_msg = ttk.Label(row, text="", foreground=cf.GREY)
        self.found_msg.pack(side="left", padx=(10, 0))
        cf.credit(self.where_box, cf.PLACES_CREDIT).pack(anchor="w", pady=(4, 0))
        row = ttk.Frame(self.where_box)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text=_("Or its coordinates:")).pack(side="left")
        self.lat, self.lon, self.named = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for text, var, width in ((_("latitude"), self.lat, 8), (_("longitude"), self.lon, 8),
                                 (pgettext("a place's name", "name"), self.named, 20)):
            ttk.Label(row, text=text, foreground=cf.GREY).pack(side="left", padx=(10, 4))
            ttk.Entry(row, textvariable=var, width=width).pack(side="left")
        self.button(row, _("Use these"), self.use_coords, pad=10)
        self.place_label = ttk.Label(self.page, text="", style="Head.TLabel")
        self.place_label.pack(anchor="w", pady=(16, 0))
        row = ttk.Frame(self.page)
        row.pack(fill="x", pady=(6, 0))
        self.button(row, _("Today's weather there"), self.check_place, pad=0)
        self.check_label = ttk.Label(self.page, text="", justify="left")
        self.check_label.pack(anchor="w", pady=(6, 0))
        self.check_credit = cf.credit(self.page, cf.WEATHER_CREDIT)
        self.climate = ttk.Frame(self.page)
        self.para(_("For a place other than Chornobyl, saving also looks up its climate once "
                    "- its last ten years of highs and lows - so the game can model a day "
                    "there without a connection."), parent=self.climate, color=cf.GREY)
        cf.credit(self.climate, cf.CLIMATE_CREDIT).pack(anchor="w", pady=(2, 0))
        self.pick_where()

    def pick_where(self):
        if self.where.get() == "chornobyl":
            self.cal.set_place(None)
            self.where_box.pack_forget()
            self.climate.pack_forget()
        else:
            self.where_box.pack(anchor="w", fill="x", padx=(24, 0), pady=(6, 0),
                                before=self.place_label)
            self.climate.pack(anchor="w", pady=(16, 0), fill="x")
        self.show_place()

    def show_place(self):
        if self.cal.place or self.where.get() == "chornobyl":
            text = _("Weather from: %s") % ce.place_text(self.cal.place)
        else:
            text = _("Weather from: pick a place above")
        self.place_label.configure(text=text)
        self.check_label.configure(text="")
        self.check_credit.pack_forget()

    def fetcher(self, label):
        if self._fw is None:
            try:
                import fetch_weather
                self._fw = fetch_weather
            except ImportError:
                # translators: %s is a file in the tools' folder, _tools
                label.configure(text=_("%s is missing. Copy _tools from the mod's folder "
                                       "again.") % "_tools\\fetch_weather.py",
                                foreground=cf.RED)
        return self._fw

    def find_place(self):
        fw = self.fetcher(self.found_msg)
        text = self.query.get().strip()
        if not fw:
            return
        if not text:
            self.found_msg.configure(text=_("Type a place to look for."), foreground=cf.RED)
            return
        self.found_msg.configure(text=_("Looking it up..."), foreground=cf.GREY)
        self.found.delete(0, "end")
        self._found = []

        def done(found, error):
            if not self.found.winfo_exists():
                return
            if error is not None:
                # translators: %s is the kind of error, as Python names it
                self.found_msg.configure(text=_("Couldn't reach open-meteo.com (%s).")
                                         % type(error).__name__, foreground=cf.RED)
                return
            self._found = found
            for p in found:
                self.found.insert("end", cf.found_text(p))
            if found:
                self.found.selection_set(0)
            # translators: Use this place is the button's name
            msg = (ngettext("%d found. Pick one and press Use this place.",
                            "%d found. Pick one and press Use this place.", len(found))
                   % len(found) if found else _("Nothing by that name. Try another spelling."))
            self.found_msg.configure(text=msg, foreground=cf.GREY if found else cf.RED)

        self.in_background(lambda: fw.search(text), done)

    def use_found(self):
        sel = self.found.curselection()
        if not sel or sel[0] >= len(self._found):
            self.found_msg.configure(text=_("Pick a place in the list first."),
                                     foreground=cf.RED)
            return
        f = self._found[sel[0]]
        self.cal.set_place({"name": f["name"][:season.PLACE_CHARS].strip(), "lat": f["lat"],
                            "lon": f["lon"]})
        self.found_msg.configure(text="", foreground=cf.GREY)
        self.show_place()

    def use_coords(self):
        """A place by its coordinates, for one the search doesn't know, or without a
        connection: degrees, north and east positive."""
        def number(v):
            try:
                return float(v.strip().replace(",", "."))
            except ValueError:
                return None

        lat, lon = number(self.lat.get()), number(self.lon.get())
        if lat is None or lon is None:
            self.found_msg.configure(text=_("Give the latitude and longitude as numbers, like "
                                            "50.45 and 30.52."), foreground=cf.RED)
            return
        place = {"name": self.named.get().strip() or "%.2f, %.2f" % (lat, lon),
                 "lat": lat, "lon": lon}
        problems = season.place_problems(place)
        if problems:
            self.found_msg.configure(text=" ".join(cf.reason(p) for p in problems),
                                     foreground=cf.RED)
            return
        self.cal.set_place(place)
        self.found_msg.configure(text="", foreground=cf.GREY)
        self.show_place()

    def check_place(self):
        fw = self.fetcher(self.check_label)
        if not fw:
            return
        place = self.cal.place or ce.DEFAULT_PLACE
        self.check_label.configure(text=_("Asking open-meteo.com..."), foreground=cf.GREY)
        self.check_credit.pack_forget()

        def done(rows, error):
            if not self.check_label.winfo_exists():
                return
            if error is not None or not rows:
                # translators: %s is the kind of error, as Python names it
                self.check_label.configure(text=_("Couldn't reach open-meteo.com (%s).")
                                           % type(error).__name__, foreground=cf.RED)
                return
            t = rows[0]
            # translators: %(sky)s is the sky that day, like "partly cloudy"
            self.check_label.configure(foreground="#000000", text=_(
                "Today in %(place)s: high %(high).0f°C (%(high_f).0f°F), low %(low).0f°C "
                "(%(low_f).0f°F), %(sky)s.") % {
                    "place": place["name"], "high": t["high"], "high_f": t["high"] * 9 / 5 + 32,
                    "low": t["low"], "low_f": t["low"] * 9 / 5 + 32,
                    "sky": cf.SKY.get(t["cycle"], t["cycle"])})
            self.check_credit.pack(anchor="w", after=self.check_label)

        self.in_background(lambda: fw.to_rows(fw.fetch(place)), done)

    # 5. review

    def step_review(self):
        ttk = self.ttk
        self.heading(_("Check it, then save"))
        grid = ttk.Frame(self.page)
        grid.pack(anchor="w", pady=(12, 0))
        for i, (what, text) in enumerate(self.review_rows()):
            ttk.Label(grid, text=what, style="Head.TLabel").grid(row=i, column=0, sticky="nw",
                                                                 pady=3)
            ttk.Label(grid, text=text, wraplength=680, justify="left").grid(
                row=i, column=1, sticky="w", padx=(18, 0), pady=3)
        now, on = on_today(self.cal)
        n = len(self.cal.toggle)
        if not n:
            text = _("With no seasonal mods, play.bat has nothing to switch. The seasonal "
                     "atmosphere runs all the same.")
        elif on:
            # translators: %(on)s is a list of the mods on today
            text = ngettext("Today is %(season)s. With this setup, play.bat has %(on)s on, and "
                            "the other %(off)d off until their seasons.",
                            "Today is %(season)s. With this setup, play.bat has %(on)s on, and "
                            "the other %(off)d off until their seasons.", n - len(on)) % {
                "season": cf.label(now, self.cal), "on": ce.few(on, 3), "off": n - len(on)}
        else:
            text = ngettext("Today is %(season)s. With this setup, play.bat has none of them "
                            "on, and the other %(off)d off until their seasons.",
                            "Today is %(season)s. With this setup, play.bat has none of them "
                            "on, and the other %(off)d off until their seasons.", n) % {
                "season": cf.label(now, self.cal), "off": n}
        self.para(text, pad=(16, 0))
        problems = raw_problems(self.cal)
        if problems:
            self.subhead(_("Fix these first; play.bat would refuse the setup as it is:"))
            self.problem_rows(self.page, problems)
        row = ttk.Frame(self.page)
        row.pack(anchor="w", pady=(16, 0))
        self.button(row, _("Preview what play.bat would do..."),
                    lambda: cf.show_preview(self.root, self.cal), pad=0)
        # translators: Save is the button's name; %s is the file it writes
        self.para(_("Save writes %s; the file it replaces is kept beside it as "
                    "seasons_config.py.bak.") % "_tools\\seasons_config.py", color=cf.GREY,
                  pad=(14, 0))

    def review_rows(self):
        cal = self.cal
        rows = [(_("Seasonal mods"), "%d: %s" % (len(cal.toggle), ce.few(cal.toggle, 3))
                 if cal.toggle else _("none"))]
        if cal.layout:
            rows.append((_("Texture sets"), ce.few(cal.layout, 3)))
        if cal.sound_src:
            rows.append((_("Ambient sound"), _("follows the season, from %s") % cal.sound_src))
        rows.append((_("Seasons"), seasons_words(cal)))
        if cal.own:
            rows.append((_("Seasons of your own"), own_words(cal)))
        if cal.spells:
            rows.append((_("Spells"), ce.few(cal.spells, 4)))
        rows.append((_("Weather from"), ce.place_text(cal.place)))
        if cal.events:
            rows.append((_("Events"), ce.few(cal.events, 4)))
        return rows

    def problem_rows(self, parent, problems):
        ttk = self.ttk
        for p in problems[:5]:
            line = ttk.Frame(parent)
            line.pack(fill="x", pady=1)
            key = step_for(p)
            self.button(line, _("Fix"), (lambda k=key: self.fix(k)), side="right", pad=0)
            ttk.Label(line, text="- " + cf.plain(p), foreground=cf.RED, wraplength=760,
                      justify="left").pack(side="left", anchor="w")
        if len(problems) > 5:
            ttk.Label(parent, text=ngettext("and %d more", "and %d more", len(problems) - 5)
                      % (len(problems) - 5), foreground=cf.RED).pack(anchor="w")

    def fix(self, key):
        if key is None:
            self.advanced()
        elif self.mode == "steps":
            self.step = STEPS.index(key)
            self.render()
        else:
            self.edit(key)

    # 6. how to play

    def step_done(self):
        self.heading(_("All set"))
        if self.saved_lines:
            self.para("\n".join(l for l in self.saved_lines if l), color=cf.GREY)
        self.subhead(_("How to play"))
        self.para(_("From now on, start the game with play.bat in your GAMMA folder, not from "
                    "MO2. Each time, it switches the seasonal mods for the day, then opens MO2 "
                    "and starts the game. Most days it has nothing to switch."))
        self.shortcut_row(self.page).pack(anchor="w", pady=(12, 0))
        self.para(_("To change any of this later, open configure.bat again: it opens to a "
                    "summary of your setup."), color=cf.GREY, pad=(16, 0))
        row = self.ttk.Frame(self.page)
        row.pack(anchor="w", pady=(10, 0))
        self.button(row, _("Save this setup as a preset..."),
                    lambda: cf.save_preset_dialog(self.root, self.cal), pad=0)

    def shortcut_row(self, parent):
        """Which MO2 entry play.bat starts, to change, and whether MO2 has it."""
        tk, ttk = self.tk, self.ttk
        from tkinter import messagebox
        play = os.path.join(self.gamma, "play.bat")
        entries = installer.mo2_entries(self.gamma)
        now = installer.read_shortcut(play)
        line = ttk.Frame(parent)
        # translators: followed by a list of the programs MO2 can start, like Anomaly (DX11)
        ttk.Label(line, text=_("play.bat starts")).pack(side="left")
        var = tk.StringVar(value=now or "")
        combo = ttk.Combobox(line, textvariable=var, state="readonly", width=34,
                             values=entries + ([now] if now and now not in entries else []))
        combo.pack(side="left", padx=(8, 0))
        status = ttk.Label(line, text="")
        status.pack(side="left", padx=(10, 0))

        def show():
            if not os.path.isfile(play):
                combo.configure(state="disabled")
                status.configure(text=_("play.bat isn't in your GAMMA folder. Open "
                                        "configure.bat from the mod's folder to put it there."),
                                 foreground=cf.RED)
            elif var.get() in entries:
                status.configure(text=_("✓ MO2 has this entry"), foreground=GREEN)
            else:
                status.configure(text=_("MO2 has no entry by that name. Pick one."),
                                 foreground=cf.RED)

        def pick(e=None):
            try:
                installer.write_shortcut(play, var.get())
            except (ValueError, OSError) as err:
                messagebox.showerror("play.bat", str(err), parent=self.root)
                var.set(installer.read_shortcut(play) or "")
            show()

        combo.bind("<<ComboboxSelected>>", pick)
        show()
        self.shortcut_combo, self.shortcut_status = combo, status
        return line

    # --- saving ---------------------------------------------------------------------------

    def save_now(self):
        """Write the setup, and hand what changed to the game: the dial for a calendar or
        names, the weather for a new place. False, with the reason shown, when refused."""
        from tkinter import messagebox
        moved, placed = cf.calendar_moved(self.cal), self.cal.place_changed()
        saved, lines = self.cal.save()
        if not saved:
            messagebox.showerror(pgettext("dialog title", "Save"),
                                 "\n".join(cf.plain(l) for l in lines), parent=self.root)
            return False
        extra = []
        if self.cal.wrote:
            self.root.configure(cursor="watch")
            self.root.update()
            if moved:
                ok, out = cf.draw_dial()
                extra += [""] + (cf.dial_sentence(self.cal) if ok else out)
            if placed:
                extra += ["", _("The weather now comes from %s:")
                          % ce.place_text(self.cal.place)]
                extra += cf.fetch_now()
            self.root.configure(cursor="")
        self.saved_lines = lines + extra
        self.applied = self.start_choice = "now"
        self.kept, self.kept_layout = {}, {}
        if moved and (self.cal.custom() or self.cal.names) and not cf.have_pillow():
            cf.offer_pillow(self.root)
        return True

    def ctrl_s(self):
        if self.mode == "edit":
            self.save_edit()
        elif self.mode == "steps" and self.current() == "review":
            self.next()

    # --- the summary ----------------------------------------------------------------------

    def summary(self):
        """The setup as saved, with a way to change each part."""
        ttk = self.ttk
        self.mode, self.editing = "summary", None
        self.cal = ce.Calendar()
        self.kept, self.kept_layout = {}, {}
        self.clear()
        self.heading(_("Seasons of the Zone"))
        if self.cal.error:
            # changed on disk while the window was open, into something it can't read
            self.para("\n".join([_("seasons_config.py can't be read now:")] + self.cal.error),
                      color=cf.RED)
            self.para(_("Fix it in Notepad and open configure.bat again. It is %s.")
                      % self.cal.path)
            self.button(self.bar, _("Close"), self.close, default=True, side="right", pad=0)
            return
        self.para(_("Your setup, as saved. Change any part; each change is saved on its own."))
        grid = ttk.Frame(self.page)
        grid.pack(anchor="w", fill="x", pady=(14, 0))
        cal = self.cal
        rows = [(_("Seasonal mods"), "%d: %s" % (len(cal.toggle), ce.few(cal.toggle, 3))
                 if cal.toggle else _("none yet"), lambda: self.edit("mods"))]
        if cal.layout or cal.sound_src:
            if cal.layout and cal.sound_src:
                # translators: %(sets)s is a list of the mods whose texture sets are swapped
                text = _("%(sets)s; ambient sound from %(mod)s") % {
                    "sets": ce.few(cal.layout, 2), "mod": cal.sound_src}
            elif cal.layout:
                text = ce.few(cal.layout, 2)
            else:
                text = _("ambient sound from %s") % cal.sound_src
            rows.append((_("Texture sets and sound"), text, lambda: self.edit("mods")))
        rows += [(_("Seasons"), seasons_words(cal), lambda: self.edit("seasons")),
                 (_("Seasons of your own"), own_words(cal) if cal.own else _("none yet"),
                  lambda: self.edit("seasons")),
                 (_("Spells"), ce.few(cal.spells, 3) if cal.spells else _("none yet"),
                  lambda: self.edit("seasons")),
                 (_("Weather from"), ce.place_text(cal.place), lambda: self.edit("weather")),
                 (_("Events"),
                  # translators: %s is a list of the player's events
                  _("%s (changed in the advanced editor)") % ce.few(cal.events, 3)
                  if cal.events else _("none (made in the advanced editor)"), self.advanced)]
        for i, (what, text, change) in enumerate(rows):
            ttk.Label(grid, text=what, style="Head.TLabel").grid(row=i, column=0, sticky="nw",
                                                                 pady=5)
            ttk.Label(grid, text=text, wraplength=560, justify="left").grid(
                row=i, column=1, sticky="w", padx=(18, 0), pady=5)
            ttk.Button(grid, text=_("Change..."), command=change).grid(
                row=i, column=2, sticky="e", padx=(18, 0))
        grid.columnconfigure(1, weight=1)
        self.shortcut_row(self.page).pack(anchor="w", pady=(16, 0))
        if cal.problems:
            self.subhead(_("play.bat refuses the setup as it is, until these are fixed:"))
            self.problem_rows(self.page, cal.problems)
        left, right = ttk.Frame(self.bar), ttk.Frame(self.bar)
        left.pack(side="left")
        right.pack(side="right")
        self.button(left, _("Advanced editor..."), self.advanced, pad=0)
        self.button(left, _("Run the setup again"), lambda: self.steps())
        self.button(left, _("Save as a preset..."),
                    lambda: cf.save_preset_dialog(self.root, self.cal))
        self.language_box(left)
        self.button(right, _("Close"), self.close, default=True, side="right", pad=0)
        self.button(right, _("Preview the next launch..."),
                    lambda: cf.show_preview(self.root, self.cal), side="right")

    def edit(self, key):
        """One step on its own, from the summary, saved from there."""
        self.mode, self.editing = "edit", key
        self.render()

    def save_edit(self):
        from tkinter import messagebox
        if not self.leave(self.editing):
            return
        problems = raw_problems(self.cal)
        if problems:
            messagebox.showerror(pgettext("dialog title", "Save"), "\n".join(
                [_("play.bat would refuse this:")] + [cf.plain(p) for p in problems]),
                parent=self.root)
            return
        if not self.save_now():
            return
        messagebox.showinfo(_("Saved"), "\n".join(self.saved_lines), parent=self.root)
        self.summary()

    # --- leaving --------------------------------------------------------------------------

    def unsaved(self):
        return (self.mode in ("steps", "edit") and self.current() != "done"
                and not self.cal.error and self.cal.dirty())

    def advanced(self):
        """The tabbed editor, for everything the steps leave out. What the steps changed is
        saved first, or left out."""
        from tkinter import messagebox
        if self.unsaved():
            ans = messagebox.askyesnocancel(
                _("Advanced editor"), _("Save what you've set here first? If not, the "
                                        "advanced editor opens on the setup as it was saved."),
                parent=self.root)
            if ans is None or (ans and (raw_problems(self.cal) or not self.save_now())):
                return
        top = self.tk.Toplevel(self.root)
        self.root.withdraw()
        cf.App(top, ce.Calendar(), self.inst)
        self.root.wait_window(top)
        self.root.deiconify()
        if is_set_up(ce.Calendar()):
            self.summary()
        else:
            self.steps()

    def close(self):
        from tkinter import messagebox
        if self.unsaved():
            if not messagebox.askyesno(
                    pgettext("dialog title", "Close"),
                    _("Leave without saving? Nothing you set here is kept."),
                    parent=self.root, default="no"):
                return
        self.root.destroy()


class DialView(object):
    """The year dial, drawn as the game will draw it for a calendar and names."""
    PX = 250
    PANEL = (17, 30, 19, 255)

    def __init__(self, parent, tk, ttk):
        self.blank = tk.PhotoImage(width=self.PX, height=self.PX)
        self.view = tk.Label(parent, image=self.blank,
                             background="#%02x%02x%02x" % self.PANEL[:3])
        self.view.pack()
        self.text = ttk.Label(parent, text="", foreground=cf.GREY, wraplength=self.PX,
                              justify="center")
        self.text.pack(pady=(6, 0))
        self.photo, self.bsd = None, None
        try:
            import build_season_dial
            from PIL import Image, ImageTk
            self.cols = build_season_dial.season_colors(os.path.join(
                season.MODS, season.SOTZ, "gamedata", "configs", "seasons_of_the_zone.ltx"))
            self.bsd, self.Image, self.ImageTk = build_season_dial, Image, ImageTk
        except ImportError:
            self.text.configure(text=_("Showing the dial here needs Pillow, a Python package. "
                                       "Save offers to install it."))
        except OSError:
            self.text.configure(text=_("The mod's configs folder is missing, so the dial "
                                       "can't be drawn here."))

    def draw(self, dates, names, bad=False):
        if self.bsd is None:
            return
        if bad or not dates or season.calendar_problems(dates):
            self.view.configure(image=self.blank)
            self.text.configure(text=_("The dial comes back when the lines in red are fixed."))
            return
        today = datetime.date.today()
        day = datetime.date(2026, today.month, min(today.day, 28) if today.month == 2
                            else today.day)
        bounds = sorted((m, d, s) for s, (m, d) in dates.items())
        __, at = self.bsd.shown(day, bounds)
        im = self.bsd.render(at, self.cols, bounds, dict(names))
        im = self.Image.alpha_composite(self.Image.new("RGBA", im.size, self.PANEL), im)
        self.photo = self.ImageTk.PhotoImage(im.resize((self.PX, self.PX),
                                                       self.Image.LANCZOS))
        self.view.configure(image=self.photo)
        self.text.configure(text=_("The dial in MCM and on the PDA, today."))


class ModDialog(object):
    """When one mod is on: its seasons, and under More options its events, weather and the
    mod it wins over. With no mod given, the mod to add is picked first."""

    def __init__(self, guide, name=None):
        tk, ttk = guide.tk, guide.ttk
        self.g, self.name = guide, name
        cal = guide.cal
        win, f = cf.dialog(guide.root, name or _("Add a seasonal mod"))
        self.win = win
        entry = ((cal.toggle.get(name) or guide.kept.get(name) or guide.default_entry(name))
                 if name else None)
        when = set(entry["when"]) if entry else set()
        focus = None
        if name is None:
            ttk.Label(f, text=_("Which mod?"), style="Head.TLabel").pack(anchor="w")
            self.query = tk.StringVar()
            e = ttk.Entry(f, textvariable=self.query, width=50)
            e.pack(anchor="w", pady=(4, 0))
            self.query.trace_add("write", lambda *a: self.fill())
            self.list = tk.Listbox(f, height=10, width=70, exportselection=False)
            self.list.pack(anchor="w", pady=(4, 0))
            own = season._own_folders()
            self.names = [n for n in sorted(guide.inst.names, key=str.casefold)
                          if n not in cal.toggle and n not in own]
            self.fill()
            focus = e
        ttk.Label(f, text=_("On in these seasons"), style="Head.TLabel").pack(anchor="w",
                                                                              pady=(12, 4))
        grid = ttk.Frame(f)
        grid.pack(anchor="w")
        self.vars = {}
        season_grid(tk, ttk, grid, cal, when, self.vars)
        self.more = tk.BooleanVar(value=bool(when - set(season.SEASONS) - set(cal.own)))
        ttk.Checkbutton(f, text=_("More options"), variable=self.more,
                        command=self.show_more).pack(anchor="w", pady=(12, 0))
        # a place held for the options, so they open above the buttons, not under them
        slot = ttk.Frame(f)
        slot.pack(anchor="w", fill="x")
        self.more_box = ttk.Frame(slot)
        extra = sorted(cal.periods) + sorted(cal.events)
        if extra:
            ttk.Label(self.more_box, text=_("Also on for these events"),
                      style="Head.TLabel").pack(anchor="w", pady=(6, 2))
            for p in extra:
                v = tk.BooleanVar(value=p in when)
                self.vars[p] = v
                if p in cal.events:
                    text = "%s  (%s)" % (p, ce.window_text(cal.events[p]))
                else:
                    # translators: %s is the name of a period, a kind of event
                    text = _("%s  (a period)") % p
                ttk.Checkbutton(self.more_box, text=text, variable=v).pack(anchor="w")
        ttk.Label(self.more_box, text=_("New events are made in the advanced editor."),
                  foreground=cf.GREY).pack(anchor="w", pady=(2, 0))
        if cal.spells:
            ttk.Label(self.more_box, text=_("Also on during these spells"),
                      style="Head.TLabel").pack(anchor="w", pady=(10, 2))
            for p in sorted(cal.spells, key=str.casefold):
                v = tk.BooleanVar(value=p in when)
                self.vars[p] = v
                ttk.Checkbutton(self.more_box, text="%s  (%s)" % (
                    p, cf.spell_words(cal, cal.spells[p])), variable=v).pack(anchor="w")
        ttk.Label(self.more_box, text=_("And on these kinds of weather at %s")
                  % (cal.place or ce.DEFAULT_PLACE)["name"],
                  style="Head.TLabel").pack(anchor="w", pady=(10, 2))
        for p in season.WEATHER_NAMES:
            v = tk.BooleanVar(value=p in when)
            self.vars[p] = v
            ttk.Checkbutton(self.more_box, text="%s: %s" % (p, cf.WEATHER_TEXT[p]),
                            variable=v).pack(anchor="w")
        self.above_choices = [(None, _("picked for you, from the files they share"))]
        if name:
            for other, n in ce.overlaps(guide.inst, name):
                self.above_choices.append((other, ngettext(
                    "%(mod)s  (%(n)d shared file)", "%(mod)s  (%(n)d shared files)", n)
                    % {"mod": other, "n": n}))
        now = entry["above"] if entry else None
        if now and now not in [c[0] for c in self.above_choices]:
            self.above_choices.append((now, now))
        ttk.Label(self.more_box, text=_("Wins over"), style="Head.TLabel").pack(anchor="w",
                                                                              pady=(10, 2))
        self.above = ttk.Combobox(self.more_box, state="readonly", width=60,
                                  values=[c[1] for c in self.above_choices])
        pick = [i for i, c in enumerate(self.above_choices) if c[0] == now]
        self.above.current(pick[0] if pick and name in cal.toggle else 0)
        self.above.pack(anchor="w")
        ttk.Label(self.more_box, text=_("Where two mods have the same file, MO2 uses the one "
                                        "that wins. play.bat keeps this one just below the mod "
                                        "it wins over in MO2's list."), foreground=cf.GREY,
                  wraplength=520, justify="left").pack(anchor="w", pady=(2, 0))
        self.show_more()
        cf.button_row(f, (_("OK"), self.ok), (_("Cancel"), win.destroy))
        win.bind("<Return>", lambda e: self.ok())
        cf.present(win, guide.root, focus)

    def fill(self):
        q = self.query.get().strip().lower()
        self.shown = [n for n in self.names if q in n.lower()]
        self.list.delete(0, "end")
        for n in self.shown:
            self.list.insert("end", n)

    def show_more(self):
        if self.more.get():
            self.more_box.pack(anchor="w", fill="x")
        else:
            self.more_box.pack_forget()

    def ok(self):
        from tkinter import messagebox
        g, cal = self.g, self.g.cal
        name = self.name
        if name is None:
            sel = self.list.curselection()
            if not sel:
                messagebox.showerror(self.win.title(), _("Pick the mod in the list."),
                                     parent=self.win)
                return
            name = self.shown[sel[0]]
        when = [p for p, v in self.vars.items() if v.get()]
        if not when:
            messagebox.showerror(self.win.title(), _("Check at least one season."),
                                 parent=self.win)
            return
        above = self.above_choices[self.above.current()][0]
        if above is None:
            above = settle(g, name, when, parent=self.win)
            if above is None:
                return
        if ce.loops(cal.toggle, name, above):
            messagebox.showerror(self.win.title(), _("%s already wins over this mod, so this "
                                                     "one can't win over it as well.") % above,
                                 parent=self.win)
            return
        cal.put(name, when, above)
        g.kept.pop(name, None)
        self.win.destroy()
        g.render()


def season_grid(tk, ttk, grid, cal, when, into):
    """A checkbox for each season, two to a row with its dates beside it, then one for each
    of the player's own seasons; their variables go in `into`, by name."""
    wins = ce.season_windows(cal.dates)
    off = _("off in your calendar")
    rows = ([(s, cf.title(s, cal), wins.get(s, off)) for s in season.SEASONS]
            + [(o, o, ce.window_text(cal.own[o])) for o in cal.own_order()])
    for i, (key, text, dates) in enumerate(rows):
        v = tk.BooleanVar(value=key in when)
        into[key] = v
        ttk.Checkbutton(grid, text=text, variable=v).grid(
            row=i // 2, column=(i % 2) * 2, sticky="w", pady=1)
        ttk.Label(grid, text=dates, foreground=cf.GREY).grid(
            row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(8, 24))


def archives():
    """mod_install, or None for a _tools from before it."""
    try:
        import mod_install
        return mod_install
    except ImportError:
        return None


def ask_winner(guide, name, other, n, seasons, parent=None):
    """Two seasonal mods on at once share files: whose should the game use? True for
    `name`'s, False for `other`'s, None when the player backs out."""
    tk, ttk = guide.tk, guide.ttk
    win, f = cf.dialog(parent or guide.root, _("Which one wins?"))
    # translators: %(seasons)s is the seasons both mods are on in, like "winter, deep winter"
    guide.para(ngettext("%(mod)s and %(other)s are both on in %(seasons)s, and ship %(n)d of "
                        "the same file. Whose should the game use while both are on?",
                        "%(mod)s and %(other)s are both on in %(seasons)s, and ship %(n)d of "
                        "the same files. Whose should the game use while both are on?", n)
               % {"mod": name, "other": other, "seasons": seasons, "n": n},
               parent=f, wrap=520)
    pick = tk.StringVar(value="mine")
    # translators: whose files the game uses, by the mod's name: Winter Pack's
    ttk.Radiobutton(f, text=_("%s's") % name, value="mine", variable=pick).pack(
        anchor="w", pady=(10, 0))
    guide.para(_("Right for a recolor, a fix or an add-on made for the other one."), parent=f,
               color=cf.GREY, pad=(0, 0), indent=24, wrap=520)
    ttk.Radiobutton(f, text=_("%s's") % other, value="theirs", variable=pick).pack(
        anchor="w", pady=(6, 0))
    said = {}

    def ok():
        said["pick"] = pick.get()
        win.destroy()

    cf.button_row(f, (_("OK"), ok), (_("Cancel"), win.destroy))
    win.bind("<Return>", lambda e: ok())
    cf.present(win, parent or guide.root)
    (parent or guide.root).wait_window(win)
    if parent is not None and parent.winfo_exists():
        parent.grab_set()                   # the dialog it was asked from holds input again
    return None if "pick" not in said else said["pick"] == "mine"


def settle(guide, name, when, parent=None):
    """The mod `name` wins over, when it is on in `when`: the one the files they share
    pick, except that for each other seasonal mod on at the same time with files in common
    the player says which one wins. Returns it, or None when the player backs out. Setting
    another mod to win moves that mod, not this one."""
    cal, inst = guide.cal, guide.inst
    auto = ce.anchor_for(inst, name, when, cal.toggle, cal)
    above, rivals = auto[0] or "", auto[2]
    beat = []
    for other, n, both in rivals:
        c = cal.toggle[other]
        if c["above"] == name:
            continue                        # already set to win over this one
        if name in cal.toggle and cal.toggle[name]["above"] == other:
            beat.append(other)              # already set to lose to this one
            continue
        mine = ask_winner(guide, name, other, n, cf.when_text(both, cal), parent)
        if mine is None:
            return None
        if mine:
            beat.append(other)
        elif not ce.loops(cal.toggle, other, name):
            cal.put(other, c["when"], name)
    if beat:
        # just above the one that is highest in MO2's list, it wins over all of them
        order = {m: i for i, m in enumerate(inst.names)}
        above = min(beat, key=lambda m: order.get(m, len(order)))
    return above


class InstallDialog(object):
    """Install a mod from its archive and make it seasonal, in one go: its installer's
    options as checkboxes, a fix file from its author, its seasons. The archive is read
    in the background; installing shows how far it has got."""

    def __init__(self, guide, archive):
        mi = archives()
        self.g, self.mi, self.archive = guide, mi, archive
        self.pkg, self.win = None, None
        # a big solid archive takes a second or more to read its installer from
        guide.root.configure(cursor="watch")
        guide.in_background(lambda: mi.Package(archive), self.read)

    def read(self, pkg, error):
        from tkinter import messagebox
        g = self.g
        g.root.configure(cursor="")
        if error is not None:
            if isinstance(error, self.mi.ArchiveError):
                text = str(error)
            else:
                # translators: %(error)s is what went wrong, as the system says it
                text = _("%(archive)s can't be read: %(error)s") % {
                    "archive": os.path.basename(self.archive), "error": error}
            messagebox.showerror(pgettext("dialog title", "Install"), text, parent=g.root)
            return
        if pkg.problem:
            messagebox.showinfo(pgettext("dialog title", "Install"), "%s\n\n%s" % (
                os.path.basename(self.archive), pkg.problem), parent=g.root)
            return
        self.pkg = pkg
        self.build()

    def build(self):
        g, pkg = self.g, self.pkg
        tk, ttk = g.tk, g.ttk
        # translators: %s is the archive's file name
        win, f = cf.dialog(g.root, _("Install %s") % os.path.basename(self.archive))
        self.win = win
        row = ttk.Frame(f)
        row.pack(fill="x")
        # translators: followed by a box with the name of the mod's folder
        ttk.Label(row, text=_("Install it as")).pack(side="left")
        self.name = tk.StringVar(value=pkg.name)
        ttk.Entry(row, textvariable=self.name, width=72).pack(side="left", padx=(8, 0))
        if pkg.about:
            g.para(pkg.about, parent=f, color=cf.GREY, wrap=620)
        self.chosen = {}
        if pkg.fomod:
            chosen = pkg.fomod.default()
            for step in pkg.fomod.steps:
                for group in step["groups"]:
                    plugins = [p for p in group["plugins"] if p["files"]]
                    if not plugins:
                        continue
                    ttk.Label(f, text=group["name"], style="Head.TLabel").pack(
                        anchor="w", pady=(12, 2))
                    one = group["type"] in ("SelectExactlyOne", "SelectAtMostOne")
                    radio = tk.StringVar(value=next((p["id"] for p in plugins
                                                     if p["id"] in chosen), ""))
                    for p in plugins:
                        if one:
                            ttk.Radiobutton(f, text=p["name"], value=p["id"],
                                            variable=radio).pack(anchor="w")
                            self.chosen[p["id"]] = (radio, p["id"])
                        else:
                            v = tk.BooleanVar(value=p["id"] in chosen)
                            ttk.Checkbutton(f, text=p["name"], variable=v,
                                            state="disabled" if p["type"] == "NotUsable"
                                            else "normal").pack(anchor="w")
                            self.chosen[p["id"]] = (v, None)
                        if p["description"]:
                            g.para(p["description"], parent=f, color=cf.GREY, pad=(0, 0),
                                   indent=24, wrap=620)
        ttk.Label(f, text=_("Fix files from the author"), style="Head.TLabel").pack(
            anchor="w", pady=(12, 2))
        self.extra = []
        self.extra_box = ttk.Frame(f)
        self.extra_box.pack(anchor="w", fill="x")
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=(2, 0))
        g.button(row, _("Add a file..."), self.add_extra, pad=0)
        ttk.Label(row, text=_("a file the author says to drop into the mod; it goes where the "
                              "mod has a file of that name"), foreground=cf.GREY).pack(
            side="left", padx=(10, 0))
        ttk.Label(f, text=_("On in these seasons"), style="Head.TLabel").pack(anchor="w",
                                                                              pady=(12, 2))
        guess = set(self.mi.seasons_in(pkg.name) or self.mi.seasons_in(
            os.path.basename(self.archive)))
        grid = ttk.Frame(f)
        grid.pack(anchor="w")
        self.seasons = {}
        season_grid(tk, ttk, grid, g.cal, guess, self.seasons)
        self.bar = ttk.Progressbar(f, mode="determinate", length=560)
        self.msg = ttk.Label(f, text="", foreground=cf.GREY, wraplength=620, justify="left")
        self.msg.pack(anchor="w", pady=(12, 0))
        self.buttons = cf.button_row(f, (_("Install"), self.go), (_("Cancel"), win.destroy))
        self.show_size()
        win.bind("<Return>", lambda e: self.go())
        cf.present(win, g.root)

    def choice(self):
        """The installer options checked, as plugin ids."""
        out = set()
        for pid, (var, value) in self.chosen.items():
            if value is None and var.get():
                out.add(pid)
            elif value is not None and var.get() == value:
                out.add(pid)
        return out if self.pkg.fomod else None

    def show_size(self):
        size = self.pkg.size(self.choice())
        # translators: %(size)s is like "12 MB"; %(folder)s is the folder it goes in
        self.msg.configure(text=_("About %(size)s, into %(folder)s.") % {
            "size": megabytes(size), "folder": "mods\\" + (self.name.get().strip() or "?")},
            foreground=cf.GREY)

    def add_extra(self):
        from tkinter import filedialog, messagebox
        path = filedialog.askopenfilename(parent=self.win, title=_("A fix file from the author"),
                                          initialdir=os.path.dirname(self.archive))
        if not path:
            return
        dests = [d for __, d in self.pkg.files(self.choice())]
        dest = self.mi.place(path, dests)
        if not dest:
            messagebox.showerror(pgettext("dialog title", "Install"), _(
                "This install has no file called %s, or more than one, so there's no telling "
                "where it goes. Check the options above, or put it in the mod by hand after.")
                % os.path.basename(path), parent=self.win)
            return
        self.extra = [(p, d) for p, d in self.extra if d != dest] + [(path, dest)]
        for w in self.extra_box.winfo_children():
            w.destroy()
        for p, d in self.extra:
            # translators: a fix file's name, and where in the mod it goes
            self.g.ttk.Label(self.extra_box, text=_("%(file)s  goes to  %(dest)s") % {
                "file": os.path.basename(p), "dest": d.replace("/", "\\")}).pack(anchor="w")

    def go(self):
        from tkinter import messagebox
        g = self.g
        name = self.name.get().strip()
        when = [s for s, v in self.seasons.items() if v.get()]
        problems = self.pkg.fomod.problems(self.choice()) if self.pkg.fomod else []
        if not when:
            problems.append(_("Check at least one season."))
        if problems:
            messagebox.showerror(pgettext("dialog title", "Install"), "\n".join(problems),
                                 parent=self.win)
            return
        for b in self.buttons:
            b.configure(state="disabled")
        self.bar.pack(anchor="w", pady=(10, 0), before=self.msg)
        self.msg.configure(text=_("Installing..."), foreground=cf.GREY)
        state = {"done": 0, "total": self.pkg.size(self.choice()) or 1}

        def progress(done, total):
            state["done"], state["total"] = done, total or 1

        def tick():
            if not self.win.winfo_exists():
                return
            self.bar.configure(maximum=state["total"], value=state["done"])
            if "over" not in state:
                self.win.after(200, tick)

        def done(folder, error):
            state["over"] = True
            if error is not None:
                for b in self.buttons:
                    b.configure(state="normal")
                self.bar.pack_forget()
                self.msg.configure(text=str(error), foreground=cf.RED)
                return
            self.win.destroy()
            self.adopt(name, when)

        choice = self.choice()
        g.in_background(lambda: self.mi.install(self.pkg, name, choice, self.extra, progress),
                        done)
        tick()

    def adopt(self, name, when):
        """The mod is in place: make it seasonal, asking which mod wins where it overlaps
        another seasonal mod on at the same time."""
        g = self.g
        above = settle(g, name, when)
        if above is None:
            above = ce.anchor_for(g.inst, name, when, g.cal.toggle)[0] or ""
        g.cal.put(name, when, above)
        g.kept.pop(name, None)
        g.render()


def megabytes(n):
    return _("%.1f GB") % (n / 1e9) if n >= 1e9 else _("%d MB") % max(1, round(n / 1e6))
