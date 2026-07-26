<#
.SYNOPSIS
  data/*.json を整形して docs/data/ にコピーする(公開用データの同期)。
.DESCRIPTION
  data/timeline.json, data/setlists.json はそのままコピー。
  data/sentiment-manual.json, data/updates-manual.json はテンプレート用の
  コメント行・未入力の空エントリを除去してから docs/data/sentiment.json,
  docs/data/updates.json として書き出す。
  編集・再生成後は必ずこのスクリプトを実行してからプレビュー・公開すること。
#>
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $root "data"
$destDir = Join-Path $root "docs\data"
if (-not (Test-Path $destDir)) {
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
}

function Write-JsonArray($items, $path) {
    $items = @($items)
    if ($items.Count -eq 0) {
        $json = "[]"
    } elseif ($items.Count -eq 1) {
        $json = "[" + ($items[0] | ConvertTo-Json -Depth 10) + "]"
    } else {
        $json = $items | ConvertTo-Json -Depth 10
    }
    $json | Out-File -FilePath $path -Encoding UTF8
}

# --- そのままコピーするもの ---
foreach ($name in @("timeline.json", "setlists.json", "youtube-stats.json", "songs.json")) {
    $src = Join-Path $dataDir $name
    if (-not (Test-Path $src)) {
        Write-Warning "見つからないためスキップ: $src"
        continue
    }
    Get-Content $src -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null  # JSONとして妥当かチェック
    Copy-Item -Path $src -Destination (Join-Path $destDir $name) -Force
    Write-Output "同期しました: $src -> $destDir\$name"
}

# --- sentiment-manual.json: event_idがあり、positive/negative/noteのいずれかに中身がある行だけ公開 ---
$sentimentSrc = Join-Path $dataDir "sentiment-manual.json"
if (Test-Path $sentimentSrc) {
    $raw = Get-Content $sentimentSrc -Raw -Encoding UTF8 | ConvertFrom-Json
    $filtered = @($raw | Where-Object {
        $_.event_id -and (
            ($_.positive -and $_.positive.Count -gt 0) -or
            ($_.negative -and $_.negative.Count -gt 0) -or
            ($_.note -and $_.note.Trim() -ne "")
        )
    })
    Write-JsonArray $filtered (Join-Path $destDir "sentiment.json")
    Write-Output "生成しました: docs\data\sentiment.json ($($filtered.Count)件、未入力分は除外)"
}

# --- updates-manual.json: idがある行だけ公開、日付降順 ---
$updatesSrc = Join-Path $dataDir "updates-manual.json"
if (Test-Path $updatesSrc) {
    $raw = Get-Content $updatesSrc -Raw -Encoding UTF8 | ConvertFrom-Json
    $filtered = @($raw | Where-Object { $_.id } | Sort-Object -Property date -Descending)
    Write-JsonArray $filtered (Join-Path $destDir "updates.json")
    Write-Output "生成しました: docs\data\updates.json ($($filtered.Count)件)"
}
