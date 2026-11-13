"""Drop every job that isn't an undergrad finance internship.

ApplyPilot scores general fit, so it rates a Sales Intern 7/10. This sets off-target jobs to
score 1 so they're never enriched, scored, tailored or applied to. The daily script runs it
right after searching and again after scoring.

  python $HOME\\job-agent\\applypilot\\keep_finance_only.py
"""
import os
import re
import sqlite3

# Finance roles an undergrad rising senior can do. Wealth management is preferred but not required.
KEEP = re.compile(
    r"wealth|private client|private bank|financial plan|estate planning|retirement planning|"
    r"financial advis|wealth advis|investment advis|family office|\bpwm\b|"
    r"financ|fp&a|\bfp ?& ?a\b|treasury|\brisk\b|credit|underwrit|"
    r"investment|portfolio|asset management|equity research|\bresearch analyst|"
    r"sales (and|&) trading|\btrading\b|capital markets|banking|\bbank\b|"
    r"summer analyst|corporate development|valuation|private equity|venture capital|"
    r"fixed income|real estate (finance|investment)|\bm&a\b|global markets|\bmarkets\b", re.I)

# Not finance, or not open to an undergrad without a license.
DROP = re.compile(
    r"software|engineer|developer|\bdata scien|machine learning|\bit\b|technology intern|cyber|"
    r"marketing|human resources|\bhr\b|recruit|graphic|design|nurse|"
    r"retail sales|teller|insurance agent|loan officer|mortgage loan|"
    r"\bmba\b|graduate program|ph\.?d|master'?s|associate program|"
    r"full[- ]time|senior|\bsr\.?\b|manager|director|vice president|\bvp\b|"
    r"\b20(2[0-6]|2[89]|3\d)\b(?!.*2027)|\bspring\b|\bfall\b|\bwinter\b|year[- ]round|co-?op|"
    r"unpaid|for[- ]credit|social media|brand|credit repair|legal|crop|catastrophe|"
    r"\bit risk\b|cyber|grc|compliance analyst", re.I)

INTERN = re.compile(r"intern|summer analyst|summer 20\d\d analyst|summer associate|summer program", re.I)


def keep(title: str) -> bool:
    t = title or ""
    return bool(INTERN.search(t) and KEEP.search(t) and not DROP.search(t))


if __name__ == "__main__":
    db = os.path.expanduser("~/.applypilot/applypilot.db")
    c = sqlite3.connect(db)
    rows = c.execute("select url, title from jobs where applied_at is null "
                     "and (fit_score is null or fit_score > 1)").fetchall()
    dropped = kept = 0
    for url, title in rows:
        if keep(title):
            kept += 1
            continue
        c.execute("update jobs set fit_score = 1, scored_at = coalesce(scored_at, 'filtered'), "
                  "full_description = coalesce(full_description, '[filtered]'), "
                  "score_reasoning = '[filtered: not an undergrad finance internship] ' "
                  "|| coalesce(score_reasoning, '') where url = ?", (url,))
        dropped += 1
    c.commit()
    print(f"Kept {kept} finance internships, dropped {dropped} others.")
    print("Roles scoring 7+ and not yet applied to:")
    for score, title in c.execute("select fit_score, title from jobs where applied_at is null "
                                  "and fit_score >= 7 order by fit_score desc"):
        print(f"  [{score}/10] {title}")
