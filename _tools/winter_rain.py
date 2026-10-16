"""No Rain in Winter: the installed weathers, with their rain taken out, for the winters.

The snowfall layer (patches/apply_seasonal_snowfall.py) plays snow on the rain and storm
weathers, but the weather's own rain falls with it: a weather file's rain_density is what
makes the engine draw rain, play its sound and wet the ground, and no script can change it.
So this builds a mod of copies of every installed weather that rains, each with every
rain_density set to 0 and nothing else changed, and the calendar turns it on in the winters.

DLTX can't do it: the game loads every .ltx in the weathers folder as a weather of its own
(CEnvironment::load_weathers), so a mod_*.ltx there would be loaded as a broken weather.

Each copy names the mod it was made from and that copy's SHA-256 on its first line, so a
copy whose source has changed since can be told apart; play.bat makes the mod again then.

Each zeroed line keeps the rain it had on the next line, as sotz_rain_density, which the
engine never reads (CEnvDescriptor::load reads its keys by name). The game's gameplay
scripts that go by rain (NPC sight in a storm, weapons jamming, campfires, the AI taking
cover) read it back through Seasons of the Zone, while rain's sound and drops stay off.
FORMAT is on the first line too: a copy of an older format reads as changed, and is made
again.
"""
import hashlib
import io
import os
import re

MOD = "No Rain in Winter (seasonal)"
WHEN = ("winter", "winter_snow")
WEATHERS = ("gamedata", "configs", "environment", "weathers")
MARK = "; Seasons of the Zone: "
FORMAT = 2
HEAD = re.compile(r'^; Seasons of the Zone: rain off for the winters, from "(.+)", sha256 '
                  r'([0-9a-f]{64})(?:, format (\d+))?\.')
RAIN = re.compile(r"^([ \t]*rain_density[ \t]*=[ \t]*)([^;\r\n]*?)([ \t]*(?:;.*)?)$")
KEPT = "sotz_rain_density"

META = (
    "[General]\n"
    "modid=0\n"
    "version=1.0.0\n"
    "newestVersion=\n"
    "category=0\n"
    "installationFile=\n"
    "comments=Made by Seasons of the Zone: the installed weathers that rain, with no rain, "
    "for the winters.\n"
    "notes=Made by configure.py rain --build from the weathers that win in MO2, and made "
    "again by play.bat when one of them changes. Don't edit it: the next build replaces it.\n")


def _nl(raw):
    return "\r\n" if "\r\n" in raw else "\n"


OVERWRITE = "overwrite"


def weather_files(mods, order):
    """{file name lower case: (mod, path)}: the copy of each weather that MO2 gives the game.
    MO2's overwrite folder (beside mods/) comes first, then the enabled mods in `order`,
    highest priority first; this mod is left out."""
    out = {}
    layers = [(OVERWRITE, os.path.join(os.path.dirname(mods), OVERWRITE, *WEATHERS))]
    layers += [(name, os.path.join(mods, name, *WEATHERS)) for name, on in order
               if on and name != MOD]
    for name, d in layers:
        try:
            files = os.listdir(d)
        except OSError:
            continue
        for f in files:
            low = f.lower()
            if low.endswith(".ltx") and low not in out and os.path.isfile(os.path.join(d, f)):
                out[low] = (name, os.path.join(d, f))
    return out


def _value(v):
    try:
        return float(v.strip())
    except ValueError:
        return None


def rains(text):
    """Does a weather file rain at any hour?"""
    for line in text.splitlines():
        m = RAIN.match(line)
        if m and (_value(m.group(2)) or 0) > 0:
            return True
    return False


def _kept_key(prefix):
    """A rain_density line's start with the key renamed to KEPT, its '=' left in the same
    column when the spaces before it allow."""
    m = re.match(r"^([ \t]*)rain_density( *)(=.*)$", prefix)
    pad = len(KEPT) - len("rain_density")
    if m and len(m.group(2)) > pad:
        return m.group(1) + KEPT + m.group(2)[pad:] + m.group(3)
    return prefix.replace("rain_density", KEPT, 1)


def dry(text):
    """The weather with every rain_density set to 0 and the rain it had kept on the next
    line as KEPT, every other character as it was, and the count of lines changed."""
    nl = _nl(text)
    out, n = [], 0
    for line in text.split(nl):
        m = RAIN.match(line)
        if m and _value(m.group(2)) not in (None, 0.0):
            out.append(m.group(1) + "0" + m.group(3))
            out.append(_kept_key(m.group(1)) + m.group(2).strip())
            n += 1
            continue
        out.append(line)
    return nl.join(out), n


def head_line(mod, digest):
    return (MARK + 'rain off for the winters, from "%s", sha256 %s, format %d. Made by '
            'configure.py rain --build; play.bat makes it again when that copy changes.'
            % (mod, digest, FORMAT))


def _read(path):
    raw = open(path, "rb").read()
    return raw, raw.decode("latin-1")


def wanted(mods, order):
    """{file name: (mod, path, sha256)} for every winning weather that rains."""
    out = {}
    for low, (mod, path) in sorted(weather_files(mods, order).items()):
        raw, text = _read(path)
        if rains(text):
            out[low] = (mod, path, hashlib.sha256(raw).hexdigest())
    return out


def made(mods):
    """{file name lower case: (mod, sha256, file name, format)} for the copies in this mod
    now, as their first lines say (a line without a format is format 1); a file without
    that line is not one of ours and is left out."""
    d = os.path.join(mods, MOD, *WEATHERS)
    out = {}
    try:
        files = os.listdir(d)
    except OSError:
        return out
    for f in files:
        try:
            first = io.open(os.path.join(d, f), encoding="latin-1").readline()
        except OSError:
            continue
        m = HEAD.match(first)
        if m:
            out[f.lower()] = (m.group(1), m.group(2), f, int(m.group(3) or 1))
    return out


def stale(mods, order):
    """What a build would change: (new, changed, gone), lists of file names. All empty when
    the mod is current. A copy of an older FORMAT counts as changed."""
    want, have = wanted(mods, order), made(mods)
    new = sorted(f for f in want if f not in have)
    changed = sorted(f for f in want if f in have and (
        have[f][:2] != (want[f][0], want[f][2]) or have[f][3] != FORMAT))
    gone = sorted(f for f in have if f not in want)
    return new, changed, gone


def build(mods, order):
    """Make the mod from the weathers that win now. Returns {mod: [file names]} of what it
    was made from, and the number of rain lines turned off. Copies of weathers that no
    longer rain, or are no longer there, are taken out."""
    folder = os.path.join(mods, MOD)
    d = os.path.join(folder, *WEATHERS)
    os.makedirs(d, exist_ok=True)
    want = wanted(mods, order)
    for low, (_, _, f, _) in made(mods).items():
        if low not in want:
            os.remove(os.path.join(d, f))
    sources, lines = {}, 0
    for low, (mod, path, digest) in sorted(want.items()):
        raw, text = _read(path)
        body, n = dry(text)
        lines += n
        out = (head_line(mod, digest) + _nl(text) + body).encode("latin-1")
        target = os.path.join(d, os.path.basename(path))
        if not (os.path.isfile(target) and open(target, "rb").read() == out):
            with open(target, "wb") as fh:
                fh.write(out)
        sources.setdefault(mod, []).append(os.path.basename(path))
    meta = os.path.join(folder, "meta.ini")
    if not os.path.isfile(meta):
        with io.open(meta, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(META)
    return sources, lines


def anchor(mods, order, files):
    """The enabled mod this one has to win over: the highest that ships any of `files`."""
    for name, on in order:
        if on and name != MOD:
            d = os.path.join(mods, name, *WEATHERS)
            if any(os.path.isfile(os.path.join(d, f)) for f in files):
                return name
    return None
