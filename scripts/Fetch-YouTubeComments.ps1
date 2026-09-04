<#
.SYNOPSIS
    Base Ball Bear 公式PV YouTube コメント取得スクリプト

.PARAMETER ApiKey
    YouTube Data API v3 のキー。チャットやコードには書かず、実行時に渡してください。

.PARAMETER MaxPerVideo
    1動画あたりの最大追加コメント数（デフォルト: 5）

.PARAMETER DryRun
    ファイルに書き込まず、取得内容だけ表示する

.EXAMPLE
    .\Fetch-YouTubeComments.ps1 -ApiKey "AIza..."
    .\Fetch-YouTubeComments.ps1 -ApiKey "AIza..." -MaxPerVideo 8
    .\Fetch-YouTubeComments.ps1 -ApiKey "AIza..." -DryRun
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$ApiKey,

    [int]$MaxPerVideo = 5,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# ── 動画ID → タイムラインイベントID の対応表 ──────────────────────────
# VideoId    : YouTube動画ID
# EventId    : timeline.json の id フィールド（文字列として比較）
# Title      : 確認用のラベル
$videoMapping = @(
    @{ VideoId = "baVH_BFtQXU"; EventId = "31";  Title = "ELECTRIC SUMMER (20周年記念 Remastered PV)" }
    @{ VideoId = "cK96Q0w0C4U"; EventId = "33";  Title = "抱きしめたい PV" }
    @{ VideoId = "Og0nJf6cIhw"; EventId = "34";  Title = "ドラマチック PV" }
    @{ VideoId = "Pno3nts_ZIE"; EventId = "42";  Title = "BREEEEZE GIRL (20周年記念 Remastered PV)" }
    @{ VideoId = "kDc2VebfUdk"; EventId = "46";  Title = "short hair PV" }
    @{ VideoId = "tZF-CNuCSaQ"; EventId = "150"; Title = "ホワイトワイライト PV" }
    @{ VideoId = "jZxmOwwD2i4"; EventId = "158"; Title = "きみの目 PV" }
    @{ VideoId = "-AupWnQwok4"; EventId = "159"; Title = "クチビル・ディテクティヴ PV" }
    @{ VideoId = "er800teuY4U"; EventId = "19";  Title = "すべては君のせいで MV (DIARY KEY収録)" }
    @{ VideoId = "DYp9ayv1OA0"; EventId = "19";  Title = "DIARY KEY MV" }
)

# ── パス解決 ────────────────────────────────────────────────────────────
$scriptDir = Split-Path $MyInvocation.MyCommand.Path -Parent
$dataPath  = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "..\data\sentiment-manual.json"))
$docsPath  = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "..\docs\data\sentiment-manual.json"))

# ── sentiment-manual.json を読み込む ────────────────────────────────────
$raw  = [System.IO.File]::ReadAllText($dataPath, [System.Text.Encoding]::UTF8)
$data = $raw | ConvertFrom-Json

$apiBase    = "https://www.googleapis.com/youtube/v3/commentThreads"
$totalAdded = 0

# ── 日本語文字が含まれるか判定 ──────────────────────────────────────────
function HasJapanese([string]$text) {
    return $text -match "[぀-ゟ゠-ヿ一-鿿]"
}

# ── メインループ ─────────────────────────────────────────────────────────
foreach ($entry in $videoMapping) {
    $vid      = $entry.VideoId
    $eventId  = $entry.EventId
    $vidTitle = $entry.Title
    $vidUrl   = "https://www.youtube.com/watch?v=$vid"

    Write-Host ""
    Write-Host "━━ $vidTitle" -ForegroundColor Cyan
    Write-Host "   動画ID=$vid  →  イベントID=$eventId"

    # YouTube API 呼び出し
    $uri = "${apiBase}?videoId=${vid}&part=snippet&order=relevance&maxResults=50&key=${ApiKey}"
    try {
        $resp = Invoke-RestMethod -Uri $uri -Method Get -ErrorAction Stop
    } catch {
        $msg = $_.ToString()
        if ($msg -like "*commentsDisabled*") {
            Write-Warning "   コメント無効の動画です（スキップ）"
        } else {
            Write-Warning "   APIエラー: $msg"
        }
        continue
    }

    if (-not $resp.items -or $resp.items.Count -eq 0) {
        Write-Host "   コメントなし（スキップ）"
        continue
    }

    # 日本語コメントを優先、なければ全件 → likeCount 降順
    $candidates = $resp.items | Where-Object { HasJapanese $_.snippet.topLevelComment.snippet.textOriginal }
    if ($candidates.Count -eq 0) {
        $candidates = $resp.items
    }
    $sorted   = $candidates | Sort-Object { [int]$_.snippet.topLevelComment.snippet.likeCount } -Descending
    $selected = $sorted | Select-Object -First $MaxPerVideo

    # 対象イベントエントリを探す（文字列比較）
    $eventEntry = $data | Where-Object { $_.PSObject.Properties['event_id'] -and [string]$_.event_id -eq $eventId } | Select-Object -First 1

    if (-not $eventEntry) {
        Write-Host "   イベントID=$eventId のエントリが未存在 → 新規作成" -ForegroundColor Yellow
        $eventEntry = [PSCustomObject]@{
            event_id = $eventId
            positive = @()
            negative = @()
            note     = ""
        }
        $data = @($data) + $eventEntry
    }

    # positive[] に追加（重複テキストはスキップ）
    $addedCount = 0
    foreach ($item in $selected) {
        $raw = $item.snippet.topLevelComment.snippet.textOriginal
        $text = ($raw -replace "`r`n|`r|`n", " " -replace "\s+", " ").Trim()
        if ($text.Length -gt 200) { $text = $text.Substring(0, 200) + "…" }
        if ([string]::IsNullOrWhiteSpace($text)) { continue }

        # 重複チェック
        $exists = $eventEntry.positive | Where-Object {
            ($_ -is [string] -and $_ -eq $text) -or
            ($null -ne $_.text -and $_.text -eq $text)
        }
        if ($exists) {
            Write-Host "   (重複スキップ): $($text.Substring(0, [Math]::Min(40,$text.Length)))..."
            continue
        }

        $commentObj = [PSCustomObject]@{
            text       = $text
            source     = "YouTube PVコメント"
            source_url = $vidUrl
        }

        if ($DryRun) {
            Write-Host "   [DryRun] $text" -ForegroundColor DarkGray
        } else {
            $eventEntry.positive = @($eventEntry.positive) + $commentObj
        }
        $addedCount++
    }

    Write-Host "   $addedCount 件追加"
    $totalAdded += $addedCount
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "合計 $totalAdded 件のコメントを追加しました"

if ($DryRun) {
    Write-Host "DryRun モード: ファイルへの書き込みはスキップされました" -ForegroundColor Yellow
    exit 0
}

# ── 書き戻し ────────────────────────────────────────────────────────────
$utf8noBom = New-Object System.Text.UTF8Encoding $false
$json = $data | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($dataPath, $json, $utf8noBom)

Copy-Item -Path $dataPath -Destination $docsPath -Force
Write-Host "data/ + docs/data/ に書き込み完了" -ForegroundColor Green
