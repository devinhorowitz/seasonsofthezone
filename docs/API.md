# The read API

Seasons of the Zone keeps a schedule the rest of the game does not: where the year is,
which days are marked, what the weather is about to do, and how long until the next
emission. `sotz_api.script` publishes that as a small read-only surface so other mods can
use it — on a wrist device, a HUD, a custom PDA page — without opening ours.

Everything else in the mod is internal and may be rearranged between versions. This file
is the contract.

## Calling it

X-Ray gives every `.script` file its own table and exposes it to other files under the
**file's** name. So:

```lua
local t = sotz_api.temperature()
local b = sotz_api.blowout()
```

never the bare function name. A bare `temperature()` resolves only inside `sotz_api`
itself and silently returns nil everywhere else.

## Guarantees

- **Pure reads.** Nothing here changes game state.
- **Nothing throws.** A missing manager, a missing mod, a save loaded before the world is
  up — all return `nil`, never an error. Consumers still need a nil check, not a `pcall`.
- **Cheap.** Every result is cached for 2 real seconds, so a device may call these once a
  frame.
- **`sotz_api.VERSION`** is an integer that only goes up, and only when an existing field
  changes meaning. New fields are added *without* a bump. Check `>=`, never `==`.

Current version: **1**.

---

## `temperature()`

```lua
{ low = -8, high = -2, now = -5, hour = 6.5, rising = true,
  band = "freezing", freezing = true, frost = true, thaw = false,
  curve = { … 24 hourly samples … },
  cycle = "cloudy", unit = "C", source = "observed", place = "Chornobyl" }
```

**The real world sets the base; the in-game sky moves it.** Those are two systems and the
page keeps them straight.

*Weather* — what is falling on you, how the light looks, when it turns — is Atmospherics'
alone. Nothing about Chornobyl's actual clouds touches the ribbon, the glyphs or the
barometer, because the sky the player is standing in is the game's.

*Temperature* starts outside. Anomaly has no ambient temperature at all, so there is
nothing in game for an external reading to contradict, and `fetch_weather.py` supplies the
real Zone's high and low. Then the in-game sky has its say: cloud squeezes the swing toward
the mean, rain and storm drag the whole day down. A storm reading the same as clear sky
would be a number that is real but inert.

| field | |
|---|---|
| `base_low` / `base_high` | what the station said |
| `low` / `high` / `now` | after the in-game sky moved it |
| `sky_shift` | the gap, in whole degrees — negative when the weather is costing you |
| `source` | `observed` when a station reading was used, `model` when climate normals were |

Off a 14 / 4 station reading, clear sky reads 14 at mid-afternoon and a storm reads 8.

The curve between the endpoints runs on the **game** clock, because the day is accelerated:
minimum just before dawn, maximum mid-afternoon, the rise compressed against the fall.

### The hooks

Temperature drives nothing in Anomaly, which is exactly what makes it useful to hang a mod
off - it is a free signal with no existing behaviour to fight.

| field | meaning |
|---|---|
| `band` | `freezing` / `cold` / `mild` / `warm` / `hot`, for *now* |
| `freezing` | below zero at this moment |
| `frost` | the day dips below zero at some point |
| `thaw` | it froze **and** will rise above zero again |

`thaw` is the pair, not the freeze: a melt effect wants the day that goes under and comes
back, which a hard freeze never does.

The staging half publishes the day-scale ones as **periods**, so a mod can be scoped to
them exactly as it is scoped to a season - `when = ["freezing"]`, `["thaw"]`, `["heat"]`.
They overlay whatever season is running:

```
high  14.5  low   7.8  ->  ['autumn']
high  -2.0  low  -9.0  ->  ['autumn', 'freezing']
high   6.0  low  -3.0  ->  ['autumn', 'freezing', 'thaw']
high  31.0  low  19.0  ->  ['autumn', 'heat']
```

Every flag is decided in **Celsius before any unit conversion**: zero is a property of
water, not of the unit being read.

## `weather()`

```lua
{ now = "storm",
  next = { cycle = "rain", at = "11:30", away_min = 90 },
  plan = { … up to six segments … } }
```

`nil` without Atmospherics.

**Not a prediction.** Atmospherics does not roll the weather as it goes —
`WeatherManager:roll_day_plan` fills `day_plan` a full 24 game hours ahead. This reads that
plan, so `at` is when it will actually change. Repeats of the current cycle are not
changes and are skipped, so `next` is always a real transition. `away_min` is game minutes.

Cycle names are Atmospherics' own: `clear`, `partly`, `cloudy`, `foggy`, `rain`, `storm`.

## `blowout()`

```lua
{ tier = "exact", standing = 780, need = 200, need_exact = 700,
  emission = { seconds = 14400, fraction = 0.17 },
  psi      = { band = "building", fraction = 0.30 } }
```

Resolution depends on the player's standing with the ecologists — see
[INTERFACE.md](INTERFACE.md#the-ecologist-forecast).

| `tier` | `seconds` | `band` | `fraction` |
|---|---|---|---|
| `locked` | nil | nil | nil |
| `coarse` | nil | `WITHIN 2 HOURS` / `2 to 8 hours` / `8 to 16 hours` / `ALL CLEAR` | bracket midpoint |
| `exact` | game seconds | nil | 0–1 |

The coarse brackets are **fixed hours, not a fraction of the period**. A relayed warning
is worth a window rather than a number, and "two to eight hours" has to mean two to eight
hours whatever the frequency slider says.

### `alert` — the one to hang a device off

Every part also carries `alert`: true when an emission is **within two hours** *and* the
player's tier is allowed to know. That is the moment the page stops forecasting and starts
warning — it is what makes the panel line strobe — and it is already gated, so a consumer
does not have to re-derive the threshold and drift out of step with the page when either
number moves.

```lua
local b = sotz_api.blowout()
if b and b.emission and b.emission.alert then
    -- get indoors. True at CLEARED under two hours, and at LIMITED when the bracket
    -- reads WITHIN 2 HOURS. Never true at CLASSIFIED, where a pulse would leak the one
    -- thing being withheld.
end
```

**Do not infer anything from a locked tier.** Showing nothing is the point; a consumer
that falls back to its own countdown defeats the gate.

**`fraction` is the field to drive a gauge, a bar or a pulse rate from.** It is 0 at the
event and 1 a full period away, needs no unit conversion, and stays correct when the player
moves the frequency slider.

## `calendar()`

```lua
{ season = "autumn", label = "autumn", today = "22 September 2026",
  next = { label = "winter", days = 40 },
  marked = { kind = "memorial", key = "chornobyl" } }
```

`marked` is nil on ordinary days. `kind` is `memorial` or `anniversary`.

---

## Wearable Devices

The obvious consumer, and the one this API was shaped around.

### What is already free

If you run **Wearable Devices PDA Messages**, this mod's transmissions already reach the
Promin. That mod intercepts `news_manager.send_tip`, which is exactly what Seasons of the
Zone uses to send its remembrance and anniversary messages. Nothing to wire up.

### Why this mod ships no sensor

Wearable Devices gates sensors on the device tier: `wd_config.has_sensor(key)` reads
`active_tier.sensors[key]`, and `d_watch` / `d_vektor` construct their sensors directly
against their own configs. A new sensor key means editing those files, which would make
Seasons of the Zone a fork of Wearable Devices. It is not one, and a bridge that silently
did nothing would be worse than none.

So the bridge belongs in a **separate compat mod**, exactly as PDA Messages is separate.

### What a blowout sensor looks like

`wd_sensor_pulse` takes a `cfg` and returns a kernel with `update()` and `reset()`. The
pulse rate comes from `get_delay(fraction, min, max)` — a higher fraction means a faster
pulse, which is why `blowout()` publishes one.

```lua
-- in a compat mod, alongside a tier that declares sensors.blowout = true
local MIN_REPEAT, MAX_REPEAT = 120, 4000

local function sense()
    if not (sotz_api and sotz_api.VERSION and sotz_api.VERSION >= 1) then return nil end
    local b = sotz_api.blowout()
    if not (b and b.emission and b.emission.fraction) then return nil end   -- locked: silent
    -- near the event -> fraction near 0 -> we want the FASTEST pulse
    local urgency = 1.0 - b.emission.fraction
    if urgency < 0.5 then return nil end                     -- quiet: do not tick at all
    return { delay = wd_sensor_pulse.get_delay(urgency, MIN_REPEAT, MAX_REPEAT) }
end

function new(cfg)
    cfg.sense = sense
    return wd_sensor_pulse.new(cfg)
end
```

The device ticks slowly when an emission is a way off, faster as it closes, and says
nothing at all to a stalker the ecologists have not taken into their confidence — which is
the whole point of the gate.

`temperature()` and `weather()` need no sensor at all; they are values a page or a readout
can print directly.
