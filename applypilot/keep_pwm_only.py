"""Drop every job that isn't a wealth management / financial planning / advisory role.

ApplyPilot scores general fit, so it rates a Sales Intern 7/10. This sets off-target jobs
to score 1 so they're never tailored or applied to. Run it after scoring, before tailoring.

  python $HOME\\job-agent\\applypilot\\keep_pwm_only.py
"""
import os
import re
import sqlite3

KEEP = re.compile(r"wealth|private client|private bank|financial plan|planning|advis|family office|\bpwm\b|"
                  r"investment management|portfolio|trust|financial analyst|client service", re.I)
DROP = re.compile(r"software|engineer|developer|technology intern|marketing|human resources|\bhr\b|"
                  r"recruit|graphic|design|nurse|retail sales|insurance agent|mba|phd|investment banking", re.I)

db = os.path.expanduser("~/.applypilot/applypilot.db")
c = sqlite3.connect(db)
# unscored jobs too, so off-target titles never get enriched, scored or tailored (saves time and API credit)
rows = c.execute("select url, title from jobs where applied_at is null "
                 "and (fit_score is null or fit_score > 1)").fetchall()
dropped = kept = 0
for url, title in rows:
    t = title or ""
    if KEEP.search(t) and not DROP.search(t):
        kept += 1
        continue
    c.execute("update jobs set fit_score = 1, scored_at = coalesce(scored_at, 'filtered'), "
              "full_description = coalesce(full_description, '[filtered]'), "
              "score_reasoning = '[filtered: not a wealth management role] ' "
              "|| coalesce(score_reasoning, '') where url = ?", (url,))
    dropped += 1
c.commit()
print(f"Kept {kept} wealth management roles, dropped {dropped} others.")
print("Roles scoring 7+ and not yet applied to:")
for score, title in c.execute("select fit_score, title from jobs where applied_at is null and fit_score >= 7 "
                              "order by fit_score desc"):
    print(f"  [{score}/10] {title}")
