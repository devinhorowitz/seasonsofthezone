"""Putting the tools where they run, and the game entry play.bat starts.

The tools run from the GAMMA folder, next to ModOrganizer.exe, but they arrive inside the
mod's own folder, where MO2 installs the zip. configure.bat opened from there installs
them - or updates them - and then carries on in the GAMMA folder's copy.

An install copies the tools, their presets, play.bat and configure.bat two levels up, each
only when its bytes differ, and deletes nothing: seasons_config.py, its backups and the
presets the player saved stay as they are, and play.bat keeps the entry it started. Older
tools go over newer ones only when the player says so.

play.bat starts the game through one of MO2's executable entries, by its title; the
functions at the end read and set which one.
"""
import io
import json
import os
import re
import subprocess
import sys

from lang import _, ngettext, pgettext

HERE = os.path.dirname(os.path.abspath(__file__))
# the folder these tools came in: the mod's folder, or the GAMMA folder once installed
SOURCE = os.path.dirname(HERE)
MINE = "seasons_config.py"          # the player's own setup: never copied, never touched
PRESETS = os.path.join("_tools", "presets")
LANG = os.path.join("_tools", "lang")
VERSION_LINE = re.compile(r"""^VERSION\s*=\s*["'](\d+(?:\.\d+)*)["']""", re.M)


# --- installing the tools ------------------------------------------------------------------

def gamma_for(source):
    """The GAMMA folder for tools that came in `source`, the mod's folder: two levels up,
    mods\\<name>\\..\\.., where ModOrganizer.ini is. None when it isn't there."""
    gamma = os.path.dirname(os.path.dirname(source))
    return gamma if os.path.isfile(os.path.join(gamma, "ModOrganizer.ini")) else None


def version_of(season_py):
    """VERSION in a copy of season.py: "" for a copy from before there was one, None when
    there is no copy."""
    try:
        text = io.open(season_py, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    m = VERSION_LINE.search(text)
    return m.group(1) if m else ""


def newer(a, b):
    """Is version `a` newer than `b`? As numbers, so 1.10.0 is newer than 1.9.0; "" is older
    than any."""
    def key(v):
        return tuple(int(x) for x in v.split(".")) if v else ()
    return key(a) > key(b)


def files_of(source):
    """What an install copies, as paths relative to the folder they came in: the tools and
    the worked example, the presets, the translations, and the two batch files. Never
    seasons_config.py, nor the language picked in the window."""
    tools = os.path.join(source, "_tools")
    out = [os.path.join("_tools", f) for f in sorted(os.listdir(tools))
           if f.lower().endswith(".py") and f.lower() != MINE
           and os.path.isfile(os.path.join(tools, f))]
    presets = os.path.join(source, PRESETS)
    if os.path.isdir(presets):
        out += [os.path.join(PRESETS, f) for f in sorted(os.listdir(presets))
                if f.lower().endswith(".json") and os.path.isfile(os.path.join(presets, f))]
    words = os.path.join(source, LANG)
    if os.path.isdir(words):
        out += [os.path.join(LANG, f) for f in sorted(os.listdir(words))
                if f.lower().endswith((".po", ".pot"))
                and os.path.isfile(os.path.join(words, f))]
    return out + [f for f in ("configure.bat", "play.bat")
                  if os.path.isfile(os.path.join(source, f))]


def read(path):
    """A file's bytes, or None when there is none."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def saved_by_player(data):
    """Is this preset one the player saved, not one that came with the tools? One that
    can't be read counts as theirs."""
    try:
        return json.loads(data.decode("utf-8-sig")).get("shipped") is not True
    except (ValueError, AttributeError):
        return True


class Plan(object):
    """What an install would do, worked out before anything is written: each file new,
    updated or the same, by its bytes. play.bat is compared as it would be written, with
    the entry the GAMMA folder's copy starts. A preset the player saved under a name the
    tools now use is kept."""

    def __init__(self, source, gamma):
        self.source, self.gamma = source, gamma
        self.here = version_of(os.path.join(source, "_tools", "season.py"))
        self.there = version_of(os.path.join(gamma, "_tools", "season.py"))
        self.entry = None           # the entry play.bat started there, kept in the new one
        self.lost = None            # that entry, when a batch file can't hold its name
        self.files = []             # (path under either folder, bytes to write, state)
        for rel in files_of(source):
            data, old = read(os.path.join(source, rel)), read(os.path.join(gamma, rel))
            if rel == "play.bat" and old is not None:
                data = self.keep_entry(data, os.path.join(gamma, rel))
            if old is None:
                state = "new"
            elif old == data:
                state = "same"
            elif os.path.dirname(rel) == PRESETS and saved_by_player(old):
                state = "kept"
            else:
                state = "updated"
            self.files.append((rel, data, state))

    def keep_entry(self, data, old_bat):
        """The new play.bat's bytes, set to start the entry the old one started."""
        ours = read_shortcut(os.path.join(self.source, "play.bat"))
        was = read_shortcut(old_bat)
        if ours is None or was is None or was == ours:
            return data
        if shortcut_problem(was):
            self.lost = was
            return data
        self.entry = was
        return set_shortcut(data, was)

    def count(self, state):
        return sum(1 for f in self.files if f[2] == state)

    def todo(self):
        """The files to write: the new and the updated."""
        return [f for f in self.files if f[2] in ("new", "updated")]

    def update(self):
        """Were the tools there before?"""
        return any(f[2] != "new" for f in self.files)

    def downgrade(self):
        """Are the tools there newer than these?"""
        return bool(self.there) and self.here is not None and newer(self.there, self.here)

    def compared(self):
        """How the versions there and here compare, when the tools were there before:
        "same", "two" different ones, or "older" for a copy there from before there were
        versions. None for a first install."""
        if self.there is None or not self.here:
            return None
        if self.there == self.here:
            return "same"
        return "two" if self.there else "older"

    def values(self):
        """What the sentences about this install are filled in with."""
        return {"gamma": self.gamma, "there": self.there, "here": self.here}

    def counts(self):
        """"Files: 2 new, 5 updated, 17 the same.", leaving out what there is none of."""
        parts = []
        for state in ("new", "updated", "same", "kept"):
            n = self.count(state)
            if n:
                parts.append({"new": ngettext("%d new", "%d new", n),
                              "updated": ngettext("%d updated", "%d updated", n),
                              "same": ngettext("%d the same", "%d the same", n),
                              "kept": ngettext("%d of your presets kept",
                                               "%d of your presets kept", n)}[state] % n)
        comma = pgettext("between words in a list", ", ")
        # translators: %s is a list of counts of files: "2 new, 5 updated, 17 the same"
        return _("Files: %s.") % comma.join(parts)

    def entry_line(self):
        """What play.bat starts once installed, when that is the player's pick, or when
        their pick can't be kept. None otherwise."""
        if self.entry:
            return _('play.bat keeps starting "%s".') % self.entry
        if self.lost:
            return (_('play.bat starts "%(entry)s" from now on: the entry it started, '
                      '"%(old)s", has a character in its name that a batch file reads as '
                      'something else. Rename that entry in MO2, then pick it in the setup.')
                    % {"entry": read_shortcut(os.path.join(self.source, "play.bat")),
                       "old": self.lost})
        return None


def write(path, data):
    """Write a file whole or not at all: a temp file beside it, then a rename over it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def put(plan):
    """Write the new and updated files. Returns (the files written, None), or (those
    written before it stopped, what stopped it)."""
    done = []
    for rel, data, __ in plan.todo():
        try:
            write(os.path.join(plan.gamma, rel), data)
        except OSError as e:
            return done, _("Couldn't write %(file)s: %(error)s.") % {
                "file": rel, "error": (e.strerror or str(e)).rstrip(".")}
        done.append(rel)
    return done, None


def stopped(plan, done, error):
    """What to say when a file couldn't be written."""
    n = len(plan.todo())
    return [error, ngettext("%(done)d of the %(all)d files were copied; the rest are as they "
                            "were. Check that the file isn't read-only or open in another "
                            "program, then try again.",
                            "%(done)d of the %(all)d files were copied; the rest are as they "
                            "were. Check that the file isn't read-only or open in another "
                            "program, then try again.", n) % {"done": len(done), "all": n}]


def hand_off(gamma):
    """Open the setup from the GAMMA folder's copy of the tools, and leave it running.
    Through that folder's configure.bat, so a setup that stops with an error keeps the
    console open to read it; with this Python when there is no configure.bat. Returns its
    process."""
    bat = os.path.join(gamma, "configure.bat")
    if os.name == "nt" and os.path.isfile(bat):
        return subprocess.Popen(["cmd", "/c", bat], cwd=gamma)
    return subprocess.Popen([sys.executable, os.path.join(gamma, "_tools", "configure.py")],
                            cwd=gamma)


def say(*lines):
    for l in lines:
        print("  " + l if l else "")


def fail(*lines):
    say(*lines)
    raise SystemExit(1)


def state_word(state):
    """What an install does with a file, as the console lists it: new, updated, kept."""
    return {"new": pgettext("a file the install copies", "new"),
            "updated": pgettext("a file the install copies", "updated"),
            "kept": pgettext("a file the install leaves as it is", "kept")}.get(state, state)


def console(plan):
    """configure.py install --yes: the plan, then the result, in the console."""
    v = plan.values()
    if plan.downgrade():
        fail(_("The tools in your GAMMA folder, %(gamma)s, are newer than these: %(there)s "
               "there, %(here)s here.") % v,
             # translators: \n starts the next line in the console; put it where it suits
             *(_("Nothing was changed. To put these older ones there anyway, open "
                 "configure.bat\nin %s.") % plan.source).split("\n"))
    if not plan.todo():
        say(_("The tools in your GAMMA folder, %(gamma)s, are up to date (%(here)s).") % v
            if plan.here else
            _("The tools in your GAMMA folder, %s, are up to date.") % plan.gamma)
        return
    if plan.update():
        say({"same": _("Updating the tools in your GAMMA folder, %(gamma)s: %(here)s there "
                       "and here."),
             "two": _("Updating the tools in your GAMMA folder, %(gamma)s: %(there)s there, "
                      "%(here)s here."),
             "older": _("Updating the tools in your GAMMA folder, %(gamma)s: an older "
                        "version there, %(here)s here.")}.get(
            plan.compared(), _("Updating the tools in your GAMMA folder, %(gamma)s.")) % v)
    else:
        say(_("Installing the tools into your GAMMA folder, %s.") % plan.gamma)
    for rel, __, state in plan.files:
        if state == "kept":
            say("  %-8s %s" % (state_word(state), _("%s - yours, not the one that comes with "
                                                    "the tools") % rel))
        elif state != "same":
            say("  %-8s %s" % (state_word(state), rel))
    say(plan.counts())
    if plan.entry_line():
        say(plan.entry_line())
    done, error = put(plan)
    if error:
        fail(*stopped(plan, done, error))
    say(_("Done. Your settings there are kept.") if plan.update() else _("Done."),
        _("From now on, open configure.bat and play.bat in your GAMMA folder, %s.")
        % plan.gamma)


class Window(object):
    """The install in a small window, before the setup opens: what it copies where, then
    that it is done. `on` is set when the player goes on to the setup, and `error` holds
    what stopped an install."""

    def __init__(self, root, plan):
        import configure as cf
        from tkinter import ttk
        self.cf, self.ttk, self.plan = cf, ttk, plan
        self.on, self.error = False, None
        self.win, self.frame = cf.dialog(root, cf.TITLE, transient=False)
        if plan.todo():
            first = self.ask()
        else:
            first = self.page(_("Up to date"), [
                (_("The tools in your GAMMA folder, %s, are up to date. From now on, open "
                   "configure.bat and play.bat there.") % plan.gamma, None)],
                [(pgettext("button", "Continue"), self.go_on)])
        cf.present(self.win, root, first)
        self.win.lift()
        self.win.focus_force()

    def page(self, head, lines, buttons):
        """Fill the window: a heading, lines of (text, color), and buttons. Returns the
        first button, which Enter presses."""
        for w in self.frame.winfo_children():
            w.destroy()
        self.ttk.Label(self.frame, text=head, font=("TkDefaultFont", 11, "bold")).pack(
            anchor="w")
        for text, color in lines:
            self.ttk.Label(self.frame, text=text, foreground=color, justify="left",
                           wraplength=460).pack(anchor="w", pady=(8, 0))
        first = self.cf.button_row(self.frame, *buttons)[0]
        self.win.bind("<Return>", lambda e: first.invoke())
        first.focus_set()
        return first

    def ask(self):
        p, cf = self.plan, self.cf
        v = p.values()
        lines = [((_("It puts play.bat, configure.bat and the _tools folder in your GAMMA "
                     "folder, %s, where they run from. Your settings there are kept.")
                   if p.update() else
                   _("It puts play.bat, configure.bat and the _tools folder in your GAMMA "
                     "folder, %s, where they run from.")) % p.gamma, None)]
        how = p.compared()
        if how and p.downgrade():
            lines.append((_("%(there)s there, %(here)s here: the tools there are newer.") % v,
                          cf.RED))
        elif how:
            lines.append(({"same": _("%(here)s there and here."),
                           "two": _("%(there)s there, %(here)s here."),
                           "older": _("An older version there, %(here)s here.")}[how] % v,
                          cf.GREY))
        lines.append((p.counts(), cf.GREY))
        if p.entry_line():
            lines.append((p.entry_line(), cf.RED if p.lost else cf.GREY))
        return self.page(_("Update the tools") if p.update() else _("Install the tools"),
                         lines, [(pgettext("button", "Install"), self.install),
                                 (pgettext("button", "Cancel"), self.win.destroy)])

    def install(self):
        from tkinter import messagebox
        p = self.plan
        if p.downgrade() and not messagebox.askyesno(
                self.cf.TITLE, _("The tools in your GAMMA folder are newer than these: "
                                 "%(there)s there, %(here)s here. Put these older ones in "
                                 "their place?") % p.values(), icon="warning",
                default="no", parent=self.win):
            return
        done, error = put(p)
        if error:
            self.error = stopped(p, done, error)
            self.page(_("Not finished"), [(self.error[0], self.cf.RED), (self.error[1], None)],
                      [(pgettext("button", "Close"), self.win.destroy)])
            return
        self.page(_("Done"), [(_("From now on, open configure.bat and play.bat in your GAMMA "
                                 "folder, %s.") % p.gamma, None)],
                  [(pgettext("button", "Continue"), self.go_on)])

    def go_on(self):
        self.on = True
        self.win.destroy()


def window(plan):
    """The install in a window. True when the player goes on to the setup."""
    try:
        import tkinter as tk
    except ImportError:
        import season
        fail(_("The window needs tkinter, which this Python does not have. Reinstall Python "
               "from python.org with \"tcl/tk and IDLE\" checked. Until then, this command "
               "installs the tools without the window, typed in %s:") % plan.source,
             "  " + season.command("configure.py", "install --yes"))
    root = tk.Tk()
    root.withdraw()
    w = Window(root, plan)
    root.wait_window(w.win)
    root.destroy()
    if w.error:
        fail(*w.error)
    return w.on


def main(a):
    """configure.py install: put the tools in the GAMMA folder, or update them there. With
    --yes in the console; otherwise in a window that then goes on to the setup."""
    yes = getattr(a, "yes", False)
    if os.path.isfile(os.path.join(SOURCE, "ModOrganizer.ini")):
        say(_("The tools already run from your GAMMA folder, %s.") % SOURCE)
        if not yes:
            hand_off(SOURCE)
        return
    gamma = gamma_for(SOURCE)
    if not gamma:
        # translators: three lines, their labels lined up; ModOrganizer.ini is a file's name
        where = _("this copy : %(copy)s\n"
                  "looked in : %(parent)s, two folders up\n"
                  "expected  : ModOrganizer.ini   MISSING") % {
            "copy": SOURCE, "parent": os.path.dirname(os.path.dirname(SOURCE))}
        # translators: \n starts the next line in the console; put them where they suit
        how = _("The tools install from the mod's folder, where MO2 installs the zip:\n"
                "mods\\<name> in your GAMMA folder. Install the zip with MO2, right-click the "
                "mod\nthere and choose Open in Explorer, then open configure.bat.")
        fail(*([_("No GAMMA folder to put the tools in."), ""]
               + ["  " + l for l in where.split("\n")] + [""] + how.split("\n")
               + [_("Nothing has been changed.")]))
    try:
        plan = Plan(SOURCE, gamma)
    except OSError as e:
        fail(_("Couldn't read %(file)s: %(error)s. Nothing has been changed.")
             % {"file": e.filename, "error": (e.strerror or str(e)).rstrip(".")})
    if yes:
        console(plan)
    elif window(plan):
        hand_off(gamma)


# --- the entry play.bat starts -------------------------------------------------------------

SHORTCUT_LINE = re.compile(r'^(\s*set\s+"SHORTCUT=)([^"]*)(".*)$', re.I)
# what a title can't hold once it is in a batch file's set "..." line
UNSAFE = re.compile(r'["%^&|<>\r\n]|[^\x20-\x7e]')


def mo2_entries(gamma):
    """The titles in MO2's executable dropdown, in its order. [] when there are none, or no
    ModOrganizer.ini to read them from."""
    titles, here = [], False
    try:
        lines = io.open(os.path.join(gamma, "ModOrganizer.ini"), encoding="utf-8",
                        errors="replace").read().splitlines()
    except OSError:
        return []
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            here = s == "[customExecutables]"
            continue
        m = re.match(r"^(\d+)\\title=(.*)$", s)
        if here and m:
            titles.append((int(m.group(1)), m.group(2).strip()))
    return [t for _, t in sorted(titles)]


def read_shortcut(play_bat):
    """The MO2 entry play.bat starts, or None when it has no SHORTCUT line to read."""
    try:
        text = io.open(play_bat, encoding="cp1252", errors="replace").read()
    except OSError:
        return None
    for line in text.splitlines():
        m = SHORTCUT_LINE.match(line)
        if m:
            return m.group(2)
    return None


def shortcut_problem(title):
    """Why play.bat can't be set to start `title`, or None."""
    if not title or not title.strip():
        return _("Pick the entry play.bat should start.")
    if UNSAFE.search(title):
        return (_("play.bat can't hold the name \"%s\": it has a character a batch file reads "
                  "as something else. Rename that entry in MO2, then pick it here.") % title)
    return None


def set_shortcut(raw, title):
    """play.bat's bytes `raw` with its SHORTCUT set to `title`, line ends as they were.
    Raises ValueError when it has no SHORTCUT line."""
    nl = b"\r\n" if b"\r\n" in raw else b"\n"
    lines = raw.decode("cp1252").split(nl.decode())
    for i, line in enumerate(lines):
        m = SHORTCUT_LINE.match(line)
        if m:
            lines[i] = m.group(1) + title + m.group(3)
            return nl.decode().join(lines).encode("cp1252")
    raise ValueError(_("play.bat has no SHORTCUT line to set."))


def write_shortcut(play_bat, title):
    """Set the MO2 entry play.bat starts. Returns True when the file changed. Raises
    ValueError for a title a batch file can't hold, OSError when play.bat can't be
    written."""
    bad = shortcut_problem(title)
    if bad:
        raise ValueError(bad)
    raw = io.open(play_bat, "rb").read()
    new = set_shortcut(raw, title)
    if new == raw:
        return False
    tmp = play_bat + ".tmp"
    with open(tmp, "wb") as f:
        f.write(new)
    os.replace(tmp, play_bat)
    return True
