<#
.SYNOPSIS
  setlist.fm APIからBase Ball Bearのセットリストを取得し、data/raw/setlists/ にキャッシュする。
.DESCRIPTION
  setlist.fm APIの利用規約(https://www.setlist.fm/help/api-terms)により、取得データを
  無期限に保持し続けることは認められておらず、「short periods」のキャッシュのみ許可されている。
  このプロジェクトではこのキャッシュを「定期的に手動で再取得・再公開する」運用にすることで
  対応する(サイトを立ち上げっぱなしで一度も更新しない、という使い方はしないこと)。
  新しいライブがあったら、このスクリプト → Parse-Setlists.ps1 → Sync-Docs.ps1 の順で再実行し、
  公開データを更新すること。

  APIキーは https://www.setlist.fm/settings/api で無料登録(非商用利用のみ)。
  チャットやコードにAPIキーを直接書かないこと。実行時に -ApiKey で渡すか、
  環境変数 SETLISTFM_API_KEY をあらかじめ設定しておくこと。
#>
param(
    [string]$ApiKey = $env:SETLISTFM_API_KEY,
    [string]$Mbid = "b3b24a1d-78b4-40c9-98ef-19fb812b067a"  # Base Ball Bear (MusicBrainz)
)

$ErrorActionPreference = "Stop"

if (-not $ApiKey) {
    throw "APIキーが指定されていません。-ApiKey <key> を渡すか、環境変数 SETLISTFM_API_KEY を設定してください。`n(取得先: https://www.setlist.fm/settings/api )"
}

$root = Split-Path -Parent $PSScriptRoot
$rawDir = Join-Path $root "data\raw\setlists"
if (-not (Test-Path $rawDir)) {
    New-Item -ItemType Directory -Path $rawDir -Force | Out-Null
} else {
    Get-ChildItem $rawDir -Filter "page-*.json" | Remove-Item -Force
}

$headers = @{
    "x-api-key"       = $ApiKey
    "Accept"          = "application/json"
    "Accept-Language" = "ja"
}

$page = 1
$totalFetched = 0
$totalItems = $null

do {
    $url = "https://api.setlist.fm/rest/1.0/artist/$Mbid/setlists?p=$page"
    Write-Output "取得中 (page $page): $url"
    $res = Invoke-RestMethod -Uri $url -Headers $headers -UserAgent "baseball-bear-timeline/1.0 (personal fan archive project)" -TimeoutSec 30

    $outFile = Join-Path $rawDir "page-$page.json"
    $res | ConvertTo-Json -Depth 20 | Out-File -FilePath $outFile -Encoding UTF8

    if ($null -eq $totalItems) { $totalItems = [int]$res.total }
    $totalFetched += $res.setlist.Count
    Write-Output "  -> $($res.setlist.Count)件 (累計 $totalFetched / $totalItems)"

    $page++
    Start-Sleep -Milliseconds 800  # 礼儀としてのリクエスト間隔
} while ($totalFetched -lt $totalItems -and $res.setlist.Count -gt 0)

Write-Output ""
Write-Output "完了: $totalFetched 件のセットリストを $rawDir にキャッシュしました。"
Write-Output "次は .\Parse-Setlists.ps1 を実行してください。"
