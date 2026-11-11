# Job Agent

Finds wealth management internships and writes a tailored one-page resume and cover letter for each one. It scores your fit from 1 to 10, lists your gaps, and suggests screening answers. On Lever, Greenhouse and Ashby it can also submit the application for you.

It only uses facts from `resume_data.json`. It warns you if Claude writes a number that isn't in your resume or the posting, uses a cliche, or writes a letter that's too long or too short.

## Every time you open PowerShell

```
cd $HOME\job-agent
.venv\Scripts\activate
```

## The daily run (find + tailor)

```
python run.py                 # find new jobs, tailor each one, print a summary
python run.py --no-web        # skip the paid web search, job board feeds only
python run.py --max 5         # tailor at most 5 this run
python run.py --min-fit 7     # only keep applications scoring 7/10+ (default 6)
python run.py --dry-run       # find jobs without paying for tailoring
```

Where jobs come from:
1. **Job board feeds** for the firms in `firms.json` (Lever, Greenhouse, Ashby). Free and reliable.
2. **Claude web search** for everything else (big banks, Workday sites). About $0.10 to $0.40 per run.

Each run:
- skips anything already handled, including postings you ran `tailor.py` on by hand
- saves a summary to `applications\runs\`
- tracks every job in `applications\seen.json` and `applications\log.csv`

Statuses in `log.csv`:
- `ready`: tailored, no warnings. Read it and submit.
- `needs review`: tailored, but a check flagged something. Fix it first.
- `skipped (fit N)`: below your minimum fit. No files written.

Pages the agent can't read land on a "Need you" list in the summary. Use `tailor.py --text` for those.

## Auto-submit (Lever, Greenhouse, Ashby)

One-time setup:
```
copy answers.example.json answers.json
notepad answers.json
```
Fill in every `FILL_ME`. Check every answer, because these go on real applications. `answers.json` stays on your PC and is not uploaded to GitHub.

```
python submit.py --list            # what's queued, and what you must apply to yourself
python submit.py --watch           # practice: fills each form while you watch, does NOT submit
python submit.py                   # practice, no window
python submit.py --submit          # really submit (needs "auto_submit": true in answers.json)
python submit.py --only URL --watch   # one application
```

Once `"auto_submit": true` is set, `python run.py` finds, tailors and submits in one go.

The submitter never guesses. It stops and puts the application on your "needs you" list when:
- a required question has no answer in `answers.json`, your resume or your cover letter
- a CAPTCHA appears
- the site wants an account or login
- it can't confirm the submission went through

Workday and big bank sites always land on the "apply yourself" list.

Records it keeps:
- `applications\screenshots\`: the filled form, the confirmation page, and every question with the answer it gave
- `applications\submissions.csv`: every attempt and its result

Settings in `answers.json`:
- `min_fit_to_submit` (default 7)
- `max_submissions_per_run` (default 10)

## Find jobs only

```
python find_jobs.py               # list new matches, tailor nothing
python find_jobs.py --check-firms # test every firm in firms.json
```

To add a firm, find its job board link and add a line to `firms.json`:
- `jobs.lever.co/NAME` -> `"ats": "lever", "token": "NAME"`
- `job-boards.greenhouse.io/NAME` -> `"ats": "greenhouse", "token": "NAME"`
- `jobs.ashbyhq.com/NAME` -> `"ats": "ashby", "token": "NAME"`

## Run it automatically every morning

```
schtasks /create /tn "JobAgent" /tr "$HOME\job-agent\run_daily.bat" /sc daily /st 08:30
```

- Your PC must be on and you must be logged in at that time.
- The output goes to `logs\daily.log`.
- To run the task now: `schtasks /run /tn "JobAgent"`
- To remove it: `schtasks /delete /tn "JobAgent" /f`

## Tailor one posting by hand

```
python tailor.py https://jobs.lever.co/firm/12345
notepad posting.txt                     # for LinkedIn, Handshake, or pages that fail
python tailor.py --text posting.txt
python tailor.py --dry-run --text sample_posting.txt
explorer applications
```

Each application folder `applications\<Company>_<Role>\` has:
- `Daniel_Holmberg_Resume.docx` and `Daniel_Holmberg_Cover_Letter.docx`
- `.pdf` copies of both if Microsoft Word is installed
- `notes.json` with the fit score, gaps and screening answer ideas
- `posting.txt`, a copy of the posting, since links die

## Before you submit

Read both files. Check that the cover letter sounds like you and that every claim is true. Fix anything in Word, then upload.

## Updating your resume

Edit `resume_data.json` (`notepad resume_data.json`), not the Word files. Everything is built from it. `background_for_cover_letters` holds facts Claude may use in cover letters that aren't on the resume.

## First-time setup (already done on this PC)

1. Install Python from python.org with "Add python.exe to PATH" checked.
2. In the project folder, run `python -m venv .venv`, then `.venv\Scripts\activate`, then `pip install -r requirements.txt` and `playwright install chromium`.
3. Get an API key at console.anthropic.com and run `setx ANTHROPIC_API_KEY "sk-ant-..."`, then reopen PowerShell.

## Cost

- A few cents per tailored application.
- Up to about $0.40 per day for web search.
- A daily run with 15 applications costs roughly $1.

## Save changes to GitHub

```
git add .
git commit -m "describe what you changed"
git push
```
