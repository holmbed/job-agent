"""Fixes ApplyPilot for current Claude models, then clears failed scores so they get redone.

Run inside the applypilot-env:  python $HOME\\job-agent\\applypilot\\fix_applypilot.py
Safe to run more than once.
"""
import os
import sqlite3

import applypilot.llm as m

p = m.__file__
s = open(p, encoding="utf-8").read()
old = '''            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        resp = self._client.post('''
new = '''            "max_tokens": max_tokens,
        }
        if "claude" not in self.model.lower():
            payload["temperature"] = temperature

        resp = self._client.post('''
if 'if "claude" not in self.model.lower()' in s:
    print("ApplyPilot already patched")
elif old in s:
    open(p, "w", encoding="utf-8").write(s.replace(old, new))
    print("ApplyPilot patched: no temperature sent to Claude models")
else:
    print("Could not find the code to patch in", p)

db = os.path.expanduser("~/.applypilot/applypilot.db")
if os.path.exists(db):
    c = sqlite3.connect(db)
    n = c.execute("update jobs set fit_score=NULL, scored_at=NULL "
                  "where score_reasoning like '%LLM error%' or fit_score = 0").rowcount
    c.commit()
    print(f"Cleared {n} failed scores; they will be rescored on the next run")


# ---- Windows: start Claude Code and npx correctly ----
# npm installs Claude Code as claude.cmd, which Python can't start by the bare name "claude".
# Claude Code also needs "cmd /c npx" to start browser tools on Windows.
import applypilot.apply.launcher as launcher

lp = launcher.__file__
ls = open(lp, encoding="utf-8").read()
OLD_CMD = '    cmd = [\n        "claude",\n        "--model", model,'
NEW_CMD = '    cmd = [\n        __import__("shutil").which("claude") or "claude",\n        "--model", model,'
OLD_MCP = ('def _make_mcp_config(cdp_port: int) -> dict:\n'
           '    """Build MCP config dict for a specific CDP port."""\n'
           '    return {')
NEW_MCP = ('def _make_mcp_config(cdp_port: int) -> dict:\n'
           '    """Build MCP config dict for a specific CDP port."""\n'
           '    cfg = _make_mcp_config_base(cdp_port)\n'
           '    if platform.system() == "Windows":\n'
           '        for srv in cfg["mcpServers"].values():\n'
           '            if srv.get("command") == "npx":\n'
           '                srv["command"] = "cmd"\n'
           '                srv["args"] = ["/c", "npx"] + srv["args"]\n'
           '    return cfg\n'
           '\n'
           '\n'
           'def _make_mcp_config_base(cdp_port: int) -> dict:\n'
           '    return {')
changed = 0
for old, new in ((OLD_CMD, NEW_CMD), (OLD_MCP, NEW_MCP)):
    if new in ls:
        continue
    if old in ls:
        ls = ls.replace(old, new)
        changed += 1
    else:
        print("Could not find launcher code to patch:", old.splitlines()[0].strip())
if changed:
    open(lp, "w", encoding="utf-8").write(ls)
print(f"Launcher: {changed} Windows fix(es) applied" if changed else "Launcher already patched for Windows")
