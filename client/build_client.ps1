# Build the Windows client EXE.
# Run from the project root:  powershell -ExecutionPolicy Bypass -File .\build_client.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade pip
python -m pip install pyinstaller requests

python -m PyInstaller --noconfirm --clean client.spec

$dist = Join-Path $PSScriptRoot "dist"
Copy-Item -Force (Join-Path $PSScriptRoot "client.settings.json") (Join-Path $dist "client.settings.json")

Write-Host ""
Write-Host "Built: dist\OdiBetsClient.exe"
Write-Host "Ship dist\OdiBetsClient.exe together with dist\client.settings.json"
Write-Host "Edit client.settings.json so server_url points at your hosted API."
