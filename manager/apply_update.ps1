param([Parameter(Mandatory=$true)][string]$RequestPath)
$ErrorActionPreference = 'Stop'
$stagePath = $null
$backupPath = $null
$promoted = $false
$requestFull = [IO.Path]::GetFullPath($RequestPath)
$statusPath = $requestFull + '.status.json'

function Assert-Child([string]$ParentPath, [string]$ChildPath) {
    $parentFull = [IO.Path]::GetFullPath($ParentPath).TrimEnd('\') + '\'
    $childFull = [IO.Path]::GetFullPath($ChildPath)
    if (-not $childFull.StartsWith($parentFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe update path: $childFull"
    }
}
function Copy-Tree([string]$SourcePath, [string]$DestinationPath) {
    Get-ChildItem -LiteralPath $SourcePath -Force | ForEach-Object {
        if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked path is not supported: $($_.FullName)" }
        $copyTarget = Join-Path $DestinationPath $_.Name
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Path $copyTarget -Force | Out-Null
            Copy-Tree $_.FullName $copyTarget
        } else { Copy-Item -LiteralPath $_.FullName -Destination $copyTarget -Force }
    }
}
function Get-Sha256([string]$FilePath) {
    $stream = [IO.File]::OpenRead($FilePath)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}
try {
    $request = Get-Content -LiteralPath $requestFull -Raw -Encoding UTF8 | ConvertFrom-Json
    $sourcePath = [IO.Path]::GetFullPath($request.source_dir)
    $targetPath = [IO.Path]::GetFullPath($request.target_dir)
    $parentPath = Split-Path -Path $targetPath -Parent
    if (-not $parentPath -or $targetPath.TrimEnd('\') -eq [IO.Path]::GetPathRoot($targetPath).TrimEnd('\')) { throw 'Cannot update a drive root.' }
    Assert-Child $parentPath $targetPath
    if ($sourcePath -eq $targetPath -or $sourcePath.StartsWith($targetPath.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Update source must be outside the installed manager.' }
    foreach ($folder in @($sourcePath, $targetPath)) {
        if (-not (Test-Path -LiteralPath (Join-Path $folder 'ToolkitManager.exe') -PathType Leaf)) { throw "Missing manager executable: $folder" }
        if ((Get-Item -LiteralPath $folder).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked manager directories are not supported.' }
    }
    $manifest = Get-Content -LiteralPath (Join-Path $sourcePath 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $manifest.files.'ToolkitManager.exe') { throw 'Invalid release manifest.' }
    foreach ($file in $manifest.files.PSObject.Properties) {
        $filePath = Join-Path $sourcePath $file.Name
        Assert-Child $sourcePath $filePath
        if ((Get-Sha256 $filePath) -ne $file.Value) { throw "Checksum mismatch: $($file.Name)" }
    }
    Get-ChildItem -LiteralPath $sourcePath -Recurse -File -Force | ForEach-Object {
        $relative = $_.FullName.Substring($sourcePath.TrimEnd('\').Length + 1).Replace('\', '/')
        if ($relative -ne 'release-manifest.json' -and -not $manifest.files.PSObject.Properties[$relative]) { throw "Unlisted release file: $relative" }
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    while ($request.parent_pid -gt 0 -and (Get-Process -Id $request.parent_pid -ErrorAction SilentlyContinue)) {
        if ([DateTime]::UtcNow -gt $deadline) { throw 'The manager is still running; no files were replaced.' }
        Start-Sleep -Milliseconds 200
    }
    $nonce = [Guid]::NewGuid().ToString('N')
    $stagePath = $targetPath + '.update-' + $nonce
    $backupPath = $targetPath + '.backup-' + $nonce
    Assert-Child $parentPath $stagePath
    Assert-Child $parentPath $backupPath
    New-Item -ItemType Directory -Path $stagePath | Out-Null
    Copy-Tree $targetPath $stagePath
    Copy-Tree $sourcePath $stagePath
    $oldConfig = Join-Path $targetPath 'config.json'
    if (Test-Path -LiteralPath $oldConfig) { Copy-Item -LiteralPath $oldConfig -Destination (Join-Path $stagePath 'config.json') -Force }
    Move-Item -LiteralPath $targetPath -Destination $backupPath
    Move-Item -LiteralPath $stagePath -Destination $targetPath
    $promoted = $true
    if (-not $request.no_launch) { Start-Process -FilePath (Join-Path $targetPath 'ToolkitManager.exe') -WorkingDirectory $targetPath }
    @{ ok=$true; backup=$backupPath; target=$targetPath } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    exit 0
} catch {
    $message = $_.Exception.Message
    if ($backupPath -and (Test-Path -LiteralPath $backupPath)) {
        if ($promoted -and (Test-Path -LiteralPath $targetPath)) {
            $failedPath = $targetPath + '.failed-' + [Guid]::NewGuid().ToString('N')
            Assert-Child $parentPath $failedPath
            Move-Item -LiteralPath $targetPath -Destination $failedPath
        }
        if (-not (Test-Path -LiteralPath $targetPath)) { Move-Item -LiteralPath $backupPath -Destination $targetPath }
    }
    @{ ok=$false; error=$message; staging=$stagePath } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Error $message
    exit 1
}
