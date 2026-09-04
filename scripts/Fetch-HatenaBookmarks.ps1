<#
.SYNOPSIS
    Base Ball Bear 関連ページのはてなブックマークコメント取得スクリプト

.DESCRIPTION
    はてなブックマークの無料 JSON API (https://b.hatena.ne.jp/entry/json/) を使用して
    各ページのブックマークコメントを取得し、sentiment-manual.json に追加します。
    APIキー不要。1秒ウェイトでレート制限に配慮。

.PARAMETER DryRun
    ファイルに書き込まず、取得内容だけ表示する

.EXAMPLE
    .\Fetch-HatenaBookmarks.ps1
    .\Fetch-HatenaBookmarks.ps1 -DryRun
#>
param([switch]$DryRun)

$ErrorActionPreference = "Stop"

# ── 対象URL → タイムラインイベントID の対応表 ────────────────────────
$urlMapping = @(
    # メインWikipedia記事
    @{ Url="https://ja.wikipedia.org/wiki/Base_Ball_Bear";      EventId="1";  Label="Base Ball Bear (Wikipedia)" }
    # アルバム記事
    @{ Url="https://ja.wikipedia.org/wiki/C_%28Base_Ball_Bear%E3%81%AE%E3%82%A2%E3%83%AB%E3%83%90%E3%83%A0%29"; EventId="4";  Label="Cアルバム (Wikipedia)" }
    @{ Url="https://ja.wikipedia.org/wiki/%E5%8D%81%E4%B8%83%E6%AD%B3";          EventId="5";  Label="十七歳 (Wikipedia)" }
    @{ Url="https://ja.wikipedia.org/wiki/%E6%96%B0%E5%91%BC%E5%90%B8";          EventId="8";  Label="新呼吸 (Wikipedia)" }
    @{ Url="https://ja.wikipedia.org/wiki/%E4%BA%8C%E5%8D%81%E4%B9%9D%E6%AD%B3"; EventId="11"; Label="二十九歳 (Wikipedia)" }
    @{ Url="https://ja.wikipedia.org/wiki/C2_%28Base_Ball_Bear%E3%81%AE%E3%82%A2%E3%83%AB%E3%83%90%E3%83%A0%29"; EventId="12"; Label="C2 (Wikipedia)" }
    @{ Url="https://ja.wikipedia.org/wiki/%E5%85%89%E6%BA%90_%28%E3%82%A2%E3%83%AB%E3%83%90%E3%83%A0%29"; EventId="14"; Label="光源 (Wikipedia)" }
    @{ Url="https://ja.wikipedia.org/wiki/DIARY_KEY";                             EventId="19"; Label="DIARY KEY (Wikipedia)" }
    # シングル記事
    @{ Url="https://ja.wikipedia.org/wiki/BREEEEZE_GIRL";          EventId="42"; Label="BREEEEZE GIRL (Wikipedia)" }
    @{ Url="https://ja.wikipedia.org/wiki/Stairway_Generation";    EventId="44"; Label="Stairway Generation (Wikipedia)" }
    @{ Url="https://ja.wikipedia.org/wiki/%E3%83%89%E3%83%A9%E3%83%9E%E3%83%81%E3%83%83%E3%82%AF_%28Base_Ball_Bear%E3%81%AE%E6%9B%B2%29"; EventId="34"; Label="ドラマチック (Wikipedia)" }
)

$scriptDir = Split-Path $MyInvocation.MyCommand.Path -Parent
$dataPath  = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "..\data\sentiment-manual.json"))
$docsPath  = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "..\docs\data\sentiment-manual.json"))

$raw  = [System.IO.File]::ReadAllText($dataPath, [System.Text.Encoding]::UTF8)
$data = $raw | ConvertFrom-Json

$totalAdded = 0

foreach ($entry in $urlMapping) {
    $apiUrl  = "https://b.hatena.ne.jp/entry/json/?url=" + [Uri]::EscapeDataString($entry.Url)
    $eventId = $entry.EventId
    $label   = $entry.Label

    Write-Host ""
    Write-Host "== $label -> event_id=$eventId"

    $resp = $null
    try {
        $resp = Invoke-RestMethod -Uri $apiUrl -Method Get -ErrorAction Stop
    } catch {
        Write-Warning "  APIError: $_"
    }

    if ($null -ne $resp -and $null -ne $resp.bookmarks) {
        $bookmarks = $resp.bookmarks | Where-Object { $_.comment -and $_.comment.Trim() -ne "" }
        Write-Host "  comment bookmarks: $($bookmarks.Count)"

        $eventEntry = $data | Where-Object { $_.PSObject.Properties['event_id'] -and [string]$_.event_id -eq $eventId } | Select-Object -First 1
        if (-not $eventEntry) {
            Write-Host "  event_id=$eventId not found -> create"
            $eventEntry = [PSCustomObject]@{ event_id=$eventId; positive=@(); negative=@(); note="" }
            $data = @($data) + $eventEntry
        }

        $addedCount = 0
        foreach ($bm in $bookmarks) {
            $text = $bm.comment.Trim()
            if ($text.Length -gt 150) { $text = $text.Substring(0, 150) + "..." }

            $dup = $eventEntry.positive | Where-Object {
                ($_ -is [string] -and $_ -eq $text) -or ($null -ne $_.text -and $_.text -eq $text)
            }
            if (-not $dup) {
                $obj = [PSCustomObject]@{
                    text       = $text
                    source     = "Hatena Bookmark"
                    source_url = "https://b.hatena.ne.jp/entry/s/" + ($entry.Url -replace "^https://","")
                }
                if ($DryRun) {
                    Write-Host "  [DryRun] [$($bm.user)] $text"
                } else {
                    $eventEntry.positive = @($eventEntry.positive) + $obj
                }
                $addedCount++
            }
        }

        Write-Host "  added: $addedCount"
        $totalAdded += $addedCount
    } else {
        Write-Host "  no bookmarks (skip)"
    }
    Start-Sleep -Milliseconds 500
}

Write-Host ""
Write-Host "合計 $totalAdded 件"

if ($DryRun) {
    Write-Host "DryRun: 書き込みスキップ" -ForegroundColor Yellow
    exit 0
}

$utf8noBom = New-Object System.Text.UTF8Encoding $false
$json = $data | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($dataPath, $json, $utf8noBom)
Copy-Item -Path $dataPath -Destination $docsPath -Force
Write-Host "data/ + docs/data/ 同期完了" -ForegroundColor Green
