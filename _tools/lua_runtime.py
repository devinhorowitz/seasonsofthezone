"""The Lua the game runs, for the tests that load the mod's scripts.

X-Ray here runs LuaJIT 2.0.4: the modded exes carry that string, and so does xray-monolith's
luajit.h. lupa ships it as luajit20. LuaJIT 2.1 walks tables in a different order and has
library functions 2.0 lacks, and lupa's default Lua 5.x can pass what the game would not, or
fail on what it runs: a fractional day, for one, which os.time() truncates in LuaJIT and refuses
in 5.x. So the tests take LuaJIT 2.0, and say which Lua they fell back to when this lupa was
built without it.
"""
try:
    from lupa.luajit20 import LuaRuntime
    NAME = "LuaJIT 2.0"
except ImportError:                                 # a lupa built without LuaJIT 2.0
    try:
        from lupa.luajit21 import LuaRuntime
        NAME = "LuaJIT 2.1, not the game's LuaJIT 2.0"
    except ImportError:                             # a lupa built without LuaJIT
        from lupa import LuaRuntime
        NAME = "lupa's default Lua, not the game's LuaJIT 2.0"

__all__ = ["LuaRuntime", "NAME"]
