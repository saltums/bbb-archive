<#
.SYNOPSIS
  data/raw/setlists/*.json (setlist.fm APIの生データ) と data/setlists-manual.json
  (LiveFans/X/2ch等をご自身で確認して手入力したデータ) をマージし、data/setlists.json を生成する。
.DESCRIPTION
  setlist.fm由来のデータは同APIの利用規約に基づき、出典URLを保持し(source_url)、
  フロント側で "Source: ... setlist on setlist.fm" 形式のリンクを必ず表示すること。
#>
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$rawDir = Join-Path $root "data\raw\setlists"
$manualPath = Join-Path $root "data\setlists-manual.json"
$outPath = Join-Path $root "data\setlists.json"

function Convert-SetlistFmDate($d) {
    # setlist.fm の eventDate は "dd-MM-yyyy" 形式
    $parts = $d -split "-"
    return "$($parts[2])-$($parts[1])-$($parts[0])"
}

$normalized = @()

if (Test-Path $rawDir) {
    $pages = Get-ChildItem $rawDir -Filter "page-*.json" | Sort-Object Name
    foreach ($pageFile in $pages) {
        $data = Get-Content $pageFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($sl in $data.setlist) {
            $sets = @()
            if ($sl.sets -and $sl.sets.set) {
                foreach ($s in $sl.sets.set) {
                    $songs = @()
                    if ($s.song) {
                        foreach ($song in $s.song) {
                            if ($song.name) { $songs += $song.name }
                        }
                    }
                    if ($songs.Count -gt 0) {
                        $label = if ($s.encore) { if ($s.name) { $s.name } else { "Encore" } } else { if ($s.name) { $s.name } else { "Main" } }
                        $sets += [ordered]@{ label = $label; songs = $songs }
                    }
                }
            }
            if ($sets.Count -eq 0) { continue }  # 曲目データが無いセットリストは除外

            $city = if ($sl.venue.city.name) { "$($sl.venue.city.name), $($sl.venue.city.country.name)" } else { "" }

            $normalized += [ordered]@{
                id          = "sf-$($sl.id)"
                source      = "setlistfm"
                source_label = "setlist.fm"
                source_url  = $sl.url
                date        = Convert-SetlistFmDate $sl.eventDate
                tour        = if ($sl.tour.name) { $sl.tour.name } else { $null }
                venue       = $sl.venue.name
                city        = $city
                sets        = $sets
                note        = $null
            }
        }
    }
} else {
    Write-Warning "$rawDir が見つかりません。先に .\Fetch-Setlists.ps1 を実行してください。"
}

if (Test-Path $manualPath) {
    $manual = Get-Content $manualPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($m in $manual) {
        if (-not $m.id) { continue }  # テンプレートのコメント行をスキップ
        $normalized += $m
    }
}

$sorted = @($normalized | Sort-Object -Property date -Descending)

# PowerShell 5.1のConvertTo-Jsonは要素0件だと空文字、1件だと配列でなく単一オブジェクトを
# 返してしまうため、常にJSON配列になるよう明示的に組み立てる。
if ($sorted.Count -eq 0) {
    $json = "[]"
} elseif ($sorted.Count -eq 1) {
    $json = "[" + ($sorted[0] | ConvertTo-Json -Depth 10) + "]"
} else {
    $json = $sorted | ConvertTo-Json -Depth 10
}
$json | Out-File -FilePath $outPath -Encoding UTF8
Write-Output "生成しました: $outPath ($($sorted.Count)件)"
