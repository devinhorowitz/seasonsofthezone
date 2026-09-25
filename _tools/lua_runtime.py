"""The Lua the game runs, for the tests that load the mod's scripts.

X-Ray runs LuaJIT 2.1, and lupa ships one. A test run under lupa's default Lua 5.x can
pass what the game would not, or fail on what it runs: a fractional day, for one, which
os.time() truncates in LuaJIT and refuses in 5.x. So the tests take LuaJIT, and say so
when this lupa was built without it.
"""
try:
    from lupa.luajit21 import LuaRuntime
    NAME = "LuaJIT 2.1"
except ImportError:                                 # a lupa built without LuaJIT
    from lupa import LuaRuntime
    NAME = "lupa's default Lua, not the game's LuaJIT 2.1"

__all__ = ["LuaRuntime", "NAME"]
