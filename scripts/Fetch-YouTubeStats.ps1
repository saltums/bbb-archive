<#
.SYNOPSIS
  YouTube Data API v3から公式チャンネルの動画一覧と再生回数を取得し、
  data/raw/youtube/ にキャッシュする。
.DESCRIPTION
  YouTube API開発者ポリシーにより、再生回数などの統計情報は取得から30日を超えて
  保持してはならない。そのため、このプロジェクトでは「定期的(30日以内目安)に
  再取得・再公開する」運用にすること。表示側には必ず取得日を明示する。

  APIキーは https://console.cloud.google.com/ で無料のプロジェクトを作成し、
  「YouTube Data API v3」を有効化した上でAPIキーを発行して取得する。
  チャットやコードに直接書かないこと。実行時に -ApiKey で渡すか、
  環境変数 YOUTUBE_API_KEY をあらかじめ設定しておくこと。
#>
param(
    [string]$ApiKey = $env:YOUTUBE_API_KEY,
    [string]$ChannelId = "UCT6xcaNMEM6t7sEFUNLI9sQ"  # Base Ball Bear Official YouTube
)

$ErrorActionPreference = "Stop"

if (-not $ApiKey) {
    throw "APIキーが指定されていません。-ApiKey <key> を渡すか、環境変数 YOUTUBE_API_KEY を設定してください。`n(取得先: https://console.cloud.google.com/ で「YouTube Data API v3」を有効化)"
}

$root = Split-Path -Parent $PSScriptRoot
$rawDir = Join-Path $root "data\raw\youtube"
if (-not (Test-Path $rawDir)) {
    New-Item -ItemType Directory -Path $rawDir -Force | Out-Null
} else {
    Get-ChildItem $rawDir -Filter "*.json" | Remove-Item -Force
}

# 1. アップロード動画一覧プレイリストIDを取得
$channelUrl = "https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id=$ChannelId&key=$ApiKey"
$channelRes = Invoke-RestMethod -Uri $channelUrl -TimeoutSec 30
$uploadsPlaylistId = $channelRes.items[0].contentDetails.relatedPlaylists.uploads
if (-not $uploadsPlaylistId) {
    throw "アップロード動画一覧プレイリストが見つかりませんでした。ChannelIdを確認してください。"
}
Write-Output "アップロード動画プレイリスト: $uploadsPlaylistId"

# 2. プレイリスト内の動画IDを全ページ取得
$videoIds = @()
$pageToken = $null
do {
    $url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId=$uploadsPlaylistId&key=$ApiKey"
    if ($pageToken) { $url += "&pageToken=$pageToken" }
    $res = Invoke-RestMethod -Uri $url -TimeoutSec 30
    $videoIds += $res.items | ForEach-Object { $_.snippet.resourceId.videoId }
    $pageToken = $res.nextPageToken
    Start-Sleep -Milliseconds 300
} while ($pageToken)

Write-Output "動画数: $($videoIds.Count)"

# 3. 動画IDを50件ずつまとめて統計情報を取得
$allStats = @()
for ($i = 0; $i -lt $videoIds.Count; $i += 50) {
    $batch = $videoIds[$i..[Math]::Min($i + 49, $videoIds.Count - 1)]
    $idsParam = $batch -join ","
    $url = "https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id=$idsParam&key=$ApiKey"
    $res = Invoke-RestMethod -Uri $url -TimeoutSec 30
    $allStats += $res.items
    Start-Sleep -Milliseconds 300
}

$outFile = Join-Path $rawDir "videos.json"
$allStats | ConvertTo-Json -Depth 10 | Out-File -FilePath $outFile -Encoding UTF8

Write-Output ""
Write-Output "完了: $($allStats.Count)件を $outFile にキャッシュしました。"
Write-Output "次は .\Parse-YouTubeStats.ps1 を実行してください。"
