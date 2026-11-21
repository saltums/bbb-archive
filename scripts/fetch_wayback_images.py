#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公式アーカイブの記事に出てくる画像を Internet Archive から取り、data/blog-archive/images/ に保存する。
取る画像の一覧は blogs.sqlite の images 表（build_blog_db.py が記事から取り出したもの）。
途中で止めても、もう一度動かせば続きから取る。

  python scripts/build_blog_db.py        # 先に画像の一覧を作る
  python scripts/fetch_wayback_images.py
  python scripts/build_blog_db.py        # 取れた画像を DB に反映
"""
import argparse, datetime, hashlib, io, json, os, re, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bbb_images import IMG_DIR, IMG_MANIFEST, OUT, local_name

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
DELAY = 2.5
# ジャケット写真。手元と pCloud にだけ置き、公開のサイトには出さない
JACKET = re.compile(r"umgi\.net/products/|/jacket|_jk|jk_|/disc/img/|/disco/img/|/album/img/|/single/img/", re.I)


def http(url, tries=5):
    wait = 10
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r.read(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(wait); wait = min(wait * 2, 300); continue
            return e.code, b"", ""
        except Exception:
            time.sleep(wait); wait = min(wait * 2, 300)
    return 0, b"", ""


def describe(data):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        return im.width, im.height, (im.format or "").lower()
    except Exception:
        return None, None, ""


def key(u):
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r":80(?=/)", "", u)
    host, _, rest = u.partition("/")
    return host.lower().removeprefix("www.") + "/" + rest


def archived(urls):
    """保存されている画像の一覧（key → 保存日時）を、場所（ホスト＋最初のフォルダ）ごとに CDX でまとめて引く。"""
    groups = {}
    for u in urls:
        k = key(u)
        host, _, rest = k.partition("/")
        groups.setdefault(host + "/" + (rest.split("/")[0] + "/" if "/" in rest else ""), []).append(u)
    found = {}
    for i, (prefix, us) in enumerate(sorted(groups.items()), 1):
        q = urllib.parse.urlencode({"url": prefix, "matchType": "prefix", "fl": "timestamp,original",
                                    "filter": "statuscode:200", "output": "json", "collapse": "urlkey"})
        status, body, _ = http("http://web.archive.org/cdx/search/cdx?" + q)
        rows = json.loads(body or b"[]")[1:] if status == 200 else None
        if rows is None:  # 一覧が引けない場所は、1枚ずつ当たる
            for u in us:
                found[key(u)] = None
        else:
            for ts, original in rows:
                found.setdefault(key(original), ts)
        print(f"  保存の一覧 {i}/{len(groups)} {prefix} {len(us)} 枚中 {sum(1 for u in us if key(u) in found)} 枚あり", flush=True)
        time.sleep(3)
    return found


def save(man):
    tmp = IMG_MANIFEST + ".tmp"
    json.dump(man, open(tmp, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=0)
    os.replace(tmp, IMG_MANIFEST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--retry", action="store_true", help="前に失敗した画像も取り直す")
    ap.add_argument("--source", help="この置き場所（カンマ区切り）の画像だけ")
    args = ap.parse_args()
    man = json.load(open(IMG_MANIFEST, encoding="utf-8")) if os.path.exists(IMG_MANIFEST) else {}
    con = sqlite3.connect(os.path.join(OUT, "blogs.sqlite"))
    rows = con.execute("SELECT url, source, wayback_ts FROM images ORDER BY source, first_date").fetchall()
    thumbs = dict(con.execute("SELECT url, thumb FROM images WHERE thumb IS NOT NULL"))
    if args.source:
        rows = [r for r in rows if r[1] in args.source.split(",")]
    con.close()  # 取得中に DB を作り直せるよう、すぐ閉じる
    # 一時的に取れなかったもの（status 0・5xx・429）は毎回取り直す。--retry なら保存なし以外も全部
    todo = [r for r in rows if r[0] not in man or (not man[r[0]].get("file") and
            (args.retry or man[r[0]].get("status") in (0, 429, 500, 502, 503, 504)))]
    print(f"画像 {len(rows)} 枚 / 取得済み {len(rows) - len(todo)} / 残り {len(todo)}", flush=True)
    if args.list:
        return
    found = archived([r[0] for r in todo] + [thumbs[r[0]] for r in todo if r[0] in thumbs])
    via = {}
    for url, source, ts in todo:
        if key(url) not in found and url in thumbs and key(thumbs[url]) in found:
            via[url] = thumbs[url]   # 大きい方は残っていない。縮小版を取る
            continue
        if key(url) not in found:
            man[url] = {"source": source, "ts": ts, "status": 404, "file": None, "note": "保存なし"}
    save(man)
    todo = [r for r in todo if key(r[0]) in found or r[0] in via]
    print(f"保存がある画像 {len(todo)} 枚を取ります", flush=True)
    by_sha = {m["sha1"]: u for u, m in man.items() if m.get("sha1")}
    for i, (url, source, ts) in enumerate(todo, 1):
        src = via.get(url, url)
        status, data, ctype = http(f"https://web.archive.org/web/{found[key(src)] or ts}id_/{src}")
        rec = {"source": source, "ts": ts, "status": status, "file": None}
        if src != url:
            rec["note"] = "縮小版"
        if status == 200 and data and not ctype.startswith("text/"):
            w, h, fmt = describe(data)
            if w:
                sha = hashlib.sha1(data).hexdigest()
                name = local_name(source, src)
                path = os.path.join(IMG_DIR, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "wb").write(data)
                kind = ("ui" if len(data) < 2500 or min(w, h) < 48 else
                        "jacket" if JACKET.search(url) else "photo")
                rec.update(file=name, bytes=len(data), width=w, height=h, format=fmt, sha1=sha, kind=kind)
                if sha in by_sha and by_sha[sha] != url:
                    rec["same_as"] = by_sha[sha]
                by_sha.setdefault(sha, url)
            else:
                rec["status"] = -1  # 画像として読めない（保存ページの差し替えなど）
        man[url] = rec
        if i % 25 == 0 or i == len(todo):
            save(man)
            ok = sum(1 for m in man.values() if m.get("file"))
            print(f"[{i}/{len(todo)}] {datetime.datetime.now():%H:%M} 保存 {ok} {source} {url[:70]}", flush=True)
        time.sleep(DELAY)
    save(man)
    ok = sum(1 for m in man.values() if m.get("file"))
    print(f"完了: 保存 {ok} / 取れず {len(man) - ok}", flush=True)


if __name__ == "__main__":
    main()
