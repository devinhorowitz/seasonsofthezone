"""Every MCM label the mod builds must have a string, or MCM shows the raw key.

The key MCM looks up is built, not written down, so a wrong one looks right in the
script: a list entry's label is "<option path>_lst_" .. its second field, which makes that
field a suffix. The units list gave it a full string id there and the dropdown read
"seasons_zone_main_units_lst_ui_mcm_seasons_zone_units_f" for two releases. This reads
the shipped MCM script, builds every key the way ui_mcm.script does, and looks each one up
in the shipped strings.

  python _tools/test_mcm_strings.py
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GD = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata")
MCM = os.path.join(GD, "scripts", "zzz_seasons_of_the_zone_mcm.script")
XML = os.path.join(GD, "configs", "text", "eng", "ui_seasons_of_the_zone.xml")

# widgets MCM draws without a label of their own
UNLABELLED = {"desc", "line", "image", "slide", "title"}


def calls(src):
    """(page, table text) for every add({...}) with a literal id, and its page function."""
    pages = [(m.start(), m.group(1)) for m in
             re.finditer(r"local function page_(\w+)\(", src)]
    for m in re.finditer(r"add\(\{", src):
        i, depth = m.end() - 1, 0
        for j in range(i, len(src)):
            depth += {"{": 1, "}": -1}.get(src[j], 0)
            if depth == 0:
                break
        body = src[i:j + 1]
        page = None
        for pos, name in pages:
            if pos < m.start():
                page = name
        # a literal id only: "mod_" .. m.key is a runtime tick, labeled by the file
        # season.py generates
        if re.match(r'\{\s*id\s*=\s*"[^"]+"\s*,', body):
            yield page, body


def keys(src):
    """(key, what) for every string the MCM pages look up."""
    out = []
    for page, body in calls(src):
        oid = re.match(r'\{\s*id\s*=\s*"([^"]+)"', body).group(1)
        kind = re.search(r'type\s*=\s*"([^"]+)"', body).group(1)
        if kind in UNLABELLED:
            continue
        hint = re.search(r'hint\s*=\s*"([^"]+)"', body)
        out.append(("ui_mcm_" + (hint.group(1) if hint else "seasons_zone_" + oid),
                    "label of %s" % oid))
        if kind == "list" and "no_str = true" not in body:
            # only the main page has lists with strings; a season page's path would
            # carry the season, which this cannot know
            assert page == "main", "a string list on page_%s - extend this test" % page
            for value, label in re.findall(r'\{\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\}', body):
                out.append(("seasons_zone_main_%s_lst_%s" % (oid, label),
                            "%s entry %r" % (oid, value)))
    for s in re.findall(r'"([a-z_]+)"', re.search(
            r"for _, s in ipairs\(\{([^}]*)\}\)", src).group(1)):
        out.append(("ui_mcm_seasons_zone_page_" + s, "page title %s" % s))
    out.append(("ui_mcm_seasons_zone_page_main", "page title main"))
    return out


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def read(p):
    return io.open(p, encoding="utf-8").read()


@case
def t_every_label_has_a_string():
    have = set(re.findall(r'<string id="([^"]+)"', read(XML)))
    want = keys(read(MCM))
    lists = [k for k, what in want if "_lst_" in k]
    assert len(lists) >= 9, "found only %d list entries - the parse is broken" % len(lists)
    missing = ["%s (%s)" % (k, what) for k, what in want if k not in have]
    assert not missing, "no string for: " + "; ".join(missing)
    return "%d keys, %d of them list entries, all in the strings" % (len(want), len(lists))


@case
def t_a_full_id_as_a_label_is_caught():
    """The 1.8.2 units list, rebuilt here: the check has to flag it."""
    bad = read(MCM).replace('{"fahrenheit", "fahrenheit"}',
                            '{"fahrenheit", "ui_mcm_seasons_zone_units_f"}')
    assert bad != read(MCM), "the units list has changed shape - update this case"
    have = set(re.findall(r'<string id="([^"]+)"', read(XML)))
    missing = [k for k, _ in keys(bad) if k not in have]
    assert missing == ["seasons_zone_main_units_lst_ui_mcm_seasons_zone_units_f"], missing
    return "the old units key is reported"


if __name__ == "__main__":
    print("  checking the MCM strings")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-34s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-34s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-34s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
