# Job Agent, step 1: tailor

You give it a job posting. It writes a tailored one-page resume and cover letter, scores how well you fit (1 to 10), lists the gaps, and logs everything to `applications/log.csv`.

It only uses facts from `resume_data.json`. If Claude writes a number that isn't in your real resume, the script prints a WARNING and records it in the log.

## Setup (one time)

```bash
cd job-agent
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium          # only needed for JavaScript-heavy job sites
```

Get an API key at console.anthropic.com (add about $5 of credit), then:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
```

## Use it

```bash
# from a link (Greenhouse, Lever, company career pages)
python tailor.py https://job-boards.greenhouse.io/firm/jobs/12345

# LinkedIn, Handshake, or anything behind a login: copy the posting into a .txt file
python tailor.py --text posting.txt

# only write files if the fit is 6/10 or better
python tailor.py --min-fit 6 https://...

# test without spending API credit
python tailor.py --dry-run --text sample_posting.txt
```

Output goes to `applications/<Company>_<Role>/`:
- `Daniel_Holmberg_Resume.docx`
- `Daniel_Holmberg_Cover_Letter.docx`
- `notes.json` (fit score, gaps, suggested screening answers)
- `posting.txt` (copy of the posting, since links die)

## Updating your resume

Edit `resume_data.json`, not the .docx files. Everything is built from it.
`background_for_cover_letters` holds facts Claude can use in cover letters but that don't appear on the resume.

## Cost

Roughly 3 to 6 cents per posting with the default model. Change it with `export CLAUDE_MODEL=...`.

## Next steps

- Step 2: a job finder that pulls PWM internship postings into a list.
- Step 3: a browser agent that fills in the application forms.
