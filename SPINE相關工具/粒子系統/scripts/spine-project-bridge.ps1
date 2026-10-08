<#
Convert one exported skeleton between a Spine 3.8, 4.0, or 4.2 project and JSON.
Only the installed official Spine CLI reads/writes native project files.

Examples (PowerShell 5.1 or later):
  .\scripts\spine-project-bridge.ps1 -InputPath 'D:\Art\hero.spine'
  .\scripts\spine-project-bridge.ps1 -InputPath 'D:\Art\hero.spine' -SpineVersion '3.8.99'
  .\scripts\spine-project-bridge.ps1 -InputPath 'D:\Art\hero_particles.json' -OutputPath 'D:\Art\hero_particles.spine'

Official references:
https://en.esotericsoftware.com/spine-command-line-interface
https://en.esotericsoftware.com/spine-export/
https://eu.esotericsoftware.com/forum/d/26465-spine-cli-export-option-for-specific-skeleton/12
#>
[CmdletBinding()]
param(
    [string] $InputPath,
    [string] $OutputPath,
    [string] $SpinePath = 'C:\Program Files\Spine\Spine.com',
    [string] $SpineVersion
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$interactive = [string]::IsNullOrWhiteSpace($InputPath)
$stagingDirectory = $null
$outputDirectory = $null
$stagingName = '.particle-spine-bridge-' + [Guid]::NewGuid().ToString('N')
$selectedVersion = $null
$temporaryProjectPath = $null

function Get-CachedSpineVersions {
    # Inspect update filenames only. Never read launcher settings or license data.
    $names = New-Object 'System.Collections.Generic.List[string]'
    $roots = @((Join-Path $env:USERPROFILE 'Spine\updates'), (Join-Path $env:APPDATA 'Spine\updates'))
    foreach ($root in $roots) {
        if ([IO.Directory]::Exists($root)) {
            foreach ($item in @(Get-ChildItem -LiteralPath $root -File)) {
                if ($item.Name -match '^(3\.8|4\.0|4\.2)\.\d+$') { $names.Add($item.Name) }
            }
        }
    }
    return @($names | Select-Object -Unique | Sort-Object { [Version] $_ })
}

function Resolve-CachedSpineVersion([string] $Requested, [string[]] $Available) {
    if ($Requested -match '^(3\.8|4\.0|4\.2)(?:\.(?:x|xx))?$') {
        $family = $Matches[1]
        $matching = @($Available | Where-Object { $_.StartsWith($family + '.') } | Sort-Object { [Version] $_ } -Descending)
        if ($matching.Count -gt 0) { return $matching[0] }
    } elseif ($Requested -match '^(3\.8|4\.0|4\.2)\.\d+$') {
        if ($Available -contains $Requested) { return $Requested }
    } else {
        throw 'SpineVersion 請指定 3.8、4.0、4.2 或精確版本（例如 3.8.99、4.0.56、4.2.43）；不支援跨版本自動轉換。'
    }
    throw ('尚未找到本機 Spine ' + $Requested + ' 版本。請先在已安裝 Spine 中啟動該版本，再使用此轉換工具；本工具不下載或安裝版本。')
}

function Select-SpineVersion([string[]] $Available) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    if ($Available.Count -eq 0) { throw '找不到本機 Spine 3.8、4.0 或 4.2。請先在已安裝 Spine 中啟動需要的版本；本工具不下載或安裝版本。' }
    $form = New-Object System.Windows.Forms.Form
    $label = New-Object System.Windows.Forms.Label
    $combo = New-Object System.Windows.Forms.ComboBox
    $ok = New-Object System.Windows.Forms.Button
    $cancel = New-Object System.Windows.Forms.Button
    try {
        $form.Text = '選擇原工程的 Spine 版本'
        $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
        $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
        $form.MaximizeBox = $false
        $form.MinimizeBox = $false
        $form.ClientSize = New-Object System.Drawing.Size(440, 172)
        $label.Text = '請選與原 .spine 工程相同的版本。僅使用本機已有版本。'
        $label.Location = New-Object System.Drawing.Point(16, 18)
        $label.Size = New-Object System.Drawing.Size(406, 36)
        $combo.Location = New-Object System.Drawing.Point(16, 64)
        $combo.Size = New-Object System.Drawing.Size(406, 28)
        $combo.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
        foreach ($version in $Available) {
            $family = ($version -split '\.')[0..1] -join '.'
            [void] $combo.Items.Add(('Spine ' + $family + '  —  ' + $version))
        }
        $default = [Array]::IndexOf($Available, '4.0.56')
        $combo.SelectedIndex = if ($default -ge 0) { $default } else { 0 }
        $ok.Text = '轉換'
        $ok.Location = New-Object System.Drawing.Point(230, 122)
        $ok.Size = New-Object System.Drawing.Size(92, 30)
        $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $cancel.Text = '取消'
        $cancel.Location = New-Object System.Drawing.Point(330, 122)
        $cancel.Size = New-Object System.Drawing.Size(92, 30)
        $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
        $form.Controls.AddRange(@($label, $combo, $ok, $cancel))
        $form.AcceptButton = $ok
        $form.CancelButton = $cancel
        if ($form.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { return $Available[$combo.SelectedIndex] }
        return $null
    } finally { $form.Dispose() }
}

function Select-ExistingFile([string] $Title, [string] $Filter, [string] $InitialDirectory) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    try {
        $dialog.Title = $Title
        $dialog.Filter = $Filter
        $dialog.CheckFileExists = $true
        $dialog.Multiselect = $false
        if ($InitialDirectory -and [IO.Directory]::Exists($InitialDirectory)) {
            $dialog.InitialDirectory = $InitialDirectory
        }
        if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
            return $dialog.FileName
        }
        return $null
    } finally { $dialog.Dispose() }
}

function Find-UnusedOutput([string] $Directory, [string] $BaseName, [string] $Extension) {
    $candidate = Join-Path $Directory ($BaseName + $Extension)
    $suffix = 2
    while (Test-Path -LiteralPath $candidate) {
        $candidate = Join-Path $Directory ($BaseName + '_' + $suffix + $Extension)
        $suffix++
    }
    return $candidate
}

function ConvertTo-WindowsArgument([string] $Value) {
    # Windows argv quoting, without a shell or expression evaluation.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-SpineCli([string[]] $Arguments) {
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $script:SpinePath
    $start.Arguments = ($Arguments | ForEach-Object { ConvertTo-WindowsArgument $_ }) -join ' '
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $start.StandardErrorEncoding = New-Object System.Text.UTF8Encoding($false)
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw '無法啟動 Spine CLI。' }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(120000)) {
            $process.Kill()
            $process.WaitForExit()
            throw ('Spine 轉換逾時，請確認已安裝並可啟動 ' + $script:selectedVersion + '。')
        }
        $log = $stdout.GetAwaiter().GetResult() + [Environment]::NewLine + $stderr.GetAwaiter().GetResult()
        # Never display or save the launcher's private license-identification line.
        $safeLines = @($log -split '\r?\n' | Where-Object { $_ -notmatch '(?i)Licensed\s+to\s*:' })
        foreach ($line in $safeLines) { if ($line.Trim()) { Write-Host $line } }
        if ($process.ExitCode -ne 0) {
            throw ('Spine CLI 轉換失敗，代碼 ' + $process.ExitCode + '。')
        }
        $safeLog = $safeLines -join [Environment]::NewLine
        $versionPattern = 'Spine ' + [regex]::Escape($script:selectedVersion) + '(?:\s|$)'
        if ($safeLog -notmatch $versionPattern -or $safeLog -notmatch 'Complete\.') {
            throw ('Spine CLI 未確認以 ' + $script:selectedVersion + ' 完成轉換。請先在 Spine 中確認該版本可用。')
        }
    } finally { $process.Dispose() }
}

function Read-SkeletonJson([string] $Path) {
    $json = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json
    $names = @($json.PSObject.Properties.Name)
    if ($names -notcontains 'skeleton' -or $names -notcontains 'bones') {
        throw '此檔案不是 Spine 骨架 JSON。請勿選取 .particle.json 專案或匯出設定 JSON。'
    }
    if (@($json.skeleton.PSObject.Properties.Name) -notcontains 'spine' -or $json.skeleton.spine -notmatch '^(3\.8|4\.0|4\.2)\.\d+$') {
        throw '只支援有精確版號的 Spine 3.8、4.0 或 4.2 骨架 JSON；請使用與原工程相同的 Spine 版本匯出。'
    }
    return $json
}

function Show-ImagePath($Json, [string] $SourceDirectory) {
    if (@($Json.skeleton.PSObject.Properties.Name) -contains 'images' -and $Json.skeleton.images) {
        $images = [string] $Json.skeleton.images
        Write-Host ('JSON 原素材路徑：' + $images)
        if ([IO.Path]::IsPathRooted($images)) {
            $resolved = [IO.Path]::GetFullPath($images)
        } else {
            $resolved = [IO.Path]::GetFullPath((Join-Path $SourceDirectory $images))
        }
        Write-Host ('原素材位置參考：' + $resolved)
    } else {
        Write-Host 'JSON 沒有 images 素材路徑；匯入後請在 Spine 設定原素材資料夾。'
    }
    Write-Host '本工具不複製或修改原素材。輸出移到其他資料夾時，請在 Spine 確認 Images 路徑。'
}

try {
    if ($interactive) {
        Write-Host 'Spine 工程轉換｜3.8 / 4.0 / 4.2'
        Write-Host '選取原 .spine 匯出 JSON，或選取追加粒子後的 JSON 建立新 .spine。'
        $InputPath = Select-ExistingFile '選取 Spine 工程或骨架 JSON' 'Spine 工程 / 骨架 JSON (*.spine;*.json)|*.spine;*.json' (Get-Location).Path
        if (-not $InputPath) { exit 0 }
    }
    if (-not [IO.File]::Exists($InputPath)) { throw ('找不到輸入檔案：' + $InputPath) }
    $InputPath = [IO.Path]::GetFullPath($InputPath)
    $inputDirectory = [IO.Path]::GetDirectoryName($InputPath)
    $inputExtension = [IO.Path]::GetExtension($InputPath).ToLowerInvariant()
    if ($inputExtension -notin @('.spine', '.json')) { throw '輸入檔案必須是 .spine 或 .json。' }

    if (-not [IO.File]::Exists($SpinePath)) {
        if ($interactive) {
            $SpinePath = Select-ExistingFile '選取已安裝 Spine 的 Spine.com' 'Spine CLI (Spine.com)|Spine.com' 'C:\Program Files'
            if (-not $SpinePath) { exit 0 }
        } else { throw '找不到 Spine.com。請以 -SpinePath 指定已安裝 Spine 的 Spine.com 路徑。' }
    }
    $SpinePath = [IO.Path]::GetFullPath($SpinePath)
    if ([IO.Path]::GetFileName($SpinePath) -ine 'Spine.com') { throw '請選取已安裝 Spine 的 Spine.com CLI。' }
    $exporting = $inputExtension -eq '.spine'
    $availableVersions = @(Get-CachedSpineVersions)
    $json = $null
    if ($exporting) {
        if (-not [string]::IsNullOrWhiteSpace($SpineVersion)) {
            $selectedVersion = Resolve-CachedSpineVersion $SpineVersion $availableVersions
        } elseif ($interactive) {
            $selectedVersion = Select-SpineVersion $availableVersions
            if (-not $selectedVersion) { exit 0 }
        } else {
            # Keep the earlier CLI default; callers select 3.8 / 4.2 explicitly.
            $selectedVersion = Resolve-CachedSpineVersion '4.0.56' $availableVersions
        }
    } else {
        $json = Read-SkeletonJson $InputPath
        $jsonVersion = [string] $json.skeleton.spine
        if (-not [string]::IsNullOrWhiteSpace($SpineVersion)) {
            $sameFamilyRequest = $SpineVersion -match '^(3\.8|4\.0|4\.2)(?:\.(?:x|xx))?$'
            $familyMatches = $sameFamilyRequest -and $jsonVersion.StartsWith($Matches[1] + '.')
            if (-not $familyMatches -and $SpineVersion -ne $jsonVersion) {
                throw ('JSON 版本為 ' + $jsonVersion + '，不能指定 ' + $SpineVersion + '。請以相同的精確版本匯入，避免升版或降版。')
            }
        }
        # JSON imports always use the precise source patch, even when a family was requested.
        $selectedVersion = Resolve-CachedSpineVersion $jsonVersion $availableVersions
    }
    Write-Host ('使用 Spine ' + $selectedVersion + '；不會升版或降版 JSON。')
    $outputExtension = if ($exporting) { '.json' } else { '.spine' }
    $suffix = if ($exporting) { '_particleSource' } else { '_particles' }
    if ([string]::IsNullOrWhiteSpace($OutputPath)) {
        $OutputPath = Find-UnusedOutput $inputDirectory ([IO.Path]::GetFileNameWithoutExtension($InputPath) + $suffix) $outputExtension
    }
    $OutputPath = [IO.Path]::GetFullPath($OutputPath)
    if ([IO.Path]::GetExtension($OutputPath) -ine $outputExtension) { throw ('輸出副檔名必須是 ' + $outputExtension + '。') }
    if ($InputPath -ieq $OutputPath) { throw '輸出不能是原輸入檔案。' }
    if (Test-Path -LiteralPath $OutputPath) { throw ('輸出檔案已存在，為保留原檔不會覆蓋：' + $OutputPath) }
    $outputDirectory = [IO.Path]::GetDirectoryName($OutputPath)
    [IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
    $stagingDirectory = Join-Path $outputDirectory $stagingName
    [IO.Directory]::CreateDirectory($stagingDirectory) | Out-Null

    if ($exporting) {
        # Fixed, locally generated settings only; third-party export settings/scripts are never executed.
        # Nonessential preserves editor import data; no key cleanup or atlas packing is performed.
        $settingsPath = Join-Path $stagingDirectory 'particle-source.export.json'
        $settings = '{"class":"export-json","name":"JSON","extension":".json","format":"JSON","prettyPrint":true,"nonessential":true,"cleanUp":false,"packAtlas":null,"packSource":"attachments","packTarget":"single","warnings":true,"output":"","input":"","open":false}'
        [IO.File]::WriteAllText($settingsPath, $settings, (New-Object Text.UTF8Encoding($false)))
        $exportDirectory = Join-Path $stagingDirectory 'export'
        [IO.Directory]::CreateDirectory($exportDirectory) | Out-Null
        Invoke-SpineCli @('--update', $selectedVersion, '--input', $InputPath, '--output', $exportDirectory, '--export', $settingsPath)
        $exports = @(Get-ChildItem -LiteralPath $exportDirectory -File -Filter '*.json')
        if ($exports.Count -ne 1) {
            throw ('需要且只支援一個可匯出的骨架，目前匯出 ' + $exports.Count + ' 個。請在 Spine 保留目標骨架的 Export 勾選，再匯出 JSON。')
        }
        $json = Read-SkeletonJson $exports[0].FullName
        if ([string] $json.skeleton.spine -ne $selectedVersion) { throw ('匯出的 JSON 版本不是所選的 ' + $selectedVersion + '；未寫入輸出檔案。') }
        Show-ImagePath $json $inputDirectory
        [IO.File]::Move($exports[0].FullName, $OutputPath)
        Write-Host '已含 Nonessential 資料；JSON 往返仍可能不保留所有工程編輯器資訊，請保存原 .spine。'
    } else {
        Show-ImagePath $json $inputDirectory
        # 4.2 rebases image/audio paths relative to the native output location.
        # Keep the temporary native project beside the final output before renaming it.
        $stagedProject = Join-Path $outputDirectory ($stagingName + '.spine')
        $temporaryProjectPath = $stagedProject
        Invoke-SpineCli @('--update', $selectedVersion, '--input', $InputPath, '--output', $stagedProject, '--import', [IO.Path]::GetFileNameWithoutExtension($InputPath))
        if (-not [IO.File]::Exists($stagedProject) -or (Get-Item -LiteralPath $stagedProject).Length -eq 0) {
            throw 'Spine 沒有產生完整工程檔案。'
        }
        [IO.File]::Move($stagedProject, $OutputPath)
    }
    Write-Host ''
    Write-Host ('轉換完成：' + $OutputPath)
    if ($exporting) { Write-Host '接著在粒子工作室的追加表演功能載入此 JSON。' }
    else { Write-Host ('請在 Spine ' + $selectedVersion + ' 開啟此新工程，確認骨架、表演與素材路徑。') }
    if ($interactive) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(('轉換完成：' + [Environment]::NewLine + $OutputPath + [Environment]::NewLine + [Environment]::NewLine + '原檔保留，請確認新工程的 Images 素材路徑。'), 'Spine 工程轉換', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
    }
    exit 0
} catch {
    $safeError = ($_.Exception.Message -split '\r?\n' | Where-Object { $_ -notmatch '(?i)Licensed\s+to\s*:' }) -join [Environment]::NewLine
    Write-Host ('轉換未完成：' + $safeError) -ForegroundColor Red
    if ($interactive) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($safeError, 'Spine 工程轉換', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    }
    exit 1
} finally {
    if ($temporaryProjectPath -and [IO.File]::Exists($temporaryProjectPath)) {
        $resolvedProject = [IO.Path]::GetFullPath($temporaryProjectPath)
        $expectedDirectory = [IO.Path]::GetFullPath($outputDirectory).TrimEnd('\')
        if ([IO.Path]::GetDirectoryName($resolvedProject).TrimEnd('\') -ieq $expectedDirectory -and [IO.Path]::GetFileName($resolvedProject) -eq ($stagingName + '.spine')) {
            Remove-Item -LiteralPath $resolvedProject -Force
        }
    }
    if ($stagingDirectory -and [IO.Directory]::Exists($stagingDirectory)) {
        # Delete only this invocation's generated staging directory under the explicit output directory.
        $resolvedStage = [IO.Path]::GetFullPath($stagingDirectory)
        $allowedParent = [IO.Path]::GetFullPath($outputDirectory).TrimEnd('\') + '\'
        if ($resolvedStage.StartsWith($allowedParent, [StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($resolvedStage) -eq $stagingName) {
            Remove-Item -LiteralPath $resolvedStage -Recurse -Force
        }
    }
}
