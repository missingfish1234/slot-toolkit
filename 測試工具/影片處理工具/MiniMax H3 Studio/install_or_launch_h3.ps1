param([switch]$Update, [switch]$UpdateOnly, [int]$GitTimeoutSeconds = 120)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$repositoryUrl = "https://github.com/justtina1001-stack/movieeasymake.git"
$runtimeBase = Join-Path $env:LOCALAPPDATA "MiniMaxH3Studio"
$runtimeRoot = Join-Path $runtimeBase "movieeasymake"
$launcher = Join-Path $runtimeRoot "start_h3_studio.bat"
$versionFile = Join-Path $runtimeBase "installed-version.json"

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $gitCommand = Get-Command git -ErrorAction Stop
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $gitCommand.Source
    $start.Arguments = ($Arguments | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }) -join ' '
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit([Math]::Max(1, $GitTimeoutSeconds) * 1000)) {
            & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
            throw "Git 等待超過 $GitTimeoutSeconds 秒；已停止本次更新。"
        }
        $out = $stdout.GetAwaiter().GetResult()
        $err = $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw "Git 失敗：$err" }
        return $out.Trim()
    }
    finally { $process.Dispose() }
}

function Save-InstalledVersion {
    $commit = Invoke-Git -C $runtimeRoot rev-parse HEAD
    $data = @{ repository = $repositoryUrl; commit = $commit; checkedAt = [DateTime]::UtcNow.ToString("o") }
    $temporary = Join-Path $runtimeBase ("version-" + [guid]::NewGuid().ToString("N") + ".tmp")
    $data | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $versionFile -Force
    Write-Host "已安裝版本：$commit" -ForegroundColor Green
}

$installed = Test-Path -LiteralPath $launcher
$updateFailed = $false
if (-not $installed -or $Update -or $UpdateOnly) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        if (-not $installed) { throw "首次安裝需要 Git for Windows：https://git-scm.com/download/win" }
        Write-Warning "未找到 Git，保留已安裝版本。"
        $updateFailed = $true
    } else {
        New-Item -ItemType Directory -Path $runtimeBase -Force | Out-Null
        $mutex = New-Object System.Threading.Mutex($false, "Local\MiniMaxH3StudioInstall")
        $locked = $false
        try {
            try { $locked = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $locked = $true }
            if (-not $locked) { throw "另一個 H3 安裝／更新正在執行，請稍後再試。" }
            if (Test-Path -LiteralPath (Join-Path $runtimeRoot ".git")) {
                Write-Host "正在更新，最多等待每個 Git 指令 $GitTimeoutSeconds 秒..." -ForegroundColor Cyan
                Invoke-Git -C $runtimeRoot fetch origin main --depth 1 | Out-Null
                $remoteLauncher = Invoke-Git -C $runtimeRoot ls-tree --name-only FETCH_HEAD -- start_h3_studio.bat
                if ($remoteLauncher -ne 'start_h3_studio.bat') { throw '新版缺少啟動檔，已保留現有版本。' }
                Invoke-Git -C $runtimeRoot merge --ff-only FETCH_HEAD | Out-Null
            } elseif (Test-Path -LiteralPath $runtimeRoot) {
                throw "安裝目錄已存在但不是 Git 專案；已保留原資料，請檢查 $runtimeRoot"
            } else {
                $staging = Join-Path $runtimeBase ("install-" + [guid]::NewGuid().ToString("N"))
                Invoke-Git clone --depth 1 --branch main --single-branch $repositoryUrl $staging | Out-Null
                if (-not (Test-Path -LiteralPath (Join-Path $staging "start_h3_studio.bat"))) { throw "下載缺少啟動檔；資料保留於 $staging" }
                Move-Item -LiteralPath $staging -Destination $runtimeRoot
            }
            if (-not (Test-Path -LiteralPath $launcher)) { throw "找不到 start_h3_studio.bat" }
            Save-InstalledVersion
        }
        catch {
            $updateFailed = $true
            if (-not (Test-Path -LiteralPath $launcher)) { throw }
            Write-Warning "本次未完成更新，使用已安裝版本。$($_.Exception.Message)"
        }
        finally { if ($locked) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
    }
}
if (Test-Path -LiteralPath $versionFile) {
    try { $v = Get-Content -LiteralPath $versionFile -Raw | ConvertFrom-Json; Write-Host "版本 commit：$($v.commit)" } catch { Write-Warning "版本紀錄損壞，可執行「檢查更新」重新建立。" }
} elseif (Get-Command git -ErrorAction SilentlyContinue) {
    try { Save-InstalledVersion } catch { Write-Warning "尚無版本紀錄：$($_.Exception.Message)" }
}
if ($UpdateOnly) { if ($updateFailed) { exit 1 }; exit 0 }
if (-not (Test-Path -LiteralPath $launcher)) { throw "尚未安裝 MiniMax H3 Studio。" }
Write-Host "啟動已安裝版本；需要更新時執行「檢查更新 MiniMax H3 Studio.cmd」。" -ForegroundColor Green
Start-Process -FilePath $env:ComSpec -ArgumentList @("/d", "/c", "`"$launcher`"") -WorkingDirectory $runtimeRoot -WindowStyle Hidden
