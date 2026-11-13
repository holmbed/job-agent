# Daily ApplyPilot run: find, keep only undergrad finance internships, score, tailor, apply.
#   powershell -ExecutionPolicy Bypass -File $HOME\job-agent\applypilot\daily.ps1 -Limit 1000
#
# Cost controls:
#   -Limit      most applications submitted this run (default 10)
#   -MinScore   only tailor and apply to jobs scoring at least this (default 8; 7 = more jobs, more cost)
#   -SkipSearch skip the job search and just finish scoring, tailoring and applying what is already found
#   Scoring uses Claude Haiku (cheap, runs on every job). Tailoring and cover letters use Sonnet
#   (better writing, only runs on jobs that pass -MinScore).
param([int]$Limit = 10, [int]$MinScore = 8, [switch]$SkipSearch)

$env:PATH += ";C:\Program Files\nodejs;$env:APPDATA\npm;C:\Program Files\Git\cmd"
# Job titles can contain emoji and non-English characters; make Python and the console use UTF-8
# so printing them can't crash a stage.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:TERM = "xterm-256color"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; chcp 65001 > $null } catch {}
Set-Location $HOME
if (-not (Test-Path "$HOME\applypilot-env\Scripts\applypilot.exe")) {
    Write-Host "ApplyPilot isn't installed yet. Run setup.ps1 first (see SETUP.md)."; exit 1
}
& "$HOME\applypilot-env\Scripts\Activate.ps1"

# Stop now if the Claude API key is missing or rejected, instead of failing every job.
$keyCheck = python -c "import os,httpx,pathlib,dotenv;dotenv.load_dotenv(pathlib.Path.home()/'.applypilot'/'.env');k=os.environ.get('LLM_API_KEY','').strip();print('missing' if not k else httpx.post('https://api.anthropic.com/v1/chat/completions',headers={'Authorization':'Bearer '+k},json={'model':'claude-haiku-5-5','messages':[{'role':'user','content':'hi'}],'max_tokens':5},timeout=60).status_code)"
if ($keyCheck -ne "200") {
    Write-Host "Claude API key problem ($keyCheck). LLM_API_KEY is missing or rejected in this window."
    Write-Host "Fix: run  notepad $HOME\.applypilot\.env  and add a line  LLM_API_KEY=your-key  (no quotes), save, then open a NEW PowerShell window."
    exit 1
}
New-Item -ItemType Directory -Force -Path "$HOME\.applypilot\logs" | Out-Null
$log = "$HOME\.applypilot\logs\daily_$(Get-Date -Format yyyy-MM-dd_HHmm).txt"
$filter = "$HOME\job-agent\applypilot\keep_finance_only.py"

& {
    "=== $(Get-Date) ApplyPilot daily run (limit $Limit, min score $MinScore, skip search: $SkipSearch) ==="
    if (-not $SkipSearch) {
        applypilot run discover
        python $filter
    }

    $env:LLM_MODEL = "claude-haiku-5-5"
    applypilot run enrich score
    python $filter

    $env:LLM_MODEL = "claude-sonnet-5-5"
    applypilot run tailor cover pdf --min-score $MinScore
    applypilot apply --model sonnet --min-score $MinScore --limit $Limit
    applypilot status
} *>&1 | Tee-Object -FilePath $log
