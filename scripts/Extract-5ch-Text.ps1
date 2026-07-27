#Requires -Version 5.1
<#
.SYNOPSIS
  5ch-raw の HTML から投稿テキストを抽出して data/5ch-text/ に保存する
#>
param(
    [string]$InputDir  = "data\5ch-raw",
    [string]$OutputDir = "data\5ch-text"
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$inPath  = Join-Path $projectRoot $InputDir
$outPath = Join-Path $projectRoot $OutputDir
New-Item -ItemType Directory -Force $outPath | Out-Null

function Strip-Html([string]$html) {
    $t = $html -replace '<br\s*/?>', "`n"
    $t = $t -replace '<[^>]+>', ''
    $t = $t -replace '&gt;',  '>'
    $t = $t -replace '&lt;',  '<'
    $t = $t -replace '&amp;', '&'
    $t = $t -replace '&nbsp;',' '
    $t = $t -replace '&#\d+;', ''
    return $t.Trim()
}

function Get-Encoding([string]$FilePath) {
    $bytes = [System.IO.File]::ReadAllBytes($FilePath)
    # BOM判定
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        return [System.Text.Encoding]::UTF8
    }
    # Content-Type meta で charset を探す (先頭4KB)
    $head = [System.Text.Encoding]::ASCII.GetString($bytes[0..[Math]::Min(4096,$bytes.Length-1)])
    if ($head -match 'charset=([a-zA-Z0-9_-]+)') {
        try { return [System.Text.Encoding]::GetEncoding($Matches[1]) } catch {}
    }
    return [System.Text.Encoding]::GetEncoding("Shift_JIS")
}

$files = Get-ChildItem $inPath -Filter "*.html" | Sort-Object Name
Write-Host "$($files.Count) ファイルを処理します"

foreach ($file in $files) {
    $outFile = Join-Path $outPath ($file.BaseName + ".txt")
    Write-Host "処理中: $($file.Name)"

    $enc  = Get-Encoding $file.FullName
    $html = [System.IO.File]::ReadAllText($file.FullName, $enc)

    # スレッドタイトル取得
    $title = ""
    if ($html -match '<title>([^<]+)</title>') { $title = $Matches[1].Trim() }

    # 各投稿を抽出 (id="N" class="... post")
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("=== $title ===")
    $lines.Add("ファイル: $($file.Name)")
    $lines.Add("")

    $postPat = [regex]'id="(\d+)"[^>]*class="[^"]*post[^"]*"'
    $contentPat = [regex]'class="post-content"[^>]*>(.*?)</div>'

    $matches2 = $postPat.Matches($html)
    foreach ($m in $matches2) {
        $num   = $m.Groups[1].Value
        $start = $m.Index

        # 日付を探す (このpost要素の中)
        $chunk = $html.Substring($start, [Math]::Min(600, $html.Length - $start))
        $date  = ""
        if ($chunk -match 'class="date">([^<]+)<') { $date = $Matches[1].Trim() }

        # post-content を探す
        $contentStart = $html.IndexOf('class="post-content"', $start)
        if ($contentStart -lt 0 -or $contentStart - $start -gt 2000) { continue }
        $bodyStart = $html.IndexOf('>', $contentStart) + 1
        $bodyEnd   = $html.IndexOf('</div>', $bodyStart)
        if ($bodyEnd -lt 0) { continue }
        $body = Strip-Html $html.Substring($bodyStart, $bodyEnd - $bodyStart)
        if ($body.Length -lt 2) { continue }

        $lines.Add("[${num}] ${date}")
        $lines.Add($body)
        $lines.Add("")
    }

    $utf8bom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllLines($outFile, $lines, $utf8bom)
    Write-Host "  → $($lines.Count) 行 ($($matches2.Count) 投稿)"
}

Write-Host "`n完了: $outPath"
