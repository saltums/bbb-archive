<#
.SYNOPSIS
  Base Ball Bearの日本語版Wikipedia記事を取得し、data/raw/ にキャッシュする。
.DESCRIPTION
  data/timeline.json は手動でキュレーションした年表データだが、その元ネタとして
  Wikipedia記事の原文を再取得・再確認できるようにこのスクリプトを用意している。
  記事タイトルは "BASE BALL BEAR" ではなく "Base Ball Bear"(大文字小文字混在)が正式。
  再実行時はキャッシュ済みファイルがあればスキップする(--Forceで強制再取得)。
#>
param(
    [string]$Title = "Base Ball Bear",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$rawDir = Join-Path $root "data\raw"
if (-not (Test-Path $rawDir)) {
    New-Item -ItemType Directory -Path $rawDir -Force | Out-Null
}

$safeName = ($Title -replace '[^\w]', '_')
$outFile = Join-Path $rawDir "$safeName.json"

if ((Test-Path $outFile) -and -not $Force) {
    Write-Output "既にキャッシュ済み: $outFile (再取得するには -Force を指定)"
    return
}

$apiUrl = "https://ja.wikipedia.org/w/api.php?action=parse&page=$([uri]::EscapeDataString($Title))&prop=wikitext|revid&format=json"

Write-Output "取得中: $apiUrl"
$res = Invoke-RestMethod -Uri $apiUrl -UserAgent "baseball-bear-timeline/1.0 (personal fan archive project)" -TimeoutSec 30

if ($res.error) {
    throw "Wikipedia APIエラー: $($res.error.info)"
}

$res | ConvertTo-Json -Depth 10 | Out-File -FilePath $outFile -Encoding utf8
Write-Output "保存しました: $outFile (revid=$($res.parse.revid))"
Write-Output ""
Write-Output "このファイルは参照用の原文キャッシュです。data/timeline.json への反映は手動で行ってください"
Write-Output "(年表イベントの抽出は自動判定の精度が低いため、目視での取捨選択を前提にしています)。"
