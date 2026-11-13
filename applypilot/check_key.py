"""Diagnose the Claude API key ApplyPilot uses. Never prints the key itself.

  python $HOME\\job-agent\\applypilot\\check_key.py
"""
import os
import pathlib

import httpx

env_file = pathlib.Path.home() / ".applypilot" / ".env"


def describe(k: str) -> str:
    if not k:
        return "empty"
    issues = []
    if k != k.strip():
        issues.append("has spaces or line breaks around it")
    if k.strip().startswith(('"', "'")):
        issues.append("is wrapped in quotes")
    if not k.strip().strip("\"'").startswith("sk-ant-"):
        issues.append("does not start with sk-ant-")
    return f"length {len(k)}, starts {k[:10]!r}" + (f"  PROBLEM: {', '.join(issues)}" if issues else "")


print("1. Windows setting LLM_API_KEY in this window:", describe(os.environ.get("LLM_API_KEY", "")))

file_key = ""
if not env_file.exists():
    print(f"2. {env_file}: FILE NOT FOUND")
else:
    raw = env_file.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        print("   note: file starts with a BOM (fine for python-dotenv)")
    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    keylines = [l for l in lines if l.strip().startswith("LLM_API_KEY")]
    if not keylines:
        print(f"2. {env_file}: NO LLM_API_KEY LINE. The key was never saved into the file.")
    else:
        if len(keylines) > 1:
            print(f"   PROBLEM: {len(keylines)} LLM_API_KEY lines; keep only one")
        file_key = keylines[-1].split("=", 1)[1] if "=" in keylines[-1] else ""
        print(f"2. Key in {env_file.name}:", describe(file_key))

used = os.environ.get("LLM_API_KEY") or file_key
used = used.strip().strip("\"'")
print("3. ApplyPilot will use:", "the Windows setting" if os.environ.get("LLM_API_KEY") else "the .env file")
if not used:
    print("\nRESULT: no key found anywhere. Add LLM_API_KEY=your-key to the .env file and save.")
    raise SystemExit(1)

r1 = httpx.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": used, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-5-5", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
                timeout=60)
r2 = httpx.post("https://api.anthropic.com/v1/chat/completions",
                headers={"Authorization": "Bearer " + used},
                json={"model": "claude-haiku-5-5", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
                timeout=60)
print(f"4. Test (Anthropic format): {r1.status_code} {r1.text[:200]}")
print(f"5. Test (ApplyPilot's format): {r2.status_code} {r2.text[:200]}")

if r1.status_code == 200 and r2.status_code == 200:
    print("\nRESULT: the key works. Run daily.ps1.")
elif r1.status_code == 401:
    print("\nRESULT: Anthropic rejects this key. It was deleted, mistyped, or copied incompletely.\n"
          "Create a new key at console.anthropic.com > API Keys, use the copy button, and replace the line in .env.")
elif r1.status_code in (400, 403) and "credit" in r1.text.lower():
    print("\nRESULT: the key is valid but the account has no credit. Add credit at console.anthropic.com > Billing.")
elif r1.status_code == 200:
    print("\nRESULT: the key works but ApplyPilot's request format is rejected. Send this output to Claude.")
else:
    print("\nRESULT: unexpected answer. Send this output to Claude (it contains no key).")
