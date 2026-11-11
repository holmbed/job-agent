"""
Job finder. Two sources:
  1. Public job feeds (Lever, Greenhouse, Ashby) for the firms in firms.json. Free and reliable.
  2. A Claude web search for wealth management internships anywhere else (big banks, Workday sites).
     Costs about $0.10 to $0.40 per run.

Usage:
  python find_jobs.py                 # list new matching jobs, don't tailor anything
  python find_jobs.py --no-web        # feeds only (free)
  python find_jobs.py --check-firms   # test every firm in firms.json and show how many jobs each has
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
SEEN_FILE = HERE / "applications" / "seen.json"
UA = {"User-Agent": "Mozilla/5.0 (job-agent personal job search)"}

# What counts as a match. Claude's fit score does the fine filtering later.
INTERN = re.compile(r"\bintern(ship)?s?\b|summer analyst|summer associate|summer program", re.I)
FIELD = re.compile(r"wealth|private client|private bank|financial plan|planning|advis|client service|"
                   r"investment|portfolio|family office|\bpwm\b|financial analyst|finance", re.I)
EXCLUDE = re.compile(r"software|engineer|developer|data scien|marketing|legal|human resources|\bhr\b|"
                     r"recruit|design|cyber|\bit\b|technology|graduate program|mba|phd|fall 20|spring 20|winter 20", re.I)
OLD_YEAR = re.compile(r"\b202[0-6]\b")


# ---------------------------------------------------------------- helpers

def clean_html(raw: str) -> str:
    from bs4 import BeautifulSoup
    return BeautifulSoup(html.unescape(raw or ""), "html.parser").get_text("\n", strip=True)


AGGREGATORS = ["linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com", "joinhandshake.com",
               "simplify.jobs", "builtin.com", "builtinseattle.com", "tealhq.com", "talents.vaia.com",
               "higherin.com", "targetjobs.co.uk", "career.com", "joinrise.co", "interndock.com",
               "diversityjobs.com", "interviewpal.com", "app.joinrunway.io"]


def is_aggregator(url: str) -> bool:
    """True for job boards that copy postings instead of hosting the real application."""
    host = re.sub(r"^https?://", "", (url or "").lower()).split("/")[0]
    return host.endswith(".edu") or any(host == d or host.endswith("." + d) for d in AGGREGATORS)


def norm_url(u: str) -> str:
    return re.sub(r"[?#].*$", "", (u or "").strip()).rstrip("/").lower()


def matches(title: str) -> bool:
    if not (INTERN.search(title) and FIELD.search(title)) or EXCLUDE.search(title):
        return False
    # drop titles that name an old year and not 2027
    return not (OLD_YEAR.search(title) and "2027" not in title)


def role_key(company: str, title: str) -> str:
    """Same program in different cities -> same key. 'PWM Internship (Boston - June 2027 Start)' -> 'pwm internship'."""
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", title.lower())
    t = re.sub(r"\s[-|,]\s.*$", " ", t)
    t = re.sub(r"[^a-z ]", " ", t)
    return f"{company.lower().strip()}|{' '.join(t.split())}"


def load_seen() -> dict:
    """Jobs already handled: everything the pipeline processed, plus anything you ran tailor.py on by hand."""
    try:
        seen = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        seen = {}
    try:
        import csv
        with (HERE / "applications" / "log.csv").open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                src = row.get("source", "")
                if src.startswith("http") and norm_url(src) not in seen:
                    seen[norm_url(src)] = {"company": row.get("company", ""), "title": row.get("role", ""),
                                           "status": "done by hand", "date": row.get("date", "")}
    except Exception:
        pass
    return seen


def save_seen(seen: dict):
    SEEN_FILE.parent.mkdir(exist_ok=True)
    SEEN_FILE.write_text(json.dumps(seen, indent=1, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- 1. job board feeds

def fetch_feed(firm: dict) -> list:
    """Return every job on a firm's board as {company, title, location, url, apply_url, posting}."""
    import requests
    ats, token, name = firm["ats"], firm["token"], firm["name"]

    if ats == "lever":
        data = requests.get(f"https://api.lever.co/v0/postings/{token}?mode=json", headers=UA, timeout=20).json()
        return [{
            "company": name, "title": j.get("text", ""),
            "location": (j.get("categories") or {}).get("location", ""),
            "url": j.get("hostedUrl", ""), "apply_url": j.get("applyUrl", ""),
            "posting": f"{name}\n{j.get('text','')}\n{(j.get('categories') or {}).get('location','')}\n\n"
                       + (j.get("descriptionPlain") or clean_html(j.get("description", "")))
                       + "\n\n" + "\n".join(clean_html(l.get("content", "")) for l in j.get("lists", []))
                       + "\n" + (j.get("additionalPlain") or ""),
        } for j in data]

    if ats == "greenhouse":
        data = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
                            headers=UA, timeout=20).json()
        return [{
            "company": name, "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "apply_url": f"https://job-boards.greenhouse.io/{token}/jobs/{j.get('id')}",
            "posting": f"{name}\n{j.get('title','')}\n{(j.get('location') or {}).get('name','')}\n\n"
                       + clean_html(j.get("content", "")),
        } for j in data.get("jobs", [])]

    if ats == "ashby":
        data = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{token}", headers=UA, timeout=20).json()
        return [{
            "company": name, "title": j.get("title", ""), "location": j.get("location", ""),
            "url": j.get("jobUrl", ""), "apply_url": j.get("applyUrl", "") or j.get("jobUrl", ""),
            "posting": f"{name}\n{j.get('title','')}\n{j.get('location','')}\n\n"
                       + (j.get("descriptionPlain") or clean_html(j.get("descriptionHtml", ""))),
        } for j in data.get("jobs", [])]

    raise ValueError(f"unknown ats {ats}")


def from_feeds(firms: list, log=print) -> list:
    found = []
    for f in firms:
        try:
            jobs = fetch_feed(f)
        except Exception as e:
            log(f"  {f['name']}: feed failed ({str(e)[:80]})")
            continue
        hits = [j for j in jobs if matches(j["title"])]
        log(f"  {f['name']}: {len(jobs)} jobs, {len(hits)} match")
        found += [{**j, "source": f"feed:{f['ats']}"} for j in hits]
    return found


# ---------------------------------------------------------------- 2. Claude web search

SEARCH_PROMPT = """Find currently open internship postings in private wealth management, wealth management, \
financial planning, or wealth advisory for Summer 2027 in the United States. Cast a wide net: big banks and \
wirehouses (Morgan Stanley, Merrill, UBS, Wells Fargo, J.P. Morgan, Goldman Sachs, RBC, Raymond James, \
Edward Jones), trust banks (Northern Trust, BNY), and independent RIAs and multi-family offices.

Rules:
- Only roles for undergraduates, starting summer 2027. Skip anything for 2026 or earlier, MBA roles, and roles whose deadline has passed.
- The url MUST be the employer's own posting: their careers site or their applicant system (myworkdayjobs.com, greenhouse.io, lever.co, ashbyhq.com, icims.com, taleo.net, oraclecloud.com, successfactors, eightfold.ai). Never a university career site (.edu), Handshake, Simplify, Built In, Teal, Indeed, or any other job aggregator. If you only find it on an aggregator, search again for the employer's own page; if you still can't find it, leave it out.
- Skip these already-known postings: {known}

After searching, output ONLY a JSON array between <jobs> and </jobs>, each item:
{{"company": "...", "title": "...", "location": "...", "url": "..."}}"""


def from_web_search(known: list, max_searches: int = 8, log=print) -> list:
    import anthropic
    from tailor import MODEL
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": SEARCH_PROMPT.format(known="; ".join(known[:80]) or "none")}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches,
              "blocked_domains": AGGREGATORS}]
    text = ""
    for _ in range(4):  # the API may pause long search turns; resend to continue
        msg = client.messages.create(model=MODEL, max_tokens=8000, messages=messages, tools=tools)
        text += "".join(b.text for b in msg.content if b.type == "text")
        if msg.stop_reason != "pause_turn":
            break
        messages = messages[:1] + [{"role": "assistant", "content": msg.content}]
    m = re.search(r"<jobs>(.*?)</jobs>", text, re.S)
    try:
        items = json.loads(m.group(1)) if m else []
    except json.JSONDecodeError:
        items = []
    log(f"  web search: {len(items)} postings found")
    return [{"company": i.get("company", ""), "title": i.get("title", ""), "location": i.get("location", ""),
             "url": i.get("url", ""), "apply_url": i.get("url", ""), "posting": None, "source": "web"}
            for i in items if i.get("url")]


# ---------------------------------------------------------------- combine

def find_new(use_web: bool = True, log=print) -> list:
    firms = json.loads((HERE / "firms.json").read_text(encoding="utf-8"))["firms"]
    seen = load_seen()
    log("Checking job board feeds...")
    jobs = from_feeds(firms, log)
    if use_web:
        log("Searching the web...")
        known = [f"{v.get('company')} - {v.get('title')}" for v in seen.values()]
        try:
            jobs += from_web_search(known, log=log)
        except Exception as e:
            log(f"  web search failed ({str(e)[:120]})")

    new, keys = [], set(seen)
    titles_seen = {(v.get("company", "").lower(), v.get("title", "").lower()) for v in seen.values()}
    for j in jobs:
        k = norm_url(j["url"])
        if not k or k in keys or (j["company"].lower(), j["title"].lower()) in titles_seen:
            continue
        keys.add(k)
        new.append(j)
    return new


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-web", action="store_true", help="feeds only, no paid web search")
    ap.add_argument("--check-firms", action="store_true", help="test each firm's feed")
    args = ap.parse_args()

    if args.check_firms:
        firms = json.loads((HERE / "firms.json").read_text(encoding="utf-8"))["firms"]
        for f in firms:
            try:
                jobs = fetch_feed(f)
                print(f"OK    {f['name']}: {len(jobs)} jobs" + (f" (e.g. {jobs[0]['title']})" if jobs else ""))
            except Exception as e:
                print(f"FAIL  {f['name']} ({f['ats']}/{f['token']}): {str(e)[:80]}")
        return

    new = find_new(use_web=not args.no_web)
    print(f"\n{len(new)} new matching jobs:")
    for j in new:
        print(f"  {j['company']} | {j['title']} | {j['location']}\n    {j['url']}")


if __name__ == "__main__":
    main()
