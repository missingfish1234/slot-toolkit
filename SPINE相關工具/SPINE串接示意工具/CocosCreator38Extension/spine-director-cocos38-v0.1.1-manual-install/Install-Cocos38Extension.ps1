param(
    [Parameter(Position = 0)]
    [string]$ProjectPath
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    $ProjectPath = Read-Host 'Enter or drag the Cocos Creator 3.8 project folder here'
}

$ProjectPath = $ProjectPath.Trim().Trim('"')
if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
    throw "Project folder does not exist: $ProjectPath"
}

$ResolvedProject = (Resolve-Path -LiteralPath $ProjectPath).Path
$AssetsPath = Join-Path $ResolvedProject 'assets'
$SettingsPath = Join-Path $ResolvedProject 'settings'

if (-not (Test-Path -LiteralPath $AssetsPath -PathType Container) -or
    -not (Test-Path -LiteralPath $SettingsPath -PathType Container)) {
    throw 'The selected folder is not a Cocos Creator 3.x project (assets/settings not found).'
}

$SourcePath = Join-Path $PSScriptRoot 'spine-director-cocos38'
if (-not (Test-Path -LiteralPath (Join-Path $SourcePath 'package.json') -PathType Leaf)) {
    throw "Extension source was not found beside this installer: $SourcePath"
}

$ExtensionsPath = Join-Path $ResolvedProject 'extensions'
$DestinationPath = Join-Path $ExtensionsPath 'spine-director-cocos38'

New-Item -ItemType Directory -Path $DestinationPath -Force | Out-Null
Copy-Item -Path (Join-Path $SourcePath '*') -Destination $DestinationPath -Recurse -Force

Write-Host ''
Write-Host 'Spine Director 3.8 was installed successfully.'
Write-Host "Installed to: $DestinationPath"
Write-Host 'Return to Cocos Creator, refresh Extensions, then enable Spine Director 3.8.'
