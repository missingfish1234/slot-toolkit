$ErrorActionPreference = 'Stop'
$extension = Join-Path $PSScriptRoot 'spine-director-cocos38'
& node (Join-Path $extension 'scripts/verify.js')
if ($LASTEXITCODE -ne 0) { throw 'Timeline verification failed; package not replaced.' }
$version = (Get-Content -LiteralPath (Join-Path $extension 'package.json') -Raw | ConvertFrom-Json).version
$staging = Join-Path ([System.IO.Path]::GetTempPath()) ('spine-timeline-package-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging | Out-Null
$package = Join-Path $staging 'spine-director-cocos38'
Copy-Item -LiteralPath $extension -Destination $package -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tests') -Destination (Join-Path $package 'tests') -Recurse
$archive = Join-Path $staging ('spine-director-cocos38-v' + $version + '-manual-install.zip')
Compress-Archive -LiteralPath $package -DestinationPath $archive
$destination = Join-Path $PSScriptRoot ([System.IO.Path]::GetFileName($archive))
if (Test-Path -LiteralPath $destination) { Copy-Item -LiteralPath $destination -Destination (Join-Path $staging 'previous-package.zip') }
Copy-Item -LiteralPath $archive -Destination $destination -Force
Get-FileHash -LiteralPath $destination -Algorithm SHA256
Write-Output ('Build staging / previous package retained at: ' + $staging)
