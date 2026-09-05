$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & node tests/transaction.test.js
    if ($LASTEXITCODE -ne 0) { throw 'Transaction regression failed' }
    & node --check source/index.js
    if ($LASTEXITCODE -ne 0) { throw 'Plugin syntax check failed' }
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'source/manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid package version' }
    $outputPath = Join-Path $PSScriptRoot ('PSDExportPipeline_' + $manifest.version + '.ccx')
    if (Test-Path -LiteralPath $outputPath) { throw 'Version package already exists; verify it or bump the version, never overwrite a published package.' }
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::Open($outputPath, [IO.Compression.ZipArchiveMode]::Create)
    try {
        $sourceRoot = Join-Path $PSScriptRoot 'source'
        Get-ChildItem -LiteralPath $sourceRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
            $relative = $_.FullName.Substring($sourceRoot.Length + 1).Replace('\', '/')
            if ($relative -notmatch '(^\.|^HANDOFF_)') {
                $entry = $archive.CreateEntry($relative, [IO.Compression.CompressionLevel]::Optimal)
                $entry.LastWriteTime = [DateTimeOffset]::new(2026, 9, 5, 0, 0, 0, [TimeSpan]::Zero)
                $inputStream = [IO.File]::OpenRead($_.FullName)
                $outputStream = $entry.Open()
                try { $inputStream.CopyTo($outputStream) } finally { $inputStream.Dispose(); $outputStream.Dispose() }
            }
        }
    } finally { $archive.Dispose() }
    Get-FileHash -LiteralPath $outputPath -Algorithm SHA256
} finally { Pop-Location }
