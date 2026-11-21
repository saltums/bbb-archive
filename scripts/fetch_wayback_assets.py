#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""元のページを当時の見た目に近づけるため、保存ページが読み込んでいた CSS と、CSS の中の画像（背景など）、
ページの背景画像（body background= など）を Internet Archive から取る。
保存先は data/blog-archive/assets/（gitignore）、目録は assets.json（元のURL → 保存したファイル）。

  python scripts/fetch_wayback_assets.py
"""
import datetime, json, os, re, sys, time, urllib.parse

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bbb_images import OUT, SKIP  # noqa: E402
from build_blog_db import decode  # noqa: E402
from fetch_wayback_images import archived, http, key  # noqa: E402

RAW = os.path.join(OUT, "raw")
ASSETS = os.path.join(OUT, "assets")
MANIFEST = os.path.join(OUT, "assets.json")
DELAY = 2.5


def absolute(base, ref):
    ref = html_unescape(ref.strip().strip("'\""))
    if not ref or ref.startswith(("data:", "javascript:", "#", "about:")):
        return None
    ref = re.sub(r"^(https?:)?//web\.archive\.org/web/\d+[a-z_]*/", "", ref)
    ref = re.sub(r"^/web/\d+[a-z_]*/", "", ref)
    u = urllib.parse.urljoin(base if re.match(r"https?://", base) else "http://" + base, ref)
    u = re.sub(r"^https?://", "http://", u)
    u = re.sub(r":80(?=/)", "", u).split("#")[0]
    return None if SKIP.search(u) or not re.match(r"http://[^/]+\.[^/]+/", u) else u


def html_unescape(s):
    import html
    return html.unescape(s)


def local(u):
    path = re.sub(r"^http://", "", u)
    stem, ext = os.path.splitext(path.split("?")[0])
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)[-160:] + re.sub(r"[^a-z0-9.]", "", ext.lower())[:6]
    if "?" in path:
        import hashlib
        name = hashlib.sha1(path.encode()).hexdigest()[:8] + "_" + name
    return name


def save(man):
    tmp = MANIFEST + ".tmp"
    json.dump(man, open(tmp, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=0)
    os.replace(tmp, MANIFEST)


def fetch_all(man, want, label):
    """want: {url: ts}。保存があるものだけ取る。"""
    todo = {u: ts for u, ts in want.items() if u not in man or man[u].get("status") in (0, 429, 500, 502, 503, 504)}
    print(f"{label}: {len(want)} 件 / 残り {len(todo)}", flush=True)
    if not todo:
        return
    found = archived(list(todo))
    got = 0
    for i, (u, ts) in enumerate(sorted(todo.items()), 1):
        if key(u) not in found:
            man[u] = {"status": 404, "file": None}
            continue
        status, data, ctype = http(f"https://web.archive.org/web/{found[key(u)] or ts}id_/{u}")
        rec = {"status": status, "file": None, "ts": found[key(u)] or ts}
        if status == 200 and data and not (ctype.startswith("text/html") and not u.endswith(".css")):
            name = local(u)
            os.makedirs(ASSETS, exist_ok=True)
            open(os.path.join(ASSETS, name), "wb").write(data)
            rec.update(file=name, type=ctype)
            got += 1
        man[u] = rec
        if i % 25 == 0:
            save(man)
            print(f"  [{i}/{len(todo)}] {datetime.datetime.now():%H:%M} 保存 {got} {u[:70]}", flush=True)
        time.sleep(DELAY)
    save(man)
    print(f"  {label} 完了: 今回 {got}", flush=True)


def main():
    man = json.load(open(MANIFEST, encoding="utf-8")) if os.path.exists(MANIFEST) else {}
    pages = json.load(open(os.path.join(OUT, "manifest.json"), encoding="utf-8"))["pages"]
    css, bgs = {}, {}
    for p in pages.values():
        if not p.get("file") or "epad" in p["file"] or not os.path.exists(os.path.join(RAW, p["file"])):
            continue
        doc = decode(open(os.path.join(RAW, p["file"]), "rb").read())
        for tag in re.findall(r"<link\b[^>]*>", doc, re.I):
            if re.search(r"stylesheet", tag, re.I):
                m = re.search(r'href\s*=\s*["\']?([^"\'\s>]+)', tag, re.I)
                u = m and absolute(p["url"], m.group(1))
                if u:
                    css.setdefault(u, p["ts"])
        for ref in re.findall(r'@import\s+(?:url\()?["\']?([^"\')\s;]+)', doc, re.I):
            u = absolute(p["url"], ref)
            if u:
                css.setdefault(u, p["ts"])
        for ref in re.findall(r'\sbackground\s*=\s*["\']?([^"\'\s>]+)', doc, re.I) + re.findall(r"url\(([^)]+)\)", doc, re.I):
            u = absolute(p["url"], ref)
            if u:
                bgs.setdefault(u, p["ts"])
    fetch_all(man, css, "CSS")
    # CSS の中の @import と url(...)
    for _ in range(2):
        more_css = {}
        for u, rec in list(man.items()):
            if rec.get("file") and (u.split("?")[0].endswith(".css") or "css" in (rec.get("type") or "")):
                text = open(os.path.join(ASSETS, rec["file"]), "rb").read().decode("utf-8", "ignore")
                for ref in re.findall(r'@import\s+(?:url\()?["\']?([^"\')\s;]+)', text, re.I):
                    v = absolute(u, ref)
                    if v and v not in man:
                        more_css.setdefault(v, rec["ts"])
                for ref in re.findall(r"url\(([^)]+)\)", text, re.I):
                    v = absolute(u, ref)
                    if v and not v.split("?")[0].endswith(".css"):
                        bgs.setdefault(v, rec["ts"])
        if not more_css:
            break
        fetch_all(man, more_css, "CSS（読み込みの先）")
    fetch_all(man, bgs, "背景などの画像")
    ok = sum(1 for r in man.values() if r.get("file"))
    print(f"完了: 保存 {ok} / 取れず {len(man) - ok}", flush=True)


if __name__ == "__main__":
    main()
