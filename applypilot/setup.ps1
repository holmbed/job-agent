# One-step ApplyPilot setup on a Windows PC. Safe to run again.
#   powershell -ExecutionPolicy Bypass -File $HOME\job-agent\applypilot\setup.ps1
$ErrorActionPreference = "Stop"
$env:PATH += ";C:\Program Files\nodejs;$env:APPDATA\npm;C:\Program Files\Git\cmd"
$src = "$HOME\job-agent\applypilot"
$app = "$HOME\.applypilot"

Write-Host "`n[1/5] Checking Python, Node and Claude Code..."
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { throw "Python is not installed. Install it from python.org with 'Add python.exe to PATH' checked, then run this again." }
python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is needed'"
node --version
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { npm install -g @anthropic-ai/claude-code }

Write-Host "`n[2/5] Creating the ApplyPilot environment (takes a few minutes the first time)..."
Set-Location $HOME
if (-not (Test-Path "$HOME\applypilot-env")) { python -m venv applypilot-env }
& "$HOME\applypilot-env\Scripts\Activate.ps1"
python -m pip install --quiet --upgrade pip
pip install --quiet applypilot
pip install --quiet --no-deps python-jobspy
pip install --quiet pydantic tls-client requests markdownify regex curl_cffi
python -c "import jobspy, applypilot; print('ApplyPilot installed')"

Write-Host "`n[3/5] Patching ApplyPilot for Claude and Windows..."
python "$src\fix_applypilot.py"

Write-Host "`n[4/5] Copying your profile, resume and search settings..."
New-Item -ItemType Directory -Force -Path $app | Out-Null
Copy-Item "$src\resume.txt" "$app\resume.txt" -Force
Copy-Item "$src\searches.yaml" "$app\searches.yaml" -Force
Copy-Item "$src\env.txt" "$app\.env" -Force
if (Test-Path "$app\profile.json") {
    Write-Host "profile.json already exists, keeping yours (it has your password)."
} else {
    Copy-Item "$src\profile.json" "$app\profile.json"
}

Write-Host "`n[5/5] Checking setup..."
applypilot doctor

Write-Host "`nStill to do by hand:"
if (-not $env:LLM_API_KEY) { Write-Host "  - Set your API key:  setx LLM_API_KEY `"your-key`"   then reopen PowerShell" }
if ((Get-Content "$app\profile.json" -Raw) -match '"password":\s*""') {
    Write-Host "  - Set a job site password:  notepad $app\profile.json   (fill in `"password`")"
}
Write-Host "  - Sign in to Indeed once (see SETUP.md step 4)"
