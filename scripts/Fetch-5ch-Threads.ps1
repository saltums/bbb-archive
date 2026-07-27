#Requires -Version 5.1
<#
.SYNOPSIS
  5ch の Base Ball Bear スレッドを「前スレ」リンクをたどって HTML 保存する

.PARAMETER StartUrl
  起点となるスレッド URL
.PARAMETER OutputDir
  保存先ディレクトリ (プロジェクトルートからの相対パス)
.PARAMETER DelaySeconds
  リクエスト間の待機秒数 (デフォルト 5 秒)
.PARAMETER MaxThreads
  さかのぼる最大スレッド数 (デフォルト 100)

.EXAMPLE
  .\Fetch-5ch-Threads.ps1
  .\Fetch-5ch-Threads.ps1 -StartUrl "https://mevius.5ch.io/test/read.cgi/musicjg/1589976243/" -MaxThreads 30
#>
param(
    [string]$StartUrl     = "https://mevius.5ch.io/test/read.cgi/musicjg/1589976243/",
    [string]$OutputDir    = "data\5ch-raw",
    [int]   $DelaySeconds = 5,
    [int]   $MaxThreads   = 100
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$outPath = Join-Path $projectRoot $OutputDir
New-Item -ItemType Directory -Force $outPath | Out-Null

$ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# --- スレッドHTML取得 ---
function Get-ThreadHtml([string]$Url) {
    $wc = New-Object System.Net.WebClient
    $wc.Headers["User-Agent"]      = $ua
    $wc.Headers["Accept"]          = "text/html,application/xhtml+xml,*/*;q=0.8"
    $wc.Headers["Accept-Language"] = "ja,en;q=0.5"
    $bytes = $wc.DownloadData($Url)
    $ct    = $wc.ResponseHeaders["Content-Type"]
    $enc   = [System.Text.Encoding]::UTF8
    if ($ct -match 'charset=([^\s;]+)') {
        try { $enc = [System.Text.Encoding]::GetEncoding($Matches[1].Trim()) } catch {}
    }
    return $enc.GetString($bytes)
}

# --- URLからスレッドID抽出 ---
function Get-ThreadId([string]$Url) {
    if ($Url -match '/(\d{9,12})/?$') { return $Matches[1] }
    return $null
}

# --- HTML から前スレ URL を抽出 ---
function Find-PrevUrl([string]$Html) {
    # 5ch/2ch系ドメインのURLパターン
    $domain  = 'https?://[a-z0-9]+\.(?:5ch\.(?:net|io)|2ch\.(?:net|sc))'
    $path    = '/test/read\.cgi/[a-z0-9]+/\d+'
    $anyUrl  = "${domain}${path}"

    # パターン1: 「前スレ」の後ろ 400字以内にURL
    if ($Html -match "前スレ[^<]{0,400}?($anyUrl)") {
        return (Normalize-Url $Matches[1].TrimEnd('/'))
    }
    # パターン2: href に URL があり、前後300字に「前スレ」
    $linkPat = "($anyUrl)"
    $m = [regex]::Matches($Html, $linkPat)
    foreach ($lm in $m) {
        $start = [Math]::Max(0, $lm.Index - 300)
        $ctx   = $Html.Substring($start, [Math]::Min(600, $Html.Length - $start))
        if ($ctx -match '前スレ') {
            return (Normalize-Url $lm.Value.TrimEnd('/'))
        }
    }
    return $null
}

# --- ドメイン正規化 ---
# mevius系 → 5ch.io、それ以外の旧サブドメイン → 2ch.sc アーカイブ
function Normalize-Url([string]$Url) {
    if ($Url -match '^https?://mevius\.') {
        return $Url -replace '\.5ch\.net/', '.5ch.io/' -replace '\.2ch\.net/', '.5ch.io/'
    }
    # echo, rio2016 など旧サブドメインは 2ch.sc へ
    return $Url -replace '\.5ch\.(net|io)/', '.2ch.sc/' -replace '\.2ch\.net/', '.2ch.sc/'
}

# --- メインループ ---
$currentUrl = $StartUrl.TrimEnd('/')
$count      = 0

Write-Host "=== 5ch BBB スレッドアーカイブ ==="
Write-Host "保存先 : $outPath"
Write-Host "起点   : $currentUrl"
Write-Host "最大   : $MaxThreads スレッド / 間隔 ${DelaySeconds}秒"
Write-Host ""

while ($currentUrl -and $count -lt $MaxThreads) {
    $count++
    $id = Get-ThreadId $currentUrl
    if (-not $id) {
        Write-Warning "スレッドID取得失敗: $currentUrl"
        break
    }

    $file = Join-Path $outPath "$id.html"

    if (Test-Path $file) {
        Write-Host "[$count] スキップ(保存済み) $id"
        $html = Get-Content $file -Raw -Encoding UTF8
    } else {
        Write-Host "[$count] 取得: $currentUrl"
        try {
            $html = Get-ThreadHtml $currentUrl
            [System.IO.File]::WriteAllText($file, $html, [System.Text.Encoding]::UTF8)
            $kb = [int]($html.Length / 1024)
            Write-Host "    保存: $id.html (${kb} KB)"
        } catch {
            Write-Warning "取得失敗 ($_) → 中断"
            break
        }
    }

    $prevUrl = Find-PrevUrl $html
    if ($prevUrl) {
        Write-Host "    前スレ → $prevUrl"
    } else {
        Write-Host "    前スレなし → 終了"
        break
    }

    $currentUrl = $prevUrl
    if ($count -lt $MaxThreads) {
        Start-Sleep -Seconds $DelaySeconds
    }
}

Write-Host ""
Write-Host "完了: $count スレッド / 保存先 $outPath"
