import sys, os
print("cwd:", os.getcwd())
print("hermes-agent exists:", os.path.isdir("/c/Users/jamie/AppData/Local/hermes/hermes-agent"))
print("research exists:", os.path.isdir("/c/Users/jamie/AppData/Local/hermes/hermes-agent/research"))
sys.path.insert(0, "/c/Users/jamie/AppData/Local/hermes/hermes-agent")
print("sys.path:", sys.path)
# try importing directly
try:
    import research.pumpfun_engine as pe
    print("import research.pumpfun_engine OK:", pe.__file__)
except Exception as e:
    print("import research.pumpfun_engine FAIL:", type(e).__name__, e)
