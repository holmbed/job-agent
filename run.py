"""
Daily pipeline: find new jobs, tailor an application for each, write a summary.
This is what the scheduled task runs every morning.

Usage:
  python run.py                    # full run
  python run.py --no-web           # skip the paid web search
  python run.py --max 5            # tailor at most 5 jobs this run
  python run.py --min-fit 7        # only keep applications scoring 7+ (default 6)
  python run.py --dry-run          # find jobs, but don't call Claude to tailor (free test)
"""

import argparse
import datetime as dt
import sys
import traceback
from pathlib import Path

import find_jobs
import tailor

HERE = Path(__file__).parent
RUNS = HERE / "applications" / "runs"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--max", type=int, default=15, help="max applications to tailor per run (cost cap)")
    ap.add_argument("--min-fit", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-submit", action="store_true", help="tailor only, don't auto-submit this run")
    ap.add_argument("--prefer", default="seattle,bellevue,portland,remote,san francisco,new york",
                    help="preferred cities, in order, when a firm posts one role in several cities")
    args = ap.parse_args()

    started = dt.datetime.now()
    lines = []

    def log(msg=""):
        print(msg)
        lines.append(msg)

    log(f"Job agent run {started:%Y-%m-%d %H:%M}")
    new = find_jobs.find_new(use_web=not args.no_web, log=log)
    log(f"\n{len(new)} new matching postings.")

    seen = find_jobs.load_seen()
    ready, skipped, failed, manual = [], [], [], []

    # One application per role per firm. Same program in several cities: keep the preferred city,
    # list the rest. If you already applied to that program anywhere, skip all its other cities.
    done_roles = {find_jobs.role_key(v.get("company", ""), v.get("title", "")) for v in seen.values()}
    pref = [c.strip().lower() for c in args.prefer.split(",") if c.strip()]
    rank = lambda j: next((i for i, c in enumerate(pref) if c in (j["location"] + j["title"]).lower()), len(pref))
    groups = {}
    for j in new:
        groups.setdefault(find_jobs.role_key(j["company"], j["title"]), []).append(j)
    picked, other_cities = [], []
    for key, js in groups.items():
        js.sort(key=rank)
        rest = js if key in done_roles else js[1:]
        if key not in done_roles:
            picked.append(js[0])
        for j in rest:
            other_cities.append(j)
            seen[find_jobs.norm_url(j["url"])] = {"company": j["company"], "title": j["title"], "url": j["url"],
                                                  "status": "other city of a role already handled",
                                                  "date": f"{started:%Y-%m-%d}"}
    if other_cities:
        log(f"Same role in other cities, not applied ({len(other_cities)}):")
        for j in other_cities:
            log(f"  {j['company']} | {j['title']}")
    new = picked
    log(f"{len(new)} distinct roles to tailor (up to {args.max}).\n")

    for job in new[: args.max]:
        key = find_jobs.norm_url(job["url"])
        log(f"- {job['company']} | {job['title']}")
        record = {"company": job["company"], "title": job["title"], "url": job["url"],
                  "apply_url": job.get("apply_url", job["url"]), "date": f"{started:%Y-%m-%d}"}
        try:
            posting = job.get("posting") or tailor.fetch_posting(job["url"])
        except SystemExit:
            log("  couldn't read the posting page, added to the manual list")
            manual.append(job)
            seen[key] = {**record, "status": "manual: page unreadable"}
            continue
        try:
            res = tailor.process(posting, job.get("apply_url") or job["url"], args.min_fit,
                                 dry_run=args.dry_run, verbose=False)
        except Exception as e:
            log(f"  failed: {str(e)[:150]}")
            failed.append(job)
            continue  # not marked seen, so it retries next run
        pkg = res["pkg"]
        log(f"  fit {pkg['fit_score']}/10 -> {res['status']}")
        for p in res["problems"]:
            log(f"  WARNING: {p}")
        seen[key] = {**record, "status": res["status"], "fit": pkg["fit_score"],
                     "folder": res["folder"].name if res["folder"] else ""}
        (skipped if res["status"] == "skipped" else ready).append((job, res))

    if not args.dry_run:
        find_jobs.save_seen(seen)

    log("\n==== Summary ====")
    log(f"Tailored, ready for you to review and submit: {len(ready)}")
    for job, res in ready:
        log(f"  [{res['pkg']['fit_score']}/10] {job['company']} | {job['title']}")
        link = job.get('apply_url') or job['url']
        if find_jobs.is_aggregator(link):
            log(f"      apply: find it on {job['company']}'s own careers site (link below is a copy, not the real application)")
        log(f"      {'posting' if find_jobs.is_aggregator(link) else 'apply'}: {link}")
        log(f"      files: {res['folder']}")
    if manual:
        log(f"Need you (page couldn't be read): {len(manual)}")
        for j in manual:
            log(f"  {j['company']} | {j['title']} | {j['url']}")
    log(f"Skipped for low fit: {len(skipped)}")
    if failed:
        log(f"Errors (will retry next run): {len(failed)}")
    if len(new) > args.max:
        log(f"{len(new) - args.max} more jobs waiting for the next run (raise --max to do more at once).")

    # ---- auto-submit (only when answers.json has "auto_submit": true)
    answers_file = HERE / "answers.json"
    if not args.dry_run and not args.no_submit and answers_file.exists():
        import json
        import submit
        if json.loads(answers_file.read_text(encoding="utf-8")).get("auto_submit"):
            log("\n==== Auto-submit ====")
            try:
                res = submit.run(really_submit=True, log=log)
                log(f"Submitted: {len(res['submitted'])}")
                for r, d in res["submitted"]:
                    log(f"  {r.get('company')} | {r.get('title')}")
                if res["needs you"] or res["failed"]:
                    log(f"Needs you: {len(res['needs you']) + len(res['failed'])}")
                    for r, d in res["needs you"] + res["failed"]:
                        log(f"  {r.get('company')} | {r.get('title')}: {d}")
                if res["not supported"]:
                    log(f"Apply yourself (Workday / big bank sites): {len(res['not supported'])}")
                    for r in res["not supported"]:
                        log(f"  {r.get('company')} | {r.get('title')}  {r['_url']}")
            except SystemExit as e:
                log(f"Auto-submit skipped: {e}")
            except Exception as e:
                log(f"Auto-submit error: {str(e)[:200]}")

    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / f"{started:%Y-%m-%d_%H%M}.txt").write_text("\n".join(lines), encoding="utf-8-sig")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
