$ErrorActionPreference = 'Stop'
$canonical = Join-Path $PSScriptRoot 'rolling-score-tester'
& npm test --prefix $canonical
if ($LASTEXITCODE -ne 0) { throw 'Cocos regression failed' }
$manifest = Get-Content -LiteralPath (Join-Path $canonical 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid version' }
$zipName = 'rolling-score-tester-v' + $manifest.version + '.zip'
$outputPath = Join-Path $PSScriptRoot $zipName
if (Test-Path -LiteralPath $outputPath) { throw 'Version package already exists; verify it or bump version, never overwrite a released package.' }
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open($outputPath, [IO.Compression.ZipArchiveMode]::Create)
try {
    Get-ChildItem -LiteralPath $canonical -Recurse -File | Sort-Object FullName | ForEach-Object {
        $relative = $_.FullName.Substring($canonical.Length + 1).Replace('\', '/')
        $entry = $archive.CreateEntry('rolling-score-tester/' + $relative, [IO.Compression.CompressionLevel]::Optimal)
        $entry.LastWriteTime = [DateTimeOffset]::new(2026, 9, 5, 0, 0, 0, [TimeSpan]::Zero)
        $inputStream = [IO.File]::OpenRead($_.FullName)
        $outputStream = $entry.Open()
        try { $inputStream.CopyTo($outputStream) } finally { $inputStream.Dispose(); $outputStream.Dispose() }
    }
} finally { $archive.Dispose() }
$toolkitRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$compatRoot = Join-Path $toolkitRoot '數字圖片工具/數字包圖工具/CocosCreator38Extension'
if (Test-Path -LiteralPath $compatRoot) {
    Get-ChildItem -LiteralPath $canonical -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($canonical.Length + 1)
        $target = Join-Path (Join-Path $compatRoot 'rolling-score-tester') $relative
        New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
    Copy-Item -LiteralPath $outputPath -Destination (Join-Path $compatRoot $zipName)
}
Get-FileHash -LiteralPath $outputPath -Algorithm SHA256
