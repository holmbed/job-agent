"""
Auto-submitter for Lever, Greenhouse and Ashby application forms.

For each tailored application that is ready and scores high enough, it:
  1. opens the application form in a browser
  2. reads every field (text boxes, dropdowns, radio buttons, file uploads)
  3. asks Claude to map each field to an answer from answers.json, your resume, or the cover letter
  4. fills the form and uploads your resume and cover letter
  5. STOPS without submitting if any required question has no known answer, a CAPTCHA appears,
     or the site wants an account; that application goes on your "needs you" list
  6. otherwise submits, then saves screenshots of the filled form and the confirmation page

Usage:
  python submit.py                     # practice run: fills forms, screenshots, does NOT submit
  python submit.py --watch             # same, but you watch the browser
  python submit.py --submit            # really submits (also needs "auto_submit": true in answers.json)
  python submit.py --only URL          # one application only
  python submit.py --list              # show what's queued and why
"""

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

import find_jobs
import tailor

HERE = Path(__file__).parent
APPS = HERE / "applications"
SHOTS = APPS / "screenshots"
PROFILE_DIR = HERE / ".browser-profile"
SUPPORTED = ("lever.co", "greenhouse.io", "ashbyhq.com")

SUCCESS = re.compile(r"thank you for (applying|your application|your interest)|application (has been |was )?"
                     r"(received|submitted)|we('ve| have) received your application|successfully submitted", re.I)
VERIFY = re.compile(r"verification code|security code|confirm your email|check your email for a code", re.I)
ACCOUNT = re.compile(r"create (an )?account|sign in to apply|log ?in to apply", re.I)


# ---------------------------------------------------------------- queue

def load_answers() -> dict:
    p = HERE / "answers.json"
    if not p.exists():
        sys.exit("answers.json is missing. Copy answers.example.json to answers.json and fill it in.")
    a = json.loads(p.read_text(encoding="utf-8"))
    missing = [k for k, v in a.items() if v == "FILL_ME"]
    if missing:
        sys.exit(f"Fill these in answers.json first: {', '.join(missing)}")
    return a


def ats_of(url: str) -> str:
    return next((d for d in SUPPORTED if d in (url or "")), "")


def queue(seen: dict, answers: dict, only: str = "") -> tuple:
    """Return (to_submit, needs_you) lists of seen records."""
    todo, manual = [], []
    for key, r in seen.items():
        url = r.get("apply_url") or r.get("url", "")
        if only and find_jobs.norm_url(only) not in (key, find_jobs.norm_url(url)):
            continue
        if r.get("status") != "ready" and not only:
            continue  # with --only, any status is allowed; the daily run only takes "ready"
        if only and r.get("status") == "submitted":
            continue
        if not only and (r.get("fit") or 0) < answers.get("min_fit_to_submit", 7):
            continue
        if not r.get("folder") or not (APPS / r["folder"]).exists():
            continue  # files were deleted or never made
        (todo if ats_of(url) else manual).append({**r, "_key": key, "_url": url})
    return todo, manual


# ---------------------------------------------------------------- reading the form

COLLECT_JS = r"""
() => {
  const txt = el => { if (!el) return ''; const c = el.cloneNode(true);
    c.querySelectorAll('select, option, textarea, input, [role="listbox"], [role="option"]').forEach(x => x.remove());
    return (c.innerText || c.textContent || '').replace(/\s+/g, ' ').trim(); };
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
                          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const labelOf = el => {
    let t = '';
    const lb = el.getAttribute('aria-labelledby');
    if (lb) t = lb.split(/\s+/).map(id => txt(document.getElementById(id))).join(' ');
    if (!t && el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) t = txt(l); }
    if (!t) { const l = el.closest('label'); if (l) t = txt(l); }
    if (!t) t = el.getAttribute('aria-label') || '';
    if (!t) { let c = el.parentElement;
      for (let i = 0; i < 5 && c && !t; i++) {
        const l = c.querySelector('label, legend, .application-label, .text, [class*="label"]'); if (l && !l.contains(el)) t = txt(l);
        c = c.parentElement; } }
    if (!t) t = el.getAttribute('placeholder') || el.name || '';
    return t.slice(0, 400);
  };
  const groupLabel = el => {
    const fs = el.closest('fieldset'); if (fs) { const lg = fs.querySelector('legend'); if (lg) return txt(lg); }
    let c = el.parentElement;
    for (let i = 0; i < 6 && c; i++) {
      const l = c.querySelector('.application-label, legend, [class*="label"], label:not(:has(input))');
      if (l && !l.contains(el)) return txt(l);
      c = c.parentElement; }
    return el.name || '';
  };
  const out = []; let n = 0; const groups = {};
  for (const el of document.querySelectorAll('input, textarea, select, [role="combobox"]')) {
    if (el.dataset.jaSkip) continue;
    let type = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea'
             : el.getAttribute('role') === 'combobox' ? 'combobox' : (el.type || 'text').toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(type)) continue;
    const lab = el.labels && el.labels[0];
    if (type !== 'file' && !visible(el) && !((type === 'radio' || type === 'checkbox') && lab && visible(lab))) continue;
    const required = el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$/.test(labelOf(el));
    if (type === 'radio' || type === 'checkbox') {
      const g = el.name || ('_' + n);
      const opt = labelOf(el);
      if (!groups[g]) { groups[g] = { id: 'ja' + (n++), type, label: groupLabel(el), required, options: [], _els: [] };
                        out.push(groups[g]); }
      el.setAttribute('data-ja', groups[g].id + ':' + groups[g].options.length);
      groups[g].options.push(opt); groups[g].required = groups[g].required || required;
      continue;
    }
    const id = 'ja' + (n++);
    el.setAttribute('data-ja', id);
    const f = { id, type, label: labelOf(el), required, value: el.value || '' };
    if (type === 'select') f.options = [...el.options].map(o => o.text.trim()).filter(Boolean).slice(0, 80);
    if (type === 'file') f.accept = el.accept || '';
    out.push(f);
  }
  for (const f of out) if (f.type === 'checkbox' && f.options.length === 1) f.label = f.options[0];
  return out.map(({_els, ...f}) => f);
}
"""

CAPTCHA_JS = r"""
() => [...document.querySelectorAll('iframe')].some(f => /recaptcha\/api2\/bframe|hcaptcha\.com.*challenge|challenges\.cloudflare/.test(f.src)
        && f.getBoundingClientRect().height > 100)
"""


def combobox_options(page, el) -> list:
    """Open a searchable dropdown and read its options without choosing one."""
    try:
        el.click(timeout=3000)
        page.wait_for_timeout(500)
        opts = page.locator('[role="option"]:visible').all_inner_texts()[:60]
        el.press("Escape")
        return [o.strip() for o in opts if o.strip()]
    except Exception:
        return []


def read_form(page) -> list:
    fields = page.evaluate(COLLECT_JS)
    for f in fields:
        if f["type"] == "combobox":
            f["options"] = combobox_options(page, page.locator(f'[data-ja="{f["id"]}"]'))
            if not f["options"]:
                f["note"] = "searchable list: type a value and the closest match is picked"
    return fields


# ---------------------------------------------------------------- asking Claude for answers

MAP_PROMPT = """You are filling out a job application form for the candidate below. For each form field, give the value to enter.

Rules:
- Use ONLY the candidate's answers file, resume data, and cover letter. Never invent facts.
- When a field lists options, return the exact text of one option.
- File fields: return "__RESUME__" for resume/CV uploads, "__COVER_LETTER__" for cover letter uploads, "__SKIP__" for anything else.
- If a text field asks for a cover letter, return "__COVER_LETTER_TEXT__".
- Short written questions (why this firm, why this role, tell us about yourself): answer in at most 120 words, first person,
  using only facts from the resume data and cover letter. No em dashes. Plain and specific.
- If a field is optional and you have no answer, return "__SKIP__".
- If a field is REQUIRED and the answer is not in the provided data, return "__UNKNOWN__". Do not guess.
- Checkboxes and radio groups: return the exact option text to select. For a single consent or terms checkbox, return "check" if the answers file consents, else "__UNKNOWN__".
- Demographic questions: use the answers file. If no option matches its meaning, pick the option meaning "decline to answer".

Company: {company}
Role: {role}

<answers_file>
{answers}
</answers_file>

<resume_data>
{resume}
</resume_data>

<cover_letter>
{cover}
</cover_letter>

<form_fields>
{fields}
</form_fields>

Output ONLY a JSON object between <values> and </values> mapping each field id to its value, plus a key "_essays" listing the ids where you wrote a short written answer."""


def map_fields(fields: list, answers: dict, record: dict, cover_text: str) -> dict:
    import anthropic
    resume = json.loads((HERE / "resume_data.json").read_text(encoding="utf-8"))
    public = {k: v for k, v in answers.items() if not k.startswith("_") and k not in
              ("auto_submit", "min_fit_to_submit", "max_submissions_per_run")}
    prompt = MAP_PROMPT.format(company=record.get("company", ""), role=record.get("title", ""),
                               answers=json.dumps(public, indent=1), resume=json.dumps(resume, indent=1),
                               cover=cover_text, fields=json.dumps(fields, indent=1, ensure_ascii=False))
    msg = anthropic.Anthropic().messages.create(model=tailor.MODEL, max_tokens=6000,
                                                messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"<values>(.*?)</values>", text, re.S)
    if not m:
        raise RuntimeError("Claude did not return field values")
    return json.loads(m.group(1))


# ---------------------------------------------------------------- filling

def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def best_option(want: str, options: list) -> str:
    """Closest option text to `want`, or '' if nothing is reasonably close."""
    w = norm(want)
    if not w or not options:
        return ""
    for o in options:
        if norm(o) == w:
            return o
    for o in options:
        if norm(o).startswith(w) or w.startswith(norm(o)) and len(norm(o)) > 2:
            return o
    for o in options:
        if w in norm(o) or (norm(o) and norm(o) in w):
            return o
    ws = set(w.split())
    scored = sorted(((len(ws & set(norm(o).split())) / max(len(ws), 1), o) for o in options), reverse=True)
    return scored[0][1] if scored and scored[0][0] >= 0.5 else ""


def cover_letter_text(folder: Path) -> str:
    try:
        from docx import Document
        ps = [p.text for p in Document(folder / "Daniel_Holmberg_Cover_Letter.docx").paragraphs]
        start = next(i for i, p in enumerate(ps) if p.startswith("Dear"))
        return "\n\n".join(ps[start:])
    except Exception:
        return ""


def file_for(folder: Path, kind: str) -> str:
    base = "Daniel_Holmberg_Resume" if kind == "resume" else "Daniel_Holmberg_Cover_Letter"
    for ext in (".pdf", ".docx"):
        if (folder / f"{base}{ext}").exists():
            return str(folder / f"{base}{ext}")
    return ""


def fill(page, fields: list, values: dict, folder: Path, cover_text: str) -> list:
    """Fill every field. Returns a list of problems (empty list means the form is complete)."""
    problems = []
    for f in fields:
        v = values.get(f["id"], "__SKIP__")
        if isinstance(v, list):
            v = v[0] if v else "__SKIP__"
        v = str(v)
        if v == "__UNKNOWN__":
            if f["required"]:
                problems.append(f"No answer for required question: {f['label'][:120]}")
            continue
        if v == "__SKIP__" or v == "":
            continue
        if v == "__COVER_LETTER_TEXT__":
            v = cover_text
        loc = page.locator(f'[data-ja="{f["id"]}"]').first
        try:
            t = f["type"]
            if t == "file":
                path = file_for(folder, "resume" if v == "__RESUME__" else "cover")
                if path:
                    loc.set_input_files(path)
                elif f["required"]:
                    problems.append(f"Missing file for: {f['label'][:80]}")
            elif t == "select":
                opt = best_option(v, f.get("options", []))
                if opt:
                    loc.select_option(label=opt)
                elif f["required"]:
                    problems.append(f"No matching option for {f['label'][:80]!r} (wanted {v!r})")
            elif t == "combobox":
                loc.click(timeout=4000)
                loc.fill("")
                loc.type(v[:40], delay=30)
                page.wait_for_timeout(1200)
                opts = page.locator('[role="option"]:visible')
                texts = opts.all_inner_texts()
                opt = best_option(v, texts)
                if opt:
                    opts.nth(texts.index(opt)).click()
                else:
                    loc.press("Escape")
                    if f["required"]:
                        problems.append(f"No matching option for {f['label'][:80]!r} (wanted {v!r})")
            elif t in ("radio", "checkbox"):
                if t == "checkbox" and len(f["options"]) == 1:
                    if v.lower() in ("check", "yes", "true") or norm(v) == norm(f["options"][0]):
                        page.locator(f'[data-ja="{f["id"]}:0"]').check(force=True)
                    continue
                opt = best_option(v, f["options"])
                if opt:
                    page.locator(f'[data-ja="{f["id"]}:{f["options"].index(opt)}"]').check(force=True)
                elif f["required"]:
                    problems.append(f"No matching choice for {f['label'][:80]!r} (wanted {v!r})")
            else:
                loc.fill(v)
        except Exception as e:
            if f["required"]:
                problems.append(f"Could not fill {f['label'][:80]!r}: {str(e).splitlines()[0][:100]}")
    return problems


def invalid_fields(page) -> list:
    """Fields the browser itself says are invalid (unchecked required boxes, bad emails, etc.)."""
    return page.evaluate(r"""() => [...document.querySelectorAll('[data-ja]')]
      .filter(el => el.willValidate && !el.checkValidity() && el.getAttribute('role') !== 'combobox')
      .map(el => (el.labels && el.labels[0] ? el.labels[0].innerText : (el.name || el.id)).trim().slice(0, 80))
      .filter((v, i, a) => a.indexOf(v) === i).slice(0, 10)""")


def empty_required(page) -> list:
    """Required text/select fields that are still empty after filling."""
    return page.evaluate(r"""() => [...document.querySelectorAll('[data-ja]')]
      .filter(el => (el.required || el.getAttribute('aria-required') === 'true')
                    && ['INPUT','TEXTAREA','SELECT'].includes(el.tagName)
                    && el.getAttribute('role') !== 'combobox'
                    && !['radio','checkbox','file'].includes(el.type) && !el.value)
      .map(el => el.getAttribute('aria-label') || el.name || el.id).slice(0, 10)""")


# ---------------------------------------------------------------- one application

def apply_one(ctx, record: dict, answers: dict, really_submit: bool, log=print) -> tuple:
    """Returns (result, detail). result is one of: submitted, practice-ok, needs you, failed."""
    folder = APPS / record.get("folder", "")
    if not record.get("folder") or not folder.exists():
        return "failed", "application folder not found"
    url = record["_url"]
    if "lever.co" in url and not url.rstrip("/").endswith("/apply"):
        url = url.rstrip("/") + "/apply"
    stamp = f"{dt.datetime.now():%Y%m%d_%H%M}_{tailor.slug(record.get('company', ''))[:20]}"
    SHOTS.mkdir(parents=True, exist_ok=True)

    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        body = page.inner_text("body")
        if ACCOUNT.search(body) and not page.locator("input[type=file]").count():
            return "needs you", "site wants an account or login"
        if page.evaluate(CAPTCHA_JS):
            return "needs you", "CAPTCHA on the form"

        fields = read_form(page)
        if not any(f["type"] == "file" for f in fields):
            return "needs you", "no resume upload found on the page (the form may be elsewhere)"
        cover = cover_letter_text(folder)
        values = map_fields(fields, answers, record, cover)
        essays = values.pop("_essays", [])
        problems = fill(page, fields, values, folder, cover)
        problems += [f"Required field still empty: {x}" for x in empty_required(page)]
        problems += [f"Form says this is invalid: {x}" for x in invalid_fields(page)
                     if not any(x[:30] in p for p in problems)]
        page.screenshot(path=str(SHOTS / f"{stamp}_filled.png"), full_page=True)
        (SHOTS / f"{stamp}_answers.json").write_text(json.dumps(
            [{"question": f["label"], "answer": values.get(f["id"], "__SKIP__")} for f in fields],
            indent=1, ensure_ascii=False), encoding="utf-8")
        if essays:
            log(f"  wrote {len(essays)} short written answer(s); see screenshots\\{stamp}_answers.json")
        if problems:
            return "needs you", " | ".join(problems[:4])
        if page.evaluate(CAPTCHA_JS):
            return "needs you", "CAPTCHA appeared"
        if not really_submit:
            return "practice-ok", f"form fully filled, not submitted (screenshot {stamp}_filled.png)"

        btn = page.locator("button, input[type=submit]").filter(has_text=re.compile(r"submit", re.I))
        if not btn.count():
            btn = page.locator("input[type=submit]")
        btn.first.click(timeout=8000)
        page.wait_for_timeout(8000)
        after = page.inner_text("body")
        page.screenshot(path=str(SHOTS / f"{stamp}_after_submit.png"), full_page=True)
        if SUCCESS.search(after):
            return "submitted", f"confirmation shown (screenshot {stamp}_after_submit.png)"
        if VERIFY.search(after):
            return "needs you", "site emailed you a verification code; enter it to finish (browser state saved)"
        if page.evaluate(CAPTCHA_JS):
            return "needs you", "CAPTCHA after clicking submit"
        return "needs you", f"no confirmation seen, check screenshot {stamp}_after_submit.png before re-applying"
    except Exception as e:
        try:
            page.screenshot(path=str(SHOTS / f"{stamp}_error.png"), full_page=True)
        except Exception:
            pass
        return "failed", str(e).splitlines()[0][:200]
    finally:
        page.close()


def record_result(record: dict, result: str, detail: str):
    path = APPS / "submissions.csv"
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "company", "role", "url", "result", "detail"])
        w.writerow([f"{dt.datetime.now():%Y-%m-%d %H:%M}", record.get("company", ""), record.get("title", ""),
                    record["_url"], result, detail])


# ---------------------------------------------------------------- run

def run(really_submit: bool = False, watch: bool = False, only: str = "", log=print) -> dict:
    answers = load_answers()
    if really_submit and not answers.get("auto_submit"):
        log('Real submitting is off. Set "auto_submit": true in answers.json to allow it. Doing a practice run.')
        really_submit = False
    seen = find_jobs.load_seen()
    todo, manual = queue(seen, answers, only)
    todo = todo[: answers.get("max_submissions_per_run", 10)]
    results = {"submitted": [], "practice-ok": [], "needs you": [], "failed": [], "not supported": manual}
    if not todo:
        log("Nothing to auto-submit.")
    else:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=not watch,
                                                       viewport={"width": 1280, "height": 900})
            for r in todo:
                log(f"- {r.get('company')} | {r.get('title')}")
                result, detail = apply_one(ctx, r, answers, really_submit, log)
                log(f"  {result}: {detail}")
                results[result].append((r, detail))
                record_result(r, result, detail)
                if result in ("submitted", "needs you", "failed"):
                    seen[r["_key"]]["status"] = result if result != "failed" else "ready"
                    seen[r["_key"]]["submit_detail"] = detail
                    if result == "submitted":
                        seen[r["_key"]]["submitted_at"] = f"{dt.datetime.now():%Y-%m-%d %H:%M}"
            ctx.close()
        find_jobs.save_seen(seen)
    return results


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", action="store_true", help="really submit (also needs auto_submit true)")
    ap.add_argument("--watch", action="store_true", help="show the browser")
    ap.add_argument("--only", default="", help="one application, by its apply URL")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--folder", default="", help="with --only: use this application folder (for jobs you tailored by hand)")
    args = ap.parse_args()

    if args.list:
        todo, manual = queue(find_jobs.load_seen(), load_answers(), args.only)
        print(f"Can auto-submit ({len(todo)}):")
        for r in todo:
            print(f"  [{r.get('fit')}/10] {r.get('company')} | {r.get('title')}")
        print(f"Not supported, apply yourself ({len(manual)}):")
        for r in manual:
            print(f"  {r.get('company')} | {r.get('title')}\n    {r['_url']}")
        return

    if args.only and args.folder:
        # one-off: an application tailored by hand with tailor.py
        folder = APPS / args.folder
        if not folder.exists():
            sys.exit(f"No folder applications\\{args.folder}")
        notes = json.loads((folder / "notes.json").read_text(encoding="utf-8"))
        seen = find_jobs.load_seen()
        seen[find_jobs.norm_url(args.only)] = {"company": notes.get("company", ""), "title": notes.get("role", ""),
                                               "url": args.only, "apply_url": args.only, "status": "by hand",
                                               "fit": notes.get("fit_score", 0), "folder": args.folder}
        find_jobs.save_seen(seen)

    res = run(args.submit, args.watch, args.only)
    print("\n==== Submit summary ====")
    for k in ("submitted", "practice-ok", "needs you", "failed"):
        if res[k]:
            print(f"{k}: {len(res[k])}")
            for r, d in res[k]:
                print(f"  {r.get('company')} | {r.get('title')}: {d}")
    if res["not supported"]:
        print(f"Apply yourself (Workday / big bank sites): {len(res['not supported'])}")
        for r in res["not supported"]:
            print(f"  {r.get('company')} | {r.get('title')}\n    {r['_url']}")


if __name__ == "__main__":
    main()
