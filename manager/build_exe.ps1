$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$venvDir = Join-Path $PSScriptRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

function Test-VenvPython {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        return $false
    }
    try {
        & $venvPython -c "import sys" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

if (-not (Test-VenvPython)) {
    if (Test-Path -LiteralPath $venvDir) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $staleVenv = Join-Path $PSScriptRoot ".venv_stale_$timestamp"
        Move-Item -LiteralPath $venvDir -Destination $staleVenv
        Write-Host "Broken virtual environment backed up to: $staleVenv"
    }

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python was not found. Install Python 3.10 or newer and run this script again."
    }

    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment (exit code $LASTEXITCODE)."
    }
}

& $venvPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $venvPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed; no release was built.' }
$newDistDir = Join-Path $PSScriptRoot "dist\ToolkitManager"
if (Test-Path -LiteralPath $newDistDir) {
    $resolvedDist = (Resolve-Path -LiteralPath $newDistDir).Path
    $allowedDistRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'dist')).TrimEnd('\') + '\'
    if (-not $resolvedDist.StartsWith($allowedDistRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe build output path.' }
    $previousDist = $newDistDir + '.backup-' + [Guid]::NewGuid().ToString('N')
    Move-Item -LiteralPath $resolvedDist -Destination $previousDist
    Write-Host "Previous build retained: $previousDist"
}
$previousBuildPath = $env:Path
try {
    # Keep unrelated native DLLs (for example Poppler's incompatible ICU) out
    # of PyInstaller's dependency resolution; Qt uses Windows' system ICU.
    $basePythonDir = & $venvPython -c "import sys; print(sys.base_prefix)"
    $env:Path = @((Join-Path $env:SystemRoot 'System32'), $env:SystemRoot, (Split-Path $venvPython -Parent), $basePythonDir) -join ';'
    & $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "ToolkitManager" `
    --add-data "config.example.json;." `
    --add-data "apply_update.ps1;." `
    run.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} finally {
    $env:Path = $previousBuildPath
}

$newDistDir = Join-Path $PSScriptRoot "dist\ToolkitManager"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "config.example.json") -Destination (Join-Path $newDistDir "config.json") -Force
$indexSource = Join-Path (Split-Path $PSScriptRoot -Parent) "tools-index.json"
if (Test-Path -LiteralPath $indexSource) {
    Copy-Item -LiteralPath $indexSource -Destination (Join-Path $newDistDir "tools-index.json") -Force
}

$previousSmokeReport = $env:TOOLKIT_SMOKE_REPORT
try {
    $env:TOOLKIT_SMOKE_REPORT = Join-Path $PSScriptRoot ('dist\smoke-' + [Guid]::NewGuid().ToString('N') + '.txt')
    $smokeProcess = Start-Process -FilePath (Join-Path $newDistDir 'ToolkitManager.exe') -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru
    if (-not $smokeProcess.WaitForExit(30000)) {
        Stop-Process -Id $smokeProcess.Id -Force
        throw 'Frozen executable smoke test timed out; release stopped.'
    }
    if ($smokeProcess.ExitCode -ne 0) {
        $detail = if (Test-Path -LiteralPath $env:TOOLKIT_SMOKE_REPORT) { Get-Content -LiteralPath $env:TOOLKIT_SMOKE_REPORT -Raw } else { '' }
        throw "Frozen executable smoke test failed; release stopped. $detail"
    }
    Write-Host 'Frozen executable smoke test passed.'
} finally { $env:TOOLKIT_SMOKE_REPORT = $previousSmokeReport }

$zipPath = Join-Path $PSScriptRoot "dist\ToolkitManager.zip"
$manifestFiles = [ordered]@{}
Get-ChildItem -LiteralPath $newDistDir -Recurse -File | Where-Object { $_.Name -ne 'release-manifest.json' } | ForEach-Object {
    $relative = $_.FullName.Substring($newDistDir.Length + 1).Replace('\', '/')
    $hashStream = [IO.File]::OpenRead($_.FullName)
    $hashAlgorithm = [Security.Cryptography.SHA256]::Create()
    try { $manifestFiles[$relative] = [BitConverter]::ToString($hashAlgorithm.ComputeHash($hashStream)).Replace('-', '').ToLowerInvariant() }
    finally { $hashAlgorithm.Dispose(); $hashStream.Dispose() }
}
$appVersion = & $venvPython -c "from toolkit_manager.models import APP_VERSION; print(APP_VERSION)"
if ($LASTEXITCODE -ne 0) { throw 'Cannot read app version.' }
@{ version=$appVersion; files=$manifestFiles } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $newDistDir 'release-manifest.json') -Encoding UTF8
if (Test-Path $zipPath) {
    Move-Item -LiteralPath $zipPath -Destination ($zipPath + '.backup-' + [Guid]::NewGuid().ToString('N'))
}
Compress-Archive -Path (Join-Path $newDistDir "*") -DestinationPath $zipPath -Force

Write-Host "Build complete: $PSScriptRoot\dist\ToolkitManager\ToolkitManager.exe"
Write-Host "Update package: $zipPath"
