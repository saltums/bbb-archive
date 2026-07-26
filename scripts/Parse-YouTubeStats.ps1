<#
.SYNOPSIS
  data/raw/youtube/videos.json を整形し、data/youtube-stats.json を生成する。
.DESCRIPTION
  YouTube API開発者ポリシーに基づき、取得日(fetched_at)を必ず記録し、
  フロント側で表示すること(統計は取得時点のスナップショットであることを明示する)。
#>
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$rawFile = Join-Path $root "data\raw\youtube\videos.json"
$outPath = Join-Path $root "data\youtube-stats.json"

if (-not (Test-Path $rawFile)) {
    Write-Warning "$rawFile が見つかりません。先に .\Fetch-YouTubeStats.ps1 を実行してください。"
    "[]" | Out-File -FilePath $outPath -Encoding UTF8
    return
}

$raw = Get-Content $rawFile -Raw -Encoding UTF8 | ConvertFrom-Json

$videos = @()
foreach ($v in $raw) {
    $videos += [ordered]@{
        id          = $v.id
        title       = $v.snippet.title
        publishedAt = $v.snippet.publishedAt.Substring(0, 10)
        viewCount   = [int64]$v.statistics.viewCount
        url         = "https://www.youtube.com/watch?v=$($v.id)"
    }
}

$sortedVideos = @($videos | Sort-Object -Property viewCount -Descending)

$result = [ordered]@{
    fetched_at = (Get-Date -Format "yyyy-MM-dd")
    videos     = $sortedVideos
}

$result | ConvertTo-Json -Depth 10 | Out-File -FilePath $outPath -Encoding UTF8
Write-Output "生成しました: $outPath ($($sortedVideos.Count)件)"
