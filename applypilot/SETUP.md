# ApplyPilot setup (Windows)

ApplyPilot runs separately from job-agent, with its own Python environment. The files in this folder are made for it:
- `resume.txt` is your resume in plain text. The setup wizard asks for it.
- `searches.yaml` searches for summer 2027 wealth management internships anywhere in the US.

## 1. Install Node.js

```
winget install OpenJS.NodeJS.LTS
```
Close PowerShell, open a new one, and check it worked with `node -v`.

## 2. Install Claude Code (ApplyPilot uses it to fill out applications)

```
npm install -g @anthropic-ai/claude-code
claude
```
Log in when it asks. If it offers to use your `ANTHROPIC_API_KEY`, say yes, and that pays from your API credit. Type `/exit` to leave.

## 3. Get a free Gemini API key

ApplyPilot uses Gemini for scoring, resume tailoring and cover letters. Get a key at aistudio.google.com: Get API key > Create API key.

## 4. Install ApplyPilot in its own environment

```
deactivate
cd $HOME
python -m venv applypilot-env
applypilot-env\Scripts\activate
pip install applypilot
pip install --no-deps python-jobspy
pip install pydantic tls-client requests markdownify regex
```

## 5. Run the setup wizard

```
applypilot init
```

Answers to give:

| Question | Answer |
|---|---|
| Resume file path | `C:\Users\axaxe\job-agent\applypilot\resume.txt` |
| Full name | Daniel Holmberg |
| Preferred name | Daniel |
| Email | holmbed@wwu.edu |
| Phone | 425-898-3324 |
| City / State / Country / ZIP | Kirkland / Washington / United States / 98033 |
| Street address | 1730 1st Street |
| LinkedIn | https://www.linkedin.com/in/mrholmberg |
| GitHub, portfolio, website | leave blank |
| Job site password | A NEW password used nowhere else. It gets stored in plain text and used to create accounts on job sites. |
| Authorized to work | y |
| Need sponsorship | n |
| Work permit type | Citizen |
| Expected annual salary | your call (e.g. 40000, roughly $20/hour full time) |
| Currency | USD |
| Acceptable range | e.g. 35000-60000 |
| Current title | Go-to-Market Strategy Intern |
| Target role | Private Wealth Management Intern |
| Years of experience | 0 |
| Highest education | Bachelor's (in progress, expected June 2028) |
| Programming languages / frameworks | leave blank |
| Tools | Excel, PowerPoint, AI tools |
| Companies to keep | Tupl Inc., DERU Market, Virke |
| Projects to keep | Monte Carlo Simulation on NASDAQ Stock Performance, Five-Year P&L Forecasting Model, Goldman Sachs Operations Job Simulation |
| School | Western Washington University |
| Metrics to keep | 41 senior decision-makers, 10 target accounts, 190-site T-Mobile deployment, 5 international markets, 2,000+ data points, 9 business units, 3,000 students, $20 pay-per-lead |
| Earliest start date | June 2027 |
| Target location / radius / titles | anything, these get replaced in step 6 |
| AI provider | gemini, then paste your Gemini key, then press Enter for the default model |
| Enable auto-apply | y |
| CapSolver | n |

## 6. Swap in the internship search config

The wizard writes a basic search file. Replace it with this one:
```
copy $HOME\job-agent\applypilot\searches.yaml $HOME\.applypilot\searches.yaml
```

## 7. Check the setup

```
applypilot doctor
```

## 8. Find, score and tailor

```
applypilot run
```
Results: `applypilot status` and `applypilot dashboard`. Tailored files are in `C:\Users\axaxe\.applypilot\`.

## 9. Practice applying (fills forms, does NOT submit)

```
applypilot apply --dry-run --model sonnet
```

## 10. Apply for real

```
applypilot apply --model sonnet
```

`--model sonnet` is better than the default (haiku) at multi-page Workday forms.

## Every time you open PowerShell

```
cd $HOME
applypilot-env\Scripts\activate
```
