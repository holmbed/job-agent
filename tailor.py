"""
Job application tailor.

Give it a job posting (URL or a saved text file). It:
  1. Pulls the posting text.
  2. Asks Claude to score the fit, then tailor your resume and write a cover letter,
     using ONLY facts from resume_data.json.
  3. Checks the output for numbers that are not in your real resume (made-up stats).
  4. Saves resume.docx, cover_letter.docx and notes.json in applications/<company>_<role>/
     and adds a row to applications/log.csv.

Usage:
  python tailor.py https://boards.greenhouse.io/somefirm/jobs/123
  python tailor.py --text posting.txt
  python tailor.py --dry-run --text posting.txt      (no API call, just tests the files)
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT_DIR = HERE / "applications"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")


# ---------------------------------------------------------------- 1. get the posting

def fetch_posting(url: str) -> str:
    """Plain request first; if the page is mostly JavaScript (Workday etc.), render it in a browser."""
    text = ""
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
    except Exception as e:
        print(f"  plain fetch failed ({e}), trying a real browser")

    if len(text) < 1500:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            text = page.inner_text("body")
            browser.close()

    if len(text) < 500:
        sys.exit("Could not read the posting from that link. Copy the posting into a .txt file and use --text.")
    return text[:30000]


# ---------------------------------------------------------------- 2. ask Claude

SYSTEM = """You tailor job applications for one real candidate. Hard rules:
- Use ONLY facts in the candidate's resume data. Never invent employers, titles, dates, numbers, tools, certifications, or results.
- You may reword, reorder, shorten, and choose which bullets and projects to include, and you may rename the skills list to match the posting's vocabulary only where the candidate truly has that skill.
- Every number you write must already appear in the resume data.
- Never use em dashes or en dashes in prose. Use commas, periods, or parentheses.
- Cover letter: 3 paragraphs, 180 to 260 words. Write like a sharp, direct college student, short sentences, no corporate filler.
  Paragraph 1: why this role and firm, in 2 or 3 sentences. Use a specific detail from the posting. Do not open with a generic career statement.
  Paragraph 2: pick the 2 strongest proof points for THIS posting and tie each one to a duty the posting lists. Do not recap the resume or list projects.
  Paragraph 3: one distinctive angle the resume only hints at (languages for serving more clients, founding Latinos in Finance, building a startup), then a one-sentence close.
  Never mention GPA, course grades, or the word "passionate". Banned: "I am excited", "thrilled", "leverage", "fast-paced", "great fit", "the best place", "I also understand", "tools I already use", "would welcome the chance".
  Do NOT include a sign-off or the candidate's name; the template adds them.
- Resume must fit on one page: at most 15 bullets total. At most 3 bullets per job, at most 3 projects with 2 bullets each (you may merge Challenge/Solution/Impact), at most 2 course bullets, 1 bullet per leadership entry. Keep bullets under 22 words. Drop the least relevant entries rather than squeezing.
- Be honest in fit_score. A sophomore/junior applying to a role that requires a degree, licenses (SIE, Series 7, 66) already held, or years of experience is a low score."""

TOOL = {
    "name": "submit_application",
    "description": "Return the tailored application package.",
    "input_schema": {
        "type": "object",
        "required": ["company", "role", "location", "fit_score", "fit_reasons", "gaps",
                     "skills", "experience", "entrepreneurship", "projects", "leadership",
                     "courses", "cover_letter"],
        "properties": {
            "company": {"type": "string"},
            "role": {"type": "string"},
            "location": {"type": "string"},
            "deadline": {"type": "string", "description": "Application deadline if stated, else empty"},
            "fit_score": {"type": "integer", "minimum": 1, "maximum": 10},
            "fit_reasons": {"type": "array", "items": {"type": "string"}},
            "gaps": {"type": "array", "items": {"type": "string"},
                     "description": "Requirements in the posting the candidate does not meet"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "experience": {"$ref": "#/$defs/section"},
            "entrepreneurship": {"$ref": "#/$defs/section"},
            "projects": {"$ref": "#/$defs/section"},
            "leadership": {"$ref": "#/$defs/section"},
            "courses": {"$ref": "#/$defs/section"},
            "cover_letter": {"type": "string",
                             "description": "Body paragraphs only, separated by blank lines. No date, address block, greeting, sign-off, or name."},
            "screening_notes": {"type": "array", "items": {"type": "string"},
                                "description": "Short suggested answers to any screening questions visible in the posting"}
        },
        "$defs": {
            "section": {
                "type": "array",
                "description": "Entries to include, most relevant first. Use ids from the resume data.",
                "items": {
                    "type": "object",
                    "required": ["id", "bullets"],
                    "properties": {
                        "id": {"type": "string"},
                        "bullets": {"type": "array", "items": {"type": "string"}}
                    }
                }
            }
        }
    }
}


def ask_claude(posting: str, resume: dict) -> dict:
    import anthropic
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    msg = client.messages.create(
        model=MODEL,
        max_tokens=6000,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "auto"},
        messages=[{
            "role": "user",
            "content": f"<resume_data>\n{json.dumps(resume, indent=1)}\n</resume_data>\n\n"
                       f"<job_posting>\n{posting}\n</job_posting>\n\n"
                       "Tailor the application for this posting. Return it by calling the submit_application tool. Do not reply with plain text."
        }],
    )
    for block in msg.content:
        if block.type == "tool_use":
            return block.input
    sys.exit("Claude did not return an application package.")


def dry_run_package(resume: dict) -> dict:
    """Untailored package straight from resume_data.json, for testing without an API key."""
    sec = lambda key, n=3: [{"id": e["id"], "bullets": e["bullets"][:n]} for e in resume[key]]
    return {
        "company": "Test Firm", "role": "Test Role", "location": "", "deadline": "",
        "fit_score": 0, "fit_reasons": ["dry run"], "gaps": [],
        "skills": resume["skills"], "experience": sec("experience"),
        "entrepreneurship": sec("entrepreneurship"), "projects": sec("projects", 2)[:3],
        "leadership": sec("leadership"), "courses": sec("courses", 2),
        "cover_letter": "Dry run paragraph one.\n\nDry run paragraph two.",
        "screening_notes": [],
    }


# ---------------------------------------------------------------- 3. fact check

def numbers_in(text: str) -> set:
    return set(re.findall(r"\d[\d,.]*\d|\d", text))


def fact_check(pkg: dict, resume: dict, posting: str = "") -> list:
    """Flag any number in the output that is not in the real resume."""
    allowed = numbers_in(json.dumps(resume, ensure_ascii=False)) | numbers_in(posting)
    written = json.dumps({k: pkg[k] for k in ("skills", "experience", "entrepreneurship",
                                               "projects", "leadership", "courses", "cover_letter")}, ensure_ascii=False)
    invented = sorted(n for n in numbers_in(written) if n not in allowed)
    known_ids = {e["id"] for k in ("experience", "entrepreneurship", "projects", "leadership", "courses")
                 for e in resume[k]}
    bad_ids = [e["id"] for k in ("experience", "entrepreneurship", "projects", "leadership", "courses")
               for e in pkg.get(k, []) if e["id"] not in known_ids]
    problems = []
    if invented:
        problems.append(f"Numbers not in your resume: {', '.join(invented)}")
    if bad_ids:
        problems.append(f"Unknown entries: {', '.join(bad_ids)}")
    return problems


def strip_dashes(s: str) -> str:
    """Backstop for the no-em-dash rule (bullets and cover letter only, not dates)."""
    s = re.sub(r"\s*—\s*", ", ", s)
    return re.sub(r"(?<=[A-Za-z])\s+–\s+(?=[A-Za-z])", ", ", s)


# ---------------------------------------------------------------- 4. write the files

def build_resume_docx(pkg: dict, resume: dict, path: Path):
    from docx import Document
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, Inches, RGBColor

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(0.55)
    sec.top_margin = sec.bottom_margin = Inches(0.5)
    right_edge = sec.page_width - sec.left_margin - sec.right_margin

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.line_spacing = 1.0

    def para(text="", bold=False, italic=False, size=None, align=None, after=0):
        p = doc.add_paragraph()
        if text:
            r = p.add_run(text)
            r.bold, r.italic = bold, italic
            if size:
                r.font.size = Pt(size)
        if align:
            p.alignment = align
        p.paragraph_format.space_after = Pt(after)
        return p

    def heading(text):
        p = para(text.upper(), bold=True, size=11)
        p.paragraph_format.space_before = Pt(7)
        p.paragraph_format.space_after = Pt(2)
        pPr = p._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "000000")):
            bottom.set(qn(k), v)
        bdr.append(bottom)
        pPr.append(bdr)

    def line_with_date(left_bold, left_rest, date):
        p = para()
        p.paragraph_format.tab_stops.add_tab_stop(right_edge, WD_TAB_ALIGNMENT.RIGHT)
        r = p.add_run(left_bold)
        r.bold = True
        if left_rest:
            p.add_run(left_rest)
        if date:
            p.add_run("\t" + date)
        p.paragraph_format.space_before = Pt(3)
        return p

    def bullet(text):
        p = para()
        p.paragraph_format.left_indent = Inches(0.2)
        p.paragraph_format.first_line_indent = Inches(-0.15)
        p.add_run("•  " + text)

    # header
    para(resume["name"], bold=True, size=18, align=WD_ALIGN_PARAGRAPH.CENTER)
    para("  •  ".join(resume["contact"]), size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER)

    heading("Education")
    for ed in resume["education"]:
        line_with_date(ed["school"], f", {ed['location']}", ed["date"])
        para(f"{ed['degree']}  •  GPA: {ed['gpa']}", italic=True)
    p = para()
    p.add_run("Relevant Skills: ").bold = True
    p.add_run(", ".join(pkg["skills"]))

    lookup = {e["id"]: e for k in ("experience", "entrepreneurship", "projects", "leadership", "courses")
              for e in resume[k]}
    titles = [("experience", "Work Experience"), ("entrepreneurship", "Entrepreneurship"),
              ("projects", "Highlighted Projects"), ("leadership", "Leadership and Involvement"),
              ("courses", "Courses")]
    for key, title in titles:
        entries = [e for e in pkg.get(key, []) if e["id"] in lookup]
        if not entries:
            continue
        heading(title)
        for e in entries:
            src = lookup[e["id"]]
            loc = f", {src['location']}" if src.get("location") else ""
            line_with_date(src["title"], f"  •  {src['org']}{loc}", src["date"])
            for b in e["bullets"]:
                bullet(strip_dashes(b))

    heading("Additional Information")
    for k, v in resume["additional"].items():
        p = para()
        p.add_run(f"{k}: ").bold = True
        p.add_run(v)

    doc.save(path)


def build_cover_letter_docx(pkg: dict, resume: dict, path: Path):
    from docx import Document
    from docx.shared import Pt, Inches

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(1)
    sec.top_margin = sec.bottom_margin = Inches(1)
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(11)
    st.paragraph_format.space_after = Pt(10)

    doc.add_paragraph(resume["name"]).runs[0].bold = True
    doc.add_paragraph("  •  ".join(resume["contact"]))
    doc.add_paragraph(dt.date.today().strftime("%B %d, %Y").replace(" 0", " "))
    doc.add_paragraph(f"{pkg['company']} Hiring Team")
    doc.add_paragraph(f"Re: {pkg['role']}")
    doc.add_paragraph("Dear Hiring Team,")
    for chunk in [c.strip() for c in pkg["cover_letter"].split("\n\n") if c.strip() and c.strip().rstrip(",") not in (resume["name"], "Sincerely", "Best", "Best regards", "Daniel Holmberg")]:
        doc.add_paragraph(strip_dashes(chunk))
    doc.add_paragraph("Sincerely,")
    doc.add_paragraph(resume["name"])
    doc.save(path)


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:40] or "job"


def log_row(pkg: dict, source: str, folder: Path, problems: list):
    OUT_DIR.mkdir(exist_ok=True)
    log = OUT_DIR / "log.csv"
    new = not log.exists()
    with log.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "company", "role", "location", "deadline", "fit_score",
                        "source", "folder", "fact_check", "status"])
        w.writerow([dt.date.today().isoformat(), pkg["company"], pkg["role"], pkg.get("location", ""),
                    pkg.get("deadline", ""), pkg["fit_score"], source, folder.name,
                    "; ".join(problems) or "ok", "drafted"])


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Tailor a resume and cover letter to one job posting.")
    ap.add_argument("url", nargs="?", help="Job posting URL")
    ap.add_argument("--text", help="Path to a .txt file with the posting pasted in")
    ap.add_argument("--dry-run", action="store_true", help="Skip Claude, just test file output")
    ap.add_argument("--min-fit", type=int, default=0, help="Skip writing files if fit score is below this")
    args = ap.parse_args()

    if not args.url and not args.text:
        ap.error("give a URL or --text posting.txt")

    resume = json.loads((HERE / "resume_data.json").read_text(encoding="utf-8"))

    print("Reading posting...")
    posting = Path(args.text).read_text(encoding="utf-8", errors="replace") if args.text else fetch_posting(args.url)
    source = args.url or args.text

    if args.dry_run:
        pkg = dry_run_package(resume)
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("Set ANTHROPIC_API_KEY first (see README).")
        print(f"Tailoring with {MODEL}...")
        pkg = ask_claude(posting, resume)

    print(f"\n{pkg['company']} | {pkg['role']} | fit {pkg['fit_score']}/10")
    for r in pkg.get("fit_reasons", []):
        print(f"  + {r}")
    for g in pkg.get("gaps", []):
        print(f"  - {g}")

    if pkg["fit_score"] < args.min_fit:
        print(f"\nBelow --min-fit {args.min_fit}, skipped.")
        return

    problems = fact_check(pkg, resume, posting)
    for p in problems:
        print(f"  WARNING: {p}")

    folder = OUT_DIR / f"{slug(pkg['company'])}_{slug(pkg['role'])}"
    folder.mkdir(parents=True, exist_ok=True)
    build_resume_docx(pkg, resume, folder / "Daniel_Holmberg_Resume.docx")
    build_cover_letter_docx(pkg, resume, folder / "Daniel_Holmberg_Cover_Letter.docx")
    (folder / "posting.txt").write_text(posting, encoding="utf-8")
    (folder / "notes.json").write_text(json.dumps({**pkg, "source": source, "fact_check": problems}, indent=2, ensure_ascii=False), encoding="utf-8")
    log_row(pkg, source, folder, problems)

    print(f"\nSaved to {folder}")


if __name__ == "__main__":
    main()
