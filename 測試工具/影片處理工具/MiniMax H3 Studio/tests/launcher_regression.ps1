$ErrorActionPreference = 'Stop'
$source = Join-Path (Split-Path $PSScriptRoot -Parent) 'install_or_launch_h3.ps1'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$functionAst = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Git' }, $true)
Invoke-Expression $functionAst.Extent.Text
$GitTimeoutSeconds = 10
if ((Invoke-Git --version) -notmatch '^git version') { throw 'Git output capture failed' }
$failed = $false
try { Invoke-Git rev-parse --verify refs/heads/definitely-missing-toolkit-regression | Out-Null } catch { $failed = $true }
if (-not $failed) { throw 'Non-zero Git status was ignored' }
$GitTimeoutSeconds = 1
$watch = [Diagnostics.Stopwatch]::StartNew()
$timedOut = $false
try { Invoke-Git -c 'alias.wait=!sleep 5' wait | Out-Null } catch { $timedOut = $_.Exception.Message -match 'Git' }
if (-not $timedOut -or $watch.Elapsed.TotalSeconds -gt 4.5) { throw 'Git timeout did not stop the process tree promptly' }
Write-Output 'PASS Git output / non-zero status / timeout'

$testBase = Join-Path ([IO.Path]::GetTempPath()) ('h3-launcher-test-' + [guid]::NewGuid().ToString('N'))
$previousLocalAppData = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = $testBase
    $runtime = Join-Path $testBase 'MiniMaxH3Studio/movieeasymake'
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    New-Item -ItemType File -Path (Join-Path $runtime 'start_h3_studio.bat') | Out-Null
    '{"commit":"fixture-installed-commit"}' | Set-Content -LiteralPath (Join-Path (Split-Path $runtime -Parent) 'installed-version.json') -Encoding UTF8
    $script:launchObserved = $false
    function Start-Process {
        param($FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle)
        if ($WorkingDirectory -ne $runtime -or $WindowStyle -ne 'Hidden') { throw 'Unexpected launcher target' }
        $script:launchObserved = $true
    }
    . $source
    if (-not $script:launchObserved) { throw 'Installed tool was not launched' }
    Write-Output 'PASS installed fast launch using existing version record (no network or real GUI)'
}
finally {
    $env:LOCALAPPDATA = $previousLocalAppData
    # Only this freshly generated fixture is removed; never the real runtime.
    $resolved = [IO.Path]::GetFullPath($testBase)
    if ($resolved.StartsWith([IO.Path]::GetTempPath(), [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf).StartsWith('h3-launcher-test-')) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
