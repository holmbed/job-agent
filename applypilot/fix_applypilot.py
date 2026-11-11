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
                  "where score_reasoning like 'LLM error%'").rowcount
    c.commit()
    print(f"Cleared {n} failed scores; they will be rescored on the next run")
