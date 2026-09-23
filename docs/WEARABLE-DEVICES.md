# A blowout warning for Wearable Devices

A proposal for [Wearable Devices](https://www.moddb.com/mods/stalker-anomaly/addons/wearable-devices),
written so it can be evaluated in about two minutes and adopted in about ten.

---

## What the player gets

Their watch starts ticking when an emission is close.

Not a number — the ecologists decide how much anyone is told, and most stalkers are told
nothing. But a stalker the ecologists have taken into their confidence gets a light on
their wrist that quickens as the pressure drops, and goes to a hard fast pulse under two
hours. No PDA, no menu, no reading anything: the device on your arm starts talking to you
while you are looking at the treeline.

That is the whole feature. Everything below is how little it costs.

---

## What it costs you

One new file in your sensor style, three lines of wiring, one key in a tier table.

### `wd_sensor_blowout.script`

Same shape as `wd_sensor_radiation.script` — a `sense()` that returns a delay, handed to
`wd_sensor_pulse`.

```lua
-- Pulse rate for an approaching emission. Silent when Seasons of the Zone is absent,
-- and silent when the player's standing with the ecologists does not entitle them to
-- the reading - that gate is the mod's, not this file's, and it is already applied.
local MIN_REPEAT, MAX_REPEAT = 120, 4000

local function get_blowout_sense()
    if not (sotz_api and sotz_api.VERSION and sotz_api.VERSION >= 1) then
        return nil                      -- mod not installed: this sensor does nothing
    end
    local b = sotz_api.blowout()
    if not (b and b.emission and b.emission.fraction) then
        return nil                      -- withheld by the ecologists, or no manager yet
    end

    -- fraction is 0 at the emission and 1 a full period away, so urgency is its
    -- complement. Below half a period there is nothing worth ticking about.
    local urgency = 1.0 - b.emission.fraction
    if urgency < 0.5 then return nil end
    return { delay = wd_sensor_pulse.get_delay(urgency, MIN_REPEAT, MAX_REPEAT) }
end

function new(cfg)
    cfg.sense = get_blowout_sense
    return wd_sensor_pulse.new(cfg)
end
```

### The wiring, in `d_watch.script`

Beside the radiation sensor, in exactly its pattern:

```lua
local blowout_sensor = wd_sensor_blowout.new({
    group = "d_watch_blowout",
    enabled = function()
        return is_sensor_ready() and d_watch_config.has_sensor("blowout")
    end,
    on_blink = function()
        bulbs.anomaly.set_on(true)          -- or its own bulb, if you would rather
        anomaly_led.set_on(true)
    end,
    off = function()
        bulbs.anomaly.set_on(false)
        anomaly_led.set_on(false)
    end,
})
```

…then `blowout_sensor.update()` alongside the others in `update_sensors`, and
`sensors = { blowout = true }` on whichever tier should carry it.

---

## Why it cannot break your mod

**It is inert without Seasons of the Zone.** `sotz_api` is a plain script namespace. If
the mod is not installed the name is nil, `sense()` returns nil on its first line, and
`wd_sensor_pulse` stops the sensor. No error, no log line, no dependency to declare.

**Every call is a pure read.** Nothing in `sotz_api` changes game state, and nothing
throws — a missing manager, a save loaded before the world is up, an absent Atmospherics
all return nil rather than raising. Your `sense()` needs a nil check, not a `pcall`.

**It is cheap enough for a per-frame sensor.** Every result is cached for two real
seconds, so calling it on your 200ms sensor interval costs one table lookup nineteen times
out of twenty.

**The contract is versioned.** `sotz_api.VERSION` is an integer that only rises, and only
when an existing field changes meaning; new fields are added without a bump. Check `>=`.
It is documented in [API.md](API.md) and covered by tests that run the shipped script
under a real Lua interpreter.

---

## If you want the simpler version

`b.emission.alert` is a single boolean: true when an emission is within two hours **and**
the player's standing entitles them to know. It is already gated, so a device can light a
lamp on it and ignore everything else.

```lua
local b = sotz_api.blowout()
if b and b.emission and b.emission.alert then
    -- get indoors
end
```

That is the whole integration, if a pulse rate is more than you want.

---

## What else is on the shelf

Same guarantees, same cost, if any of it appeals:

| call | gives you |
|---|---|
| `sotz_api.temperature()` | air temperature, and `band` / `freezing` / `frost` / `thaw` |
| `sotz_api.weather()` | what the sky is doing and what it does next, from Atmospherics' own plan |
| `sotz_api.calendar()` | the season, the next turn of it, and the days the Zone marks |

Temperature is the interesting one for a device, because Anomaly has no ambient
temperature at all — so a readout on a wrist is the only place it could ever appear.

---

## Already working, with nothing to do

If a player runs **Wearable Devices PDA Messages**, this mod's transmissions already reach
the Promin. That mod intercepts `news_manager.send_tip`, which is what Seasons of the Zone
sends through. Nothing to wire up; it is mentioned only so it is not mistaken for
something that needs doing.

---

## The snippet above is tested

`_tools/test_wd_bridge.py` lifts that `get_blowout_sense` block **out of this document**
and runs it against the real `sotz_api` under a Lua interpreter, with `wd_sensor_pulse`
stubbed exactly as you define it. It is read from the markdown rather than kept as a copy,
so the code here cannot quietly drift from the code that was checked.

```
  no Seasons of the Zone     -> nil, so the sensor stops
  withheld by the ecologists -> nil, even an hour out
  20 hours out               -> nil, nothing worth ticking about
  delay falls 1736 -> 766 -> 281 ms as the emission closes
  LIMITED drives the pulse from its bracket, without ever exposing the hour
```

If you change the snippet to suit your device, that file will tell you whether it still
behaves.

---

Seasons of the Zone: <https://github.com/devinhorowitz/seasonsofthezone>
