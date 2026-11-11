# Daily ApplyPilot run: find, score, keep only wealth management roles, tailor, apply.
# Run by hand:      powershell -ExecutionPolicy Bypass -File $HOME\job-agent\applypilot\daily.ps1
# Max applications per run is set by -Limit (default 10).
param([int]$Limit = 10)

$env:PATH += ";C:\Program Files\nodejs;$env:APPDATA\npm;C:\Program Files\Git\cmd"
Set-Location $HOME
& "$HOME\applypilot-env\Scripts\Activate.ps1"
$log = "$HOME\.applypilot\logs\daily_$(Get-Date -Format yyyy-MM-dd_HHmm).txt"

& {
    "=== $(Get-Date) ApplyPilot daily run ==="
    applypilot run discover enrich score
    python "$HOME\job-agent\applypilot\keep_pwm_only.py"
    applypilot run tailor cover pdf --min-score 7
    applypilot apply --model sonnet --min-score 7 --limit $Limit
    applypilot status
} *>&1 | Tee-Object -FilePath $log
