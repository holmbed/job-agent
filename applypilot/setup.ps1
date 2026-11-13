# One-step ApplyPilot setup on a Windows PC. Safe to run again.
#   powershell -ExecutionPolicy Bypass -File $HOME\job-agent\applypilot\setup.ps1
$ErrorActionPreference = "Stop"
$env:PATH += ";C:\Program Files\nodejs;$env:APPDATA\npm;C:\Program Files\Git\cmd"
$src = "$HOME\job-agent\applypilot"
$app = "$HOME\.applypilot"
$venv = "$HOME\applypilot-env"

function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE). Stopping." } }

function Find-Python {
    # Try every likely Python and keep the first one that actually runs and is 3.11-3.13.
    $candidates = @()
    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python31*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName
    $candidates += Get-ChildItem "C:\Program Files\Python31*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName
    foreach ($c in (Get-Command python, python3 -All -ErrorAction SilentlyContinue)) { $candidates += $c.Source }
    foreach ($p in $candidates | Select-Object -Unique) {
        if ($p -like "*WindowsApps*") { continue }   # Microsoft Store shortcut, not a real Python
        try {
            $ErrorActionPreference = "Continue"
            $v = & $p -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v -match '^3\.(1[1-3])$') { return $p }
        } catch {} finally { $ErrorActionPreference = "Stop" }
    }
    return $null
}

Write-Host "`n[1/5] Checking Python, Node and Claude Code..."
$py = Find-Python
if (-not $py) {
    throw "No working Python 3.11-3.13 found. Run:  winget install Python.Python.3.12   then close PowerShell, open a new one, and run this script again."
}
Write-Host "Using Python: $py"
node --version; Check "Node check"
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { npm install -g @anthropic-ai/claude-code; Check "Claude Code install" }

Write-Host "`n[2/5] Creating the ApplyPilot environment (takes a few minutes the first time)..."
$vpy = "$venv\Scripts\python.exe"
$healthy = $false
if (Test-Path $vpy) {
    try {
        $ErrorActionPreference = "Continue"
        & $vpy -m pip --version *> $null
        $healthy = ($LASTEXITCODE -eq 0)
    } catch { $healthy = $false } finally { $ErrorActionPreference = "Stop" }
}
if (-not $healthy) {
    if (Test-Path $venv) { Write-Host "Existing environment is broken, rebuilding it."; Remove-Item -Recurse -Force $venv }
    & $py -m venv $venv; Check "Creating the environment"
}
& $vpy -m pip install --quiet --upgrade pip; Check "pip upgrade"
& $vpy -m pip install --quiet applypilot; Check "Installing ApplyPilot"
& $vpy -m pip install --quiet --no-deps python-jobspy; Check "Installing python-jobspy"
& $vpy -m pip install --quiet pydantic tls-client requests markdownify regex curl_cffi; Check "Installing extras"
& $vpy -c "import jobspy, applypilot; print('ApplyPilot installed')"; Check "ApplyPilot import"

Write-Host "`n[3/5] Patching ApplyPilot for Claude and Windows..."
& $vpy "$src\fix_applypilot.py"; Check "Patching"

Write-Host "`n[4/5] Copying your profile, resume and search settings..."
New-Item -ItemType Directory -Force -Path "$app\logs" | Out-Null
Copy-Item "$src\resume.txt" "$app\resume.txt" -Force
Copy-Item "$src\searches.yaml" "$app\searches.yaml" -Force
Copy-Item "$src\env.txt" "$app\.env" -Force
if (Test-Path "$app\profile.json") {
    Write-Host "profile.json already exists, keeping yours (it has your password)."
} else {
    Copy-Item "$src\profile.json" "$app\profile.json"
}

Write-Host "`n[5/5] Checking setup..."
& "$venv\Scripts\applypilot.exe" doctor

Write-Host "`nSetup finished. Still to do by hand:"
$key = [Environment]::GetEnvironmentVariable("LLM_API_KEY", "User")
if (-not $key -and -not $env:LLM_API_KEY) { Write-Host "  - Set your API key:  setx LLM_API_KEY `"your-key`"   then reopen PowerShell" }
if ((Get-Content "$app\profile.json" -Raw) -match '"password":\s*""') {
    Write-Host "  - Set a job site password:  notepad $app\profile.json   (fill in `"password`")"
}
Write-Host "  - Sign in to Indeed once (SETUP.md step 4)"
