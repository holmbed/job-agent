# ApplyPilot setup (Windows)

ApplyPilot finds finance internships, tailors a resume and cover letter for each, and submits the applications. It runs separately from job-agent, in its own Python environment.

The files in this folder are made for it:
- `setup.ps1` installs and configures everything in one go
- `fix_applypilot.py` patches ApplyPilot to work with current Claude models and on Windows
- `profile.json` holds your details for application forms (no password; you add that on each PC)
- `resume.txt` is your resume as plain text
- `searches.yaml` searches for summer 2027 undergrad finance internships anywhere in the US, wealth management first
- `env.txt` tells ApplyPilot to use Claude
- `keep_finance_only.py` drops anything that isn't an undergrad finance internship (Sales, Tech, MBA roles, full-time jobs) before it costs anything
- `daily.ps1` is the full daily run: search, filter, score, tailor, apply

## 1. Run the setup script

Needs Python 3.11+, Node.js 22+ and Git.
```
cd $HOME\job-agent
git pull
powershell -ExecutionPolicy Bypass -File $HOME\job-agent\applypilot\setup.ps1
```
It ends with a list of what's still to do by hand. That list is steps 2 to 4 below.

## 2. API key

ApplyPilot uses your Claude API key (from console.anthropic.com > API Keys) for scoring (Haiku, cheap) and tailoring and cover letters (Sonnet). Type it into PowerShell, never into a chat:
```
setx LLM_API_KEY "your-key"
```
Close and reopen PowerShell afterwards.

## 3. Job site password

```
notepad $HOME\.applypilot\profile.json
```
Put a NEW password, used nowhere else, between the quotes in `"password": "",` and save. It's stored in plain text and used to create accounts on job sites.

## 4. Sign in to job sites once

ApplyPilot uses its own Chrome profile and remembers sign-ins. Open it and sign in to Indeed:
```
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="$HOME\.applypilot\chrome-workers\worker-0" https://secure.indeed.com/auth
```
Close that Chrome window when done. Do the same for any site that later fails with LOGIN_ISSUE.

## 5. Run it

```
powershell -ExecutionPolicy Bypass -File $HOME\job-agent\applypilot\daily.ps1 -Limit 5
```
`-Limit` is the most applications it submits in one run.

## 6. Schedule it every morning

```
schtasks /create /tn "ApplyPilot" /tr "powershell -ExecutionPolicy Bypass -File $HOME\job-agent\applypilot\daily.ps1" /sc daily /st 09:00
```
The PC must be on and you must be logged in at that time. Each run's log is in `$HOME\.applypilot\logs\daily_*.txt`.

## Useful commands

Run these after `cd $HOME` and `applypilot-env\Scripts\activate`:
```
applypilot status                                  # counts at each stage
applypilot dashboard                               # results in the browser
applypilot apply --dry-run --model sonnet          # fill one form without submitting
applypilot apply --reset-failed                    # retry failed applications
python $HOME\job-agent\applypilot\keep_finance_only.py   # list roles scoring 7+
```

## Cost

Ways to keep it down:
- **Spending limit:** set a monthly limit at console.anthropic.com > Settings > Limits. ApplyPilot stops when it's hit. This is the only hard cap.
- **`-MinScore`:** the daily script only tailors and applies to jobs scoring 8+ by default. `-MinScore 9` is cheaper; `-MinScore 7` applies more widely and costs more.
- **Scoring runs on Haiku,** which is cheap. Only jobs that pass the score get Sonnet for tailoring.
- **Applying runs through Claude Code.** If Claude Code is logged in with a Pro or Max plan and `ANTHROPIC_API_KEY` is not set on the PC, submitting is covered by the plan instead of API credit (plan usage limits apply).
- **Later runs are cheaper:** only new postings get scored and tailored.

Rough API cost per run: about 1 cent per job scored, 10 to 20 cents per job tailored.
