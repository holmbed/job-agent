# Job Agent: tailor

Give it a job posting. It writes a tailored one-page resume and cover letter, scores your fit (1 to 10), lists your gaps, suggests screening answers, and logs everything to `applications/log.csv`.

It only uses facts from `resume_data.json`. It warns you if Claude writes a number that isn't in your resume or the posting, uses a cliche, or writes a letter that's too long or short.

## Every time you open PowerShell

```
cd $HOME\job-agent
.venv\Scripts\activate
```

## Use it

```
# from a link (Lever, Greenhouse, Built In, company career pages)
python tailor.py https://jobs.lever.co/firm/12345

# LinkedIn, Handshake, or any page that fails: paste the posting into a text file
notepad posting.txt
python tailor.py --text posting.txt

# only write files if the fit is 6/10 or better
python tailor.py --min-fit 6 https://...

# test without spending API credit
python tailor.py --dry-run --text sample_posting.txt

# open the results
explorer applications
```

Each run creates `applications\<Company>_<Role>\` with:
- `Daniel_Holmberg_Resume.docx` and `Daniel_Holmberg_Cover_Letter.docx`
- `.pdf` copies of both if Microsoft Word is installed (upload the PDFs when a site accepts them)
- `notes.json` with the fit score, gaps and screening answer ideas
- `posting.txt`, a copy of the posting, since links die

Running the same posting again overwrites its folder.

## Before you submit

Read both files. Check the cover letter sounds like you and every claim is true. Fix anything in Word, then upload.

## Updating your resume

Edit `resume_data.json` (`notepad resume_data.json`), not the Word files. Everything is built from it. `background_for_cover_letters` holds facts Claude may use in cover letters that aren't on the resume.

## First-time setup (already done on this PC)

1. Install Python from python.org with "Add python.exe to PATH" checked.
2. In the project folder: `python -m venv .venv`, then `.venv\Scripts\activate`, then `pip install -r requirements.txt` and `playwright install chromium`.
3. Get an API key at console.anthropic.com and run `setx ANTHROPIC_API_KEY "sk-ant-..."`, then reopen PowerShell.

## Cost

A few cents per posting.

## Save changes to GitHub

```
git add .
git commit -m "describe what you changed"
git push
```
