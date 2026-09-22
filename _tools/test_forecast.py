"""Run the SHIPPED zzz_seasons_of_the_zone.script under a real Lua runtime.

Not a re-implementation: the actual file is loaded into a sandbox whose globals are
stubs for the X-Ray bindings it expects, then calendar_page() is called for real. If the
forecast logic is wrong, these assertions fail.

Every case below has a negative control - a standing or a manager state that MUST NOT
produce the tier under test - so a function that returned a constant would be caught.
"""
import io, sys
from lupa import LuaRuntime

import os
SRC = (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
       "mods", "Seasons of the Zone", "gamedata", "scripts",
       "zzz_seasons_of_the_zone.script"))

HOUR = 3600


def build(standing, surge_left, psi_left, freq=24, psi_freq=48, forecast_on=True,
          coarse=200, exact=700, have_surge=True, have_psi=True):
    """A sandbox with the engine bindings the script reaches for."""
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()

    # In game, mgr.last_surge_time is a CTime and diffSec(that) returns how long ago it
    # was. Model it as a table carrying its own elapsed value, which is what the real
    # call reduces to: elapsed = period - remaining.
    def stamp(elapsed):
        return lua.table_from({"elapsed": elapsed})

    g.printf = lambda *a: None
    g.game = lua.table_from({
        "get_game_time": lambda: lua.table_from({
            "diffSec": lambda self, other: (other["elapsed"] if other is not None else 0),
            "get": lambda self, *a: 2026,
        }),
    })
    g.db = lua.table_from({"actor": lua.table_from({"id": lambda self: 0})})
    g.relation_registry = lua.table_from({
        "community_goodwill": (lambda faction, aid:
                               standing if faction == "ecolog" else 0)
        if standing is not None else (lambda faction, aid: None),
    })
    opts = {"alife/event/emission_frequency": freq,
            "alife/event/psi_storm_frequency": psi_freq}
    g.ui_options = lua.table_from({"get": lambda k: opts.get(k)})

    g.surge_manager = lua.table_from(
        {"SurgeManager": lua.table_from({
            "_delta": freq * HOUR,
            "last_surge_time": stamp(freq * HOUR - surge_left),
        })} if have_surge else {})
    g.psi_storm_manager = lua.table_from(
        {"PsiStormManager": lua.table_from({
            "_delta": psi_freq * HOUR,
            "last_psi_storm_time": stamp(psi_freq * HOUR - psi_left),
        })} if have_psi else {})

    mcm_vals = {"forecast": forecast_on, "forecast_coarse": coarse,
                "forecast_exact": exact}
    g.ui_mcm = lua.table_from({
        "get": lambda p: mcm_vals.get(str(p).split("/")[-1]),
    })
    g.alife = lambda: None
    g.level = lua.table_from({"name": lambda: "l01_escape"})
    g.axr_main = lua.table_from({})
    g.RegisterScriptCallback = lambda *a: None
    g.time_global = lambda: 0
    g.device = lambda: lua.table_from({"width": 1920, "height": 1080})

    src = io.open(SRC, encoding="utf-8").read()
    lua.execute(src)
    return lua, g


def field(t, k):
    try:
        return t[k]
    except Exception:
        return None


CASES = []


def case(name, fn):
    CASES.append((name, fn))


# --- the three tiers ------------------------------------------------------------------
def t_locked():
    _, g = build(standing=150, surge_left=2 * HOUR, psi_left=8 * HOUR)
    p = g.calendar_page()
    fc = field(p, "forecast")
    assert field(fc, "tier") == "locked", field(fc, "tier")
    assert field(fc, "standing") == 150
    assert field(fc, "need") == 200
    # negative control: a locked page must not leak the hour or the band
    assert field(p, "surge") is None, "locked tier leaked the exact time"
    assert field(p, "surge_band") is None, "locked tier leaked a band"
    return "standing 150 < 200 -> locked, nothing leaked"


def t_coarse():
    _, g = build(standing=200, surge_left=2 * HOUR, psi_left=40 * HOUR)
    p = g.calendar_page()
    fc = field(p, "forecast")
    assert field(fc, "tier") == "coarse", field(fc, "tier")
    # 2h left of a 24h period = 8% -> imminent; 40h of 48h = 83% -> quiet
    assert field(p, "surge_band") == "imminent", field(p, "surge_band")
    assert field(p, "psi_band") == "quiet", field(p, "psi_band")
    # negative control: the coarse tier must never expose the number
    assert field(p, "surge") is None, "coarse tier leaked the exact time"
    assert field(p, "psi") is None, "coarse tier leaked the exact time"
    return "standing 200 -> coarse; bands only, no hour"


def t_exact():
    _, g = build(standing=700, surge_left=4 * HOUR, psi_left=9 * HOUR)
    p = g.calendar_page()
    fc = field(p, "forecast")
    assert field(fc, "tier") == "exact", field(fc, "tier")
    assert field(p, "surge") == 4 * HOUR, field(p, "surge")
    assert field(p, "psi") == 9 * HOUR, field(p, "psi")
    assert field(p, "surge_band") is None, "exact tier should not also set a band"
    return "standing 700 -> exact; 4h and 9h returned"


# --- the band boundaries scale with the frequency option -------------------------------
def t_bands_scale():
    # 20h left. At freq 24 that is 83% -> quiet. At freq 168 the same 20h is 12%
    # -> imminent. A hardcoded hour threshold would give the same answer twice.
    _, g = build(standing=200, surge_left=20 * HOUR, psi_left=1 * HOUR, freq=24)
    a = field(g.calendar_page(), "surge_band")
    _, g = build(standing=200, surge_left=20 * HOUR, psi_left=1 * HOUR, freq=168)
    b = field(g.calendar_page(), "surge_band")
    assert a == "quiet", a
    assert b == "imminent", b
    return "20h left reads quiet at freq 24 and imminent at freq 168"


def t_band_edges():
    got = {}
    for pct, want in ((0.10, "imminent"), (0.15, "imminent"),
                      (0.30, "building"), (0.45, "building"),
                      (0.60, "quiet")):
        _, g = build(standing=200, surge_left=int(24 * HOUR * pct), psi_left=HOUR)
        got[pct] = field(g.calendar_page(), "surge_band")
        assert got[pct] == want, "at %.0f%% got %s, want %s" % (pct * 100, got[pct], want)
    return "boundaries 15%/45% land as specified"


# --- degradation ----------------------------------------------------------------------
def t_no_manager():
    _, g = build(standing=700, surge_left=0, psi_left=0, have_surge=False,
                 have_psi=False)
    p = g.calendar_page()
    assert field(field(p, "forecast"), "tier") == "exact"
    assert field(p, "surge") is None, "invented a time with no manager"
    assert field(p, "psi") is None, "invented a time with no manager"
    return "no manager -> tier stands, times stay nil"


def t_mcm_off():
    _, g = build(standing=700, surge_left=HOUR, psi_left=HOUR, forecast_on=False)
    p = g.calendar_page()
    assert field(p, "forecast") is None, "forecast built while MCM switch is off"
    assert field(p, "surge") is None
    return "MCM off -> no forecast at all"


def t_thresholds_move():
    # the same standing reads differently when the MCM thresholds move, proving the
    # tier comes from the option and not from the constant
    _, g = build(standing=300, surge_left=HOUR, psi_left=HOUR, coarse=200, exact=700)
    a = field(field(g.calendar_page(), "forecast"), "tier")
    _, g = build(standing=300, surge_left=HOUR, psi_left=HOUR, coarse=100, exact=250)
    b = field(field(g.calendar_page(), "forecast"), "tier")
    _, g = build(standing=300, surge_left=HOUR, psi_left=HOUR, coarse=400, exact=800)
    c = field(field(g.calendar_page(), "forecast"), "tier")
    assert (a, b, c) == ("coarse", "exact", "locked"), (a, b, c)
    return "standing 300 reads coarse/exact/locked as the thresholds move"


def t_no_standing():
    _, g = build(standing=None, surge_left=HOUR, psi_left=HOUR)
    fc = field(g.calendar_page(), "forecast")
    assert field(fc, "tier") == "locked", field(fc, "tier")
    assert field(fc, "standing") is None
    return "unreadable goodwill -> locked, standing nil"


for n, f in (("locked tier", t_locked), ("coarse tier", t_coarse),
             ("exact tier", t_exact), ("bands scale", t_bands_scale),
             ("band edges", t_band_edges), ("no manager", t_no_manager),
             ("mcm off", t_mcm_off), ("thresholds move", t_thresholds_move),
             ("no standing", t_no_standing)):
    case(n, f)

if __name__ == "__main__":
    bad = 0
    for name, fn in CASES:
        try:
            print("  PASS  %-17s %s" % (name, fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-17s %s" % (name, e))
        except Exception as e:
            bad += 1
            print("  ERROR %-17s %s: %s" % (name, type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
