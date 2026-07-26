# Base Ball Bear 年表(BBB Chronicle)

バンド「Base Ball Bear」の結成(2001年)から現在までを横軸タイムラインで振り返る、非公式のファン制作アーカイブサイトです。Node/Python不要、PowerShellスクリプトのみで構成しています([six-dog-archive](../six-dog-archive/)と同じ方針)。

スマホでも見やすいよう、縦一本のリスト形式(上が最新、下が結成当時)になっています。ページ下部にメンバー各自のSNSリンクも掲載。直近5年より前には区切り線が入ります。各イベントには`importance`(`major`/`minor`)があり、主要な出来事は大きく強調、シングル等の詳細情報は小さく控えめに表示することで、情報量が多くても全体像(マクロ)と細部(ミクロ)の両方を見渡せるようにしています。「主要な出来事のみ表示」トグルで詳細を一時的に隠すこともできます。

## 構成

```
scripts/
  Fetch-Wikipedia.ps1   Wikipedia記事を取得し data/raw/ にキャッシュ(参照用)
  Fetch-Setlists.ps1    setlist.fm APIからセットリストを取得(要APIキー)
  Parse-Setlists.ps1    取得データ+手動データをマージしてdata/setlists.jsonを生成
  Sync-Docs.ps1         data/*.json を整形して docs/data/ にコピー(公開用データ同期)
  Serve-Docs.ps1        ローカルプレビュー用の最小サーバー(GitHub Pagesでは不要)
data/
  raw/                     取得した原文キャッシュ(Wikipedia・setlist.fm)
  timeline.json            年表データの正(唯一のソース)
  setlists.json            セットリスト統計データ(Parse-Setlists.ps1が生成)
  setlists-manual.json     LiveFans/X/2ch等を確認して手動追加するセットリスト
  sentiment-manual.json    各年表イベントの「当時の反応(世論)」手動入力欄
  updates-manual.json      公式LINE等の最新情報を手動追記する欄
  songs.json               アルバム収録曲一覧(Wikipediaの個別アルバム記事から手動キュレーション)
docs/                   GitHub Pages 公開ルート(素のHTML/CSS/JS、ビルド不要)
  index.html / app.js       年表(トップページ)
  setlists.html / .js       セットリスト統計ダッシュボード
  updates.html / .js        最新情報フィード
  songs.html / .js          楽曲一覧(アルバムごとの収録曲、開閉式)
  data/                     公開用データ(Sync-Docs.ps1が生成)
```

## 年表データの編集方法

`data/timeline.json` を直接編集し、保存後に以下を実行して公開用データへ反映します。

```powershell
.\scripts\Sync-Docs.ps1
```

各イベントのフィールド:

| フィールド | 内容 |
|---|---|
| `date` | `YYYY-MM-DD` (月・年までしか分からない場合は `date_precision` で明示) |
| `date_precision` | `day` / `month` / `year` |
| `type` | `release`(リリース) / `live`(ライブ) / `milestone`(できごと) |
| `title` / `description` | 表示テキスト |
| `source_url` / `source_label` | 出典 |
| `embed` | 任意。Spotifyの場合 `{ "provider": "spotify", "kind": "album" or "track", "id": "..." }` |
| `external_links` | 任意。`[{ "label": "...", "url": "..." }]`(例: LiveFansのセットリストページ) |
| `date_confidence` | 任意。`"estimated"` で「時期は推定」の表記を出す |
| `importance` | `major`(主要、大きく強調表示) / `minor`(詳細、小さく控えめに表示)。省略時は`major`扱い |

## セットリスト統計

setlist.fm APIから自動取得できますが、同APIの利用規約により**データを無期限に保持することはできません**(短期キャッシュのみ許可)。そのため、新しいライブがあった際に以下を再実行して「取得し直して公開し直す」運用にしてください。

```powershell
.\scripts\Fetch-Setlists.ps1 -ApiKey "あなたのsetlist.fm APIキー"
.\scripts\Parse-Setlists.ps1
.\scripts\Sync-Docs.ps1
```

APIキーは https://www.setlist.fm/settings/api で無料取得(非商用利用のみ)。**チャットやコードには直接書かず、実行時にのみ渡してください。**

setlist.fmに無いライブ(LiveFans/X/2ch等で確認したもの)は `data/setlists-manual.json` にサンプルを参考に追記すれば、次回の`Parse-Setlists.ps1`実行時に取り込まれます。

setlist.fm由来のデータには利用規約上、出典リンク("Source: ... setlist on setlist.fm")の表示が必須です(実装済み・削除しないこと)。

## YouTube再生回数ランキング

公式YouTubeチャンネルの動画を再生回数順に表示します(セットリスト統計ページ内)。YouTube API開発者ポリシーにより**統計情報は取得から30日を超えて保持できない**ため、setlist.fmと同様に定期的な再取得が必要です。

```powershell
.\scripts\Fetch-YouTubeStats.ps1 -ApiKey "あなたのYouTube Data APIキー"
.\scripts\Parse-YouTubeStats.ps1
.\scripts\Sync-Docs.ps1
```

APIキーは https://console.cloud.google.com/ でプロジェクトを作成し「YouTube Data API v3」を有効化して発行(無料枠あり)。**チャットやコードには直接書かないこと。**

取得日は自動的に画面上に表示されます(統計はスナップショットであることを明示するため)。

## 当時の反応(2ch世論要約)・最新情報(LINE)の入力方法

どちらも自動収集はせず、あなたが確認した内容を手動で追記する方式です。

- `data/sentiment-manual.json`: `event_id`(timeline.jsonのid)ごとに `positive` / `negative` を箇条書きで追加。年表の該当イベント詳細に「当時の反応」として表示されます。
- `data/updates-manual.json`: サンプルを参考に1件ずつ追加。`updates.html`に新着順で表示されます。画像は著作権上、転載せずテキストで要約すること。

編集後は `.\scripts\Sync-Docs.ps1` を実行してください(未入力の空エントリは自動的に除外されます)。

## 楽曲一覧

`docs/songs.html`。バンド本体のWikipedia記事には収録曲リストが無いため、**専用記事がある作品(アルバム・シングル)のみ**`data/songs.json`に手動でまとめています(2026-07-26時点で26作品、のべ153曲。カップリング曲・カラオケ版等も含む)。インディーズ時代唯一のミニアルバム『夕方ジェネレーション』・シングル『YUME is VISION』も収録済み。専用記事が無い作品は未収録です。`type`フィールドは`album`/`single`/`ep`(省略時は`album`扱い)。新しい作品にWikipedia専用記事ができ次第、同じ形式で追記してください。

## ローカルプレビュー

```powershell
.\scripts\Serve-Docs.ps1
```

`http://localhost:8090/` を開く。

## 著作権について

CDジャケット画像等は直接掲載せず、Spotifyの公式Embedウィジェットにリンクする形で対応しています。年表データの一次情報は主に[Wikipedia「Base Ball Bear」](https://ja.wikipedia.org/wiki/Base_Ball_Bear)と[公式サイトのニュース](https://www.baseballbear.com/sp/news/)。セットリストデータは[setlist.fm](https://www.setlist.fm/)提供。
