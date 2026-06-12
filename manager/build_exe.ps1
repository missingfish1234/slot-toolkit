$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$distConfig = Join-Path $PSScriptRoot "dist\ToolkitManager\config.json"
$configBackup = Join-Path $env:TEMP "ToolkitManager.config.backup.json"
if (Test-Path $distConfig) {
    Copy-Item -LiteralPath $distConfig -Destination $configBackup -Force
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
& ".\.venv\Scripts\python.exe" -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "ToolkitManager" `
    --add-data "config.example.json;." `
    run.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$newDistDir = Join-Path $PSScriptRoot "dist\ToolkitManager"
if (Test-Path $configBackup) {
    Copy-Item -LiteralPath $configBackup -Destination (Join-Path $newDistDir "config.json") -Force
}

$zipPath = Join-Path $PSScriptRoot "dist\ToolkitManager.zip"
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $newDistDir "*") -DestinationPath $zipPath -Force

Write-Host "Build complete: $PSScriptRoot\dist\ToolkitManager\ToolkitManager.exe"
Write-Host "Update package: $zipPath"
