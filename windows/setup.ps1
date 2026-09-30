# One-time developer setup for JARVIS on Windows.
#   powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Find-Python {
    foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "py", "python")) {
        try {
            if ($c -eq "py") { $v = & py -3.12 --version 2>$null; if ($LASTEXITCODE -eq 0) { return @("py", "-3.12") } }
            else { $v = & $c --version 2>$null; if ($LASTEXITCODE -eq 0 -and $v -match "3\.1[1-3]") { return @($c) } }
        } catch {}
    }
    return $null
}

Write-Host "== JARVIS setup ==" -ForegroundColor Cyan
$py = Find-Python
if (-not $py) {
    Write-Host "Python 3.12 not found - installing with winget..." -ForegroundColor Yellow
    winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
    $py = @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js not found - installing LTS with winget..." -ForegroundColor Yellow
    winget install --id OpenJS.NodeJS.LTS -e --silent --accept-package-agreements --accept-source-agreements
}

Write-Host "`n[1/4] Python virtual environment" -ForegroundColor Cyan
$venv = Join-Path $root "engine\.venv"
if (-not (Test-Path $venv)) { & $py[0] $py[1..9] -m venv $venv }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip -q
& $vpy -m pip install -r (Join-Path $root "engine\requirements-dev.txt")

Write-Host "`n[2/4] Wake word models" -ForegroundColor Cyan
& $vpy -c "import openwakeword.utils as u; u.download_models(model_names=['hey_jarvis']); print('ok')"

Write-Host "`n[3/4] Browser automation driver (uses your installed Edge)" -ForegroundColor Cyan
Write-Host "ok - Jarvis drives your installed Microsoft Edge (run '.venv\Scripts\python -m playwright install chromium' only if Edge is missing)"

Write-Host "`n[4/4] App dependencies" -ForegroundColor Cyan
Push-Location (Join-Path $root "app")
npm install
Pop-Location

Write-Host "`nDone! Start JARVIS with:  cd app; npm run dev" -ForegroundColor Green
Write-Host "Then open the panel (click the orb) -> Settings -> paste your Groq and ElevenLabs keys."
