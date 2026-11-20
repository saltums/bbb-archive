#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""今は消えたメンバーの日記・ブログを、Internet Archive（Wayback Machine）の保存分から取り戻す。

  python scripts/fetch_wayback_blogs.py            # 未取得分を取る（途中で止めても続きから）
  python scripts/fetch_wayback_blogs.py --list     # 取る予定のページ数だけ見る

保存先は data/blog-archive/（公開リポジトリには載せない）。生のバイト列のまま保存する。
"""
import argparse, datetime, json, os, re, sys, time, urllib.parse, urllib.request, urllib.error

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "blog-archive")
RAW = os.path.join(OUT, "raw")
MANIFEST = os.path.join(OUT, "manifest.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
DELAY = 2.5

# (id, 表示名, 書いた人, 保存の接頭辞, 取るページ, 外すページ)
# 公式に出たものは全部残す。中身が入れ替わる一覧ページ（LIST）は、月ごとに別の版として残す。
ASSETS = r"\.(css|js|swf|xml|jpg|jpeg|gif|png|ico|mp3|wav|zip|pdf)(\?|$)|/wp-(content|includes)/|/asset/|/img/|/images/"
SOURCES = [
    ("seiryu", "小出の旧ホームページ（曖昧日記・旧小出日記）", "小出祐介", "www.venus.dti.ne.jp/~seiryu/", r"\.html?$|/~seiryu/?$", r"bbs"),
    ("official-com", "公式サイト baseballbear.com", "", "www.baseballbear.com/", r".", ASSETS + r"|/related/|cgi-sys"),
    ("official-net", "公式サイト baseballbear.net", "", "www.baseballbear.net/", r".", ASSETS + r"|/related/|cgi-sys|check_image"),
    # 事務所（sma.co.jp）は robots.txt で Claude を全面禁止しているので、直接もアーカイブ経由も取らない
    ("universal", "ユニバーサルのバンドページ", "", "www.universal-music.co.jp/base-ball-bear/", r".", ASSETS),
    ("tumblr", "公式 tumblr", "", "baseballbearofficial.tumblr.com/", r"/post/|/page/|tumblr\.com/?$", ASSETS + r"|/image/"),
    ("playlog-koide", "小出メッセ（playlog）", "小出祐介", "playlog.jp/koide/", r"/blog", r"#"),
    ("playlog-sekine", "しおり暮らし（playlog）", "関根史織", "playlog.jp/sekine/", r"/blog", r"#"),
    ("playlog-syohei", "湯浅将平のブログ（playlog）", "湯浅将平", "playlog.jp/syohei/", r"/blog", r"#"),
    ("playlog-hori", "堀之内大介のブログ（playlog）", "堀之内大介", "playlog.jp/horinouchi/", r"/blog", r"#"),
    # ボクブロの robots.txt は /archives/ /upload/ /tag/ /comment などを禁止しているので、記事と目次だけ
    ("bokuburo", "ボクブロ（seesaa）", "", "baseballbearblog.seesaa.net/", r"/article/\d+\.html|/index-?\d*\.html|seesaa\.net/?$", r"/archives/|/upload|/tag/|comment|\.css|\.ico|robots"),
    ("livedoor", "livedoor ブログ baseballbear", "", "blog.livedoor.jp/baseballbear/", r"archives|/baseballbear/?$", r"\.(css|js|jpg|gif|png)$"),
    ("jfn", "JFN 番組ブログ", "", "www2.jfn.co.jp/bbb/", r"/blog", r"\.(css|js|jpg|gif|png)$"),
    ("emi", "EMI のバンドページ", "", "www.toshiba-emi.co.jp/capitol/bbb/", r"\.html?$|\.php|/bbb/?$", r""),
    ("emi2", "EMI のバンドページ（emimusic）", "", "www.emimusic.jp/capitol/bbb/", r"\.html?$|\.php|/bbb/?$", r""),
]


def http(url, tries=5):
    wait = 10
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(wait); wait = min(wait * 2, 300); continue
            return e.code, b""
        except Exception:
            time.sleep(wait); wait = min(wait * 2, 300)
    return 0, b""


def cdx(prefix):
    q = urllib.parse.urlencode({"url": prefix, "matchType": "prefix", "fl": "timestamp,original,mimetype,digest",
                                "filter": ["statuscode:200"], "output": "json"}, doseq=True)
    status, body = http("http://web.archive.org/cdx/search/cdx?" + q)
    rows = json.loads(body or b"[]")
    return rows[1:] if rows else []


def norm_url(u):
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r":80(?=/)", "", u).replace("%7E", "~").replace("%7e", "~")
    return u.split("#")[0].rstrip("/")


def safe_name(u):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", u)[:180]


# 中身が入れ替わるページ（トップ・お知らせ一覧・ライブ一覧・告知の掲示板・事務所のデータ）
LIST = re.compile(r"(baseballbear\.(com|net)(/(index\d*\.html?|sp|top\.html?|swf/info\d*\.html|news(/index\.html)?|live(/index\.html)?|info|media|disc|disco|bio)?)?/?$)"
                  r"|kokuchi\.cgi|/artist/json/|seesaa\.net/?$|/index-?\d*\.html$|universal-music\.co\.jp/base-ball-bear(/news)?/?$")


def plan():
    """取るページ: ふつうは同じURLにつき1つ（いちばん新しい保存）。
    中身が入れ替わる一覧ページは、内容が違う保存を月に1つずつ取る（過去のお知らせを取りこぼさないため）。"""
    jobs = []
    for sid, label, author, prefix, inc, exc in SOURCES:
        rows = cdx(prefix)
        time.sleep(4)
        seen = {}
        for ts, original, mime, digest in rows:
            if not any(k in mime for k in ("html", "text", "json", "javascript")):
                continue
            if not re.search(inc, original) or (exc and re.search(exc, original)):
                continue
            key = norm_url(original)
            if sid == "sma-json":
                key = re.sub(r"\?.*$", "", key)
            if LIST.search(key):
                seen.setdefault((key, ts[:6], digest), {"source": sid, "ts": ts, "url": original, "norm": key, "digest": digest})
            else:
                seen[(key,)] = {"source": sid, "ts": ts, "url": original, "norm": key, "digest": digest}
        # 同じ月の同じ内容（digest）は1つに
        uniq = {}
        for j in seen.values():
            uniq.setdefault((j["norm"], j["digest"]), j)
        jobs.extend(uniq.values())
        print(f"  {label}: {len(uniq)} ページ（保存の数 {len(rows)}）", flush=True)
    return jobs


ORDER = ["seiryu", "official-diary", "playlog-koide", "playlog-sekine", "playlog-syohei", "playlog-hori", "livedoor",
         "bokuburo", "jfn", "sma-json", "universal", "emi", "emi2", "tumblr", "official-com", "official-net", "official-bbs"]


def priority(j):
    """日記・ブログ → お知らせのデータ → レーベル → 公式サイトのほかのページ → ファンの掲示板 の順に取る。"""
    s = j["source"]
    if s.startswith("official"):
        s = "official-bbs" if "epad" in j["norm"] else "official-diary" if re.search(r"cgi-bin/(diary|hamripo)|aimaidiary", j["norm"]) else s
    return (ORDER.index(s) if s in ORDER else len(ORDER), j["norm"], j["ts"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--replan", action="store_true", help="取る予定を作り直す")
    args = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    man = json.load(open(MANIFEST, encoding="utf-8")) if os.path.exists(MANIFEST) else {"sources": {}, "pages": {}}
    if args.replan or not man.get("plan"):
        print("保存の一覧を確認しています…", flush=True)
        man["plan"] = sorted(plan(), key=priority)
        man["sources"] = {s[0]: {"label": s[1], "author": s[2], "prefix": s[3]} for s in SOURCES}
        json.dump(man, open(MANIFEST, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=0)
    # 一覧ページ以外は、同じURLを一度取っていればそれで足りる（保存の時期が違っても取り直さない）
    have = {p["url"] and norm_url(p["url"]) for p in man["pages"].values() if p.get("file")}
    todo = [j for j in man["plan"] if f'{j["norm"]}|{j["digest"]}' not in man["pages"]
            and (LIST.search(j["norm"]) or j["norm"] not in have)]
    print(f"取る予定 {len(man['plan'])} ページ / 残り {len(todo)} ページ", flush=True)
    if args.list:
        return
    for i, j in enumerate(todo, 1):
        url = f'https://web.archive.org/web/{j["ts"]}id_/{j["url"]}'
        status, body = http(url)
        name = f'{j["source"]}/{safe_name(j["norm"])}__{j["ts"]}.html'
        if status == 200 and body:
            os.makedirs(os.path.join(RAW, j["source"]), exist_ok=True)
            open(os.path.join(RAW, name), "wb").write(body)
        man["pages"][f'{j["norm"]}|{j["digest"]}'] = {"source": j["source"], "ts": j["ts"], "url": j["url"],
                                                     "file": name if status == 200 else None, "status": status}
        if i % 25 == 0 or i == len(todo):
            json.dump(man, open(MANIFEST, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=0)
            print(f"[{i}/{len(todo)}] {datetime.datetime.now():%H:%M} {j['source']} {j['norm'][:70]}", flush=True)
        time.sleep(DELAY)
    ok = sum(1 for p in man["pages"].values() if p["file"])
    print(f"完了: 保存 {ok} / 失敗 {len(man['pages']) - ok}", flush=True)


if __name__ == "__main__":
    main()
