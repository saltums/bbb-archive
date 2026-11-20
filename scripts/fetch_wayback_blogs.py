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
SOURCES = [
    ("seiryu", "小出の旧ホームページ（曖昧日記・旧小出日記）", "小出祐介", "www.venus.dti.ne.jp/~seiryu/", r"\.html?$|/~seiryu/?$", r"bbs"),
    ("official-com", "公式サイト（日記）", "", "www.baseballbear.com/", r"cgi-bin/(epad|diary|hamripo)|aimaidiary|newpage\d*\.html|artist/profile|news/detail", r"\.(css|js|swf|xml|jpg|gif|png)$"),
    ("official-net", "公式サイト旧ドメイン（日記）", "", "www.baseballbear.net/", r"cgi-bin/(epad|diary|hamripo)|swf/info\d*\.html", r"\.(css|js|swf|xml|jpg|gif|png)$"),
    ("playlog-koide", "小出メッセ（playlog）", "小出祐介", "playlog.jp/koide/", r"/blog", r"#"),
    ("playlog-sekine", "しおり暮らし（playlog）", "関根史織", "playlog.jp/sekine/", r"/blog", r"#"),
    ("playlog-syohei", "湯浅将平のブログ（playlog）", "湯浅将平", "playlog.jp/syohei/", r"/blog", r"#"),
    ("playlog-hori", "堀之内大介のブログ（playlog）", "堀之内大介", "playlog.jp/horinouchi/", r"/blog", r"#"),
    ("bokuburo", "ボクブロ（seesaa）", "", "baseballbearblog.seesaa.net/", r"/article/\d+\.html|/archives/\d+-\d+\.html|/index-?\d*\.html|seesaa\.net/?$", r"upload|\.css|\.ico|robots"),
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


def plan():
    """取るページ: 同じURLは1つ（いちばん新しい保存）。日記は記事ごとにURLがあるので、それで足りる。"""
    jobs = []
    for sid, label, author, prefix, inc, exc in SOURCES:
        rows = cdx(prefix)
        time.sleep(3)
        seen = {}
        for ts, original, mime, digest in rows:
            if "html" not in mime and "text" not in mime:
                continue
            if not re.search(inc, original) or (exc and re.search(exc, original)):
                continue
            key = norm_url(original)
            seen[key] = {"source": sid, "ts": ts, "url": original, "norm": key, "digest": digest}
        jobs.extend(seen.values())
        print(f"  {label}: {len(seen)} ページ（保存の数 {len(rows)}）", flush=True)
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--replan", action="store_true", help="取る予定を作り直す")
    args = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    man = json.load(open(MANIFEST, encoding="utf-8")) if os.path.exists(MANIFEST) else {"sources": {}, "pages": {}}
    if args.replan or not man.get("plan"):
        print("保存の一覧を確認しています…", flush=True)
        man["plan"] = plan()
        man["sources"] = {s[0]: {"label": s[1], "author": s[2], "prefix": s[3]} for s in SOURCES}
        json.dump(man, open(MANIFEST, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=0)
    todo = [j for j in man["plan"] if f'{j["norm"]}|{j["digest"]}' not in man["pages"]]
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
