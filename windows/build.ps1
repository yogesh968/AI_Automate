# Build the Windows installer: engine exe (PyInstaller) + Electron app (electron-builder NSIS).
#   powershell -ExecutionPolicy Bypass -File build.ps1
# Output: app\release\Jarvis Setup <version>.exe
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$vpy = Join-Path $root "engine\.venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) { throw "Run setup.ps1 first." }

Write-Host "[1/3] Icons" -ForegroundColor Cyan
Push-Location (Join-Path $root "app"); npm run icon; Pop-Location

Write-Host "[2/3] Engine -> engine\dist\jarvis-engine\" -ForegroundColor Cyan
Push-Location (Join-Path $root "engine")
& $vpy -c "import openwakeword.utils as u; u.download_models(model_names=['hey_jarvis'])"
& $vpy -m PyInstaller --noconfirm --clean jarvis-engine.spec
if (-not (Test-Path "dist\jarvis-engine\jarvis-engine.exe")) { throw "engine build failed" }
Pop-Location

Write-Host "[3/3] Installer" -ForegroundColor Cyan
Push-Location (Join-Path $root "app")
npm run dist
Pop-Location
Write-Host "Done -> app\release\" -ForegroundColor Green
