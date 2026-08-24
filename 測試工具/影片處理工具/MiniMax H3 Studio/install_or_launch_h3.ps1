$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repositoryUrl = "https://github.com/justtina1001-stack/movieeasymake.git"
$runtimeBase = Join-Path $env:LOCALAPPDATA "MiniMaxH3Studio"
$runtimeRoot = Join-Path $runtimeBase "movieeasymake"
$launcher = Join-Path $runtimeRoot "start_h3_studio.bat"

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git 指令失敗（錯誤代碼 $LASTEXITCODE）。"
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "找不到 Git for Windows。請先安裝 https://git-scm.com/download/win，重新開啟工具後再試一次。"
}

New-Item -ItemType Directory -Path $runtimeBase -Force | Out-Null

if (Test-Path -LiteralPath (Join-Path $runtimeRoot ".git")) {
    Write-Host "正在檢查 MiniMax H3 Studio 更新..." -ForegroundColor Cyan
    try {
        Invoke-Git -C $runtimeRoot fetch origin main --depth 1
        Invoke-Git -C $runtimeRoot pull --ff-only origin main
        Write-Host "H3 Studio 已同步至最新版本。" -ForegroundColor Green
    }
    catch {
        if (-not (Test-Path -LiteralPath $launcher)) { throw }
        Write-Warning "目前無法更新，將啟動已安裝版本。原因：$($_.Exception.Message)"
    }
}
elseif (Test-Path -LiteralPath $runtimeRoot) {
    throw "安裝位置已存在但不是有效的 H3 Studio：$runtimeRoot。請先重新命名該資料夾，再執行一次。"
}
else {
    Write-Host "第一次使用，正在下載 MiniMax H3 Studio..." -ForegroundColor Cyan
    Invoke-Git clone --depth 1 --branch main --single-branch $repositoryUrl $runtimeRoot
}

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "下載完成但找不到啟動檔：$launcher"
}

Write-Host "啟動 MiniMax H3 Studio..." -ForegroundColor Green
Start-Process -FilePath $env:ComSpec -ArgumentList @("/d", "/c", "`"$launcher`"") -WorkingDirectory $runtimeRoot
