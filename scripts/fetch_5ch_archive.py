#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5ch の Base Ball Bear スレッドを、前スレ・過去スレのリンクをたどって生HTMLのまま保存する。

  python scripts/fetch_5ch_archive.py                 # 起点から未取得分をたどる
  python scripts/fetch_5ch_archive.py --refresh KEY   # 指定スレ（現行スレなど）を取り直す
  python scripts/fetch_5ch_archive.py --add URL ...   # たどれなかったスレを手で足す

取得元は 5ch.io、無ければ 2ch.sc。kyodemo.net は robots.txt で禁止されているので使わない。
"""
import argparse, json, os, re, sys, time, unicodedata, urllib.request, urllib.error, datetime

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "5ch-archive")
RAW = os.path.join(OUT, "raw")
MANIFEST = os.path.join(OUT, "manifest.json")
START = ("mevius", "musicjg", "1710491275")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
DELAY = 4.0

THREAD_URL = re.compile(
    r"https?://([a-z0-9]+)\.(?:2ch\.net|5ch\.net|5ch\.io|2ch\.sc|bbspink\.com)"
    r"/test/read\.cgi/([a-z0-9]+)/(\d{9,10})")
BAND = re.compile(r"baseballbear|ベボベ|ベースボールベア|小出祐介|関根史織|関根詩織|堀之内大介|湯浅将平")


def squash(title):
    """全角・空白・記号の揺れをならす。"""
    t = unicodedata.normalize("NFKC", title).lower()
    return re.sub(r"[\s　】【\[\]]+", "", t)


def is_band(title):
    """題名にバンド名やメンバー名があるかを見る。"""
    return bool(BAND.search(squash(title)))


def http_get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "ja,en;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=40) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # タイムアウト、名前解決の失敗など
        return 0, str(e).encode("utf-8")


def decode(raw):
    return raw.decode("cp932", errors="replace")


def post_count(html):
    return max(len(re.findall(r'class="clear post"', html)), len(re.findall(r"<dt>", html)))


def title_of(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def candidates(sub, board, key):
    """現行サーバー → 5ch公式の過去ログ → 2ch.sc の順に探す。"""
    urls = []
    if sub != "kako" and int(key) >= 1483228800:  # 2017年以降は現行サーバーに残っていることがある
        urls.append(f"https://{sub}.5ch.io/test/read.cgi/{board}/{key}/")
    urls.append(f"https://kako.5ch.io/test/read.cgi/{board}/{key}/")
    urls.append(f"http://toro.2ch.sc/test/read.cgi/{board}/{key}/")
    return urls


def fetch_thread(sub, board, key):
    """(raw, source_url) を返す。どこにも無ければ (None, 試した結果)。"""
    tried = []
    for url in candidates(sub, board, key):
        status, raw = http_get(url)
        time.sleep(DELAY)
        n = post_count(decode(raw)) if status == 200 else 0
        tried.append(f"{url} -> {status}/{n}件")
        if status == 200 and n > 0:
            return raw, url
    return None, tried


def head_links(html, own_key):
    """先頭15レスのうち、スレを立てた人（>>1 と同じID）の書き込みに貼られた
    スレッドURL（前スレ・過去スレ一覧）を拾う。他人が貼った無関係なスレは追わない。"""
    marks = [m.start() for m in re.finditer(r'<div id="\d+" data-date=', html)]
    old = not marks
    if old:
        marks = [m.start() for m in re.finditer(r"<dt>\d+ ：", html)]
    chunks = [html[a:b] for a, b in zip(marks[:15], (marks + [len(html)])[1:16])]
    if not chunks:
        return []

    def uid(chunk):
        m = re.search(r"<dt>.*?<dd>", chunk, re.S) if old else re.search(r'data-userid="([^"]*)"', chunk)
        if not m:
            return None
        if old:
            m2 = re.search(r"ID:(\S+)", m.group(0))
            return m2.group(1) if m2 else None
        return m.group(1)

    owner = uid(chunks[0])
    found = {}
    for i, chunk in enumerate(chunks):
        if i > 0 and (not owner or "???" in owner or uid(chunk) != owner):
            continue
        for sub, board, key in THREAD_URL.findall(chunk):
            if key != own_key:
                found[key] = (sub, board, key)
    return list(found.values())


def load_manifest():
    if os.path.exists(MANIFEST):
        return json.load(open(MANIFEST, encoding="utf-8"))
    return {}


def save_manifest(man):
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, ensure_ascii=False, indent=1, sort_keys=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", nargs="*", default=[], help="取り直すスレッドキー")
    ap.add_argument("--add", nargs="*", default=[], help="追加でたどるスレッドURL")
    ap.add_argument("--add-file", help="追加するスレッドの一覧（[sub, board, key, 題名] のJSON）")
    ap.add_argument("--no-follow", action="store_true", help="追加したスレからは先をたどらない")
    ap.add_argument("--refresh-latest", action="store_true",
                    help="いちばん新しい本スレを取り直し、次スレが立っていればそれも取る")
    ap.add_argument("--retry-failed", action="store_true", help="前回見つからなかったスレを再試行")
    args = ap.parse_args()

    os.makedirs(RAW, exist_ok=True)
    man = load_manifest()
    queue = [START]
    if args.refresh_latest:
        main_keys = [k for k, v in man.items() if v.get("status") == "ok" and v.get("board") == "musicjg"
                     and v.get("band") and "baseballbear" in squash(v.get("title", ""))]
        if main_keys:
            latest = max(main_keys, key=int)
            args.refresh = list(args.refresh) + [latest]
            queue.insert(0, (man[latest]["sub"], "musicjg", latest))
    for u in args.add:
        m = THREAD_URL.search(u)
        if m:
            queue.append(m.groups())
        else:
            print("URLを読めません:", u)
    added = set()
    if args.add_file:
        for sub, board, key, *_ in json.load(open(args.add_file, encoding="utf-8")):
            queue.append((sub, board, key))
            added.add(key)
    seen = set()
    fetched = 0

    while queue:
        sub, board, key = queue.pop(0)
        if key in seen:
            continue
        seen.add(key)
        path = os.path.join(RAW, f"{board}_{key}.html")
        entry = man.get(key)

        if entry and entry.get("status") == "missing" and not args.retry_failed:
            continue
        is_new = False
        if os.path.exists(path) and key not in args.refresh:
            html = decode(open(path, "rb").read())
        else:
            is_new = True
            raw, src = fetch_thread(sub, board, key)
            if raw is None:
                man[key] = {"status": "missing", "sub": sub, "board": board, "tried": src}
                save_manifest(man)
                print(f"[なし] {sub}/{board}/{key}")
                for t in src:
                    print("       ", t)
                continue
            with open(path, "wb") as f:
                f.write(raw)
            html = decode(raw)
            fetched += 1
            entry = {"status": "ok", "sub": sub, "board": board, "source": src,
                     "fetched_at": datetime.datetime.now().isoformat(timespec="seconds")}

        title = title_of(html)
        entry = dict(entry or {"status": "ok", "sub": sub, "board": board})
        entry.update({"title": title, "posts": post_count(html), "band": is_band(title)})
        man[key] = entry
        save_manifest(man)
        print(f"[{'取得' if is_new else '既存'}] {key} {entry['posts']:>4}件 {title[:60]}")

        # 関連スレ（バンド名がタイトルに無いスレ）からは先をたどらない
        if entry["band"] and not (args.no_follow and key in added):
            for link in head_links(html, key):
                if link[2] not in seen:
                    queue.append(link)
            # 取り直した現行スレに次スレのURLが貼られていれば、それも取りに行く
            if is_new and args.refresh_latest and board == "musicjg":
                for sub2, board2, key2 in THREAD_URL.findall(html):
                    if board2 == "musicjg" and int(key2) > int(key) and key2 not in seen:
                        queue.append((sub2, board2, key2))

    ok = [k for k, v in man.items() if v.get("status") == "ok"]
    ng = [k for k, v in man.items() if v.get("status") == "missing"]
    print(f"\n今回取得 {fetched} 件 / 保存済み {len(ok)} 件 / 見つからず {len(ng)} 件")


if __name__ == "__main__":
    main()
