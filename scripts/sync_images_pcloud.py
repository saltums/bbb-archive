#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手元に取った公式アーカイブの画像を pCloud に送る。
置き場所は /BaseBallBear-Archive/images/<置き場所>/<年>/<日付>_<元のファイル名>（日付は画像が最初に出た記事の日）。
ボタンなどの飾り（kind=ui）と、同じ中身の画像の2枚目以降は送らない。
送った結果は data/blog-archive/images_pcloud.json に残し、build_blog_db.py が DB に入れる。
pCloud の接続情報は pcloud-sorter/config.json から実行時に読む（コードには書かない）。

  python scripts/sync_images_pcloud.py           # まだ送っていない画像を送る
  python scripts/sync_images_pcloud.py --list    # 送る枚数だけ見る
"""
import argparse, csv, io, json, os, re, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request, uuid

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bbb_images import IMG_DIR, IMG_MANIFEST, OUT, PCLOUD_ROOT

SYNCED = os.path.join(OUT, "images_pcloud.json")
SORTER_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                             "pcloud-sorter", "config.json")


def pcloud_cfg():
    pc = json.load(open(SORTER_CONFIG, encoding="utf-8")).get("pcloud", {})
    if not pc.get("token"):
        sys.exit("pCloud の接続情報が pcloud-sorter/config.json にありません")
    return pc.get("api_host", "api.pcloud.com"), pc["token"]


HOST, TOKEN = None, None


def api(endpoint, params, data=None, ctype=None):
    url = f"https://{HOST}/{endpoint}?" + urllib.parse.urlencode(dict(params, auth=TOKEN))
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": ctype} if ctype else {})
    for wait in (5, 20, 60, 0):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read().decode())
            if d.get("result", 0) != 0:
                raise RuntimeError(f'{endpoint}: {d.get("error", d)}')
            return d
        except (urllib.error.URLError, TimeoutError) as e:
            if not wait:
                raise
            time.sleep(wait)


def upload(folder, name, data):
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{b}--\r\n".encode()
    d = api("uploadfile", {"path": folder, "filename": name, "nopartial": 1, "renameifexists": 0},
            body, f"multipart/form-data; boundary={b}")
    return d["metadata"][0]["fileid"]


def folder(path, made=set()):
    """フォルダを上から順に作る（pCloud は親が無いと作れない）。"""
    parts = path.strip("/").split("/")
    for i in range(1, len(parts) + 1):
        p = "/" + "/".join(parts[:i])
        if p not in made:
            api("createfolderifnotexists", {"path": p})
            made.add(p)


def main():
    global HOST, TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    man = json.load(open(IMG_MANIFEST, encoding="utf-8")) if os.path.exists(IMG_MANIFEST) else {}
    synced = json.load(open(SYNCED, encoding="utf-8")) if os.path.exists(SYNCED) else {}
    con = sqlite3.connect(os.path.join(OUT, "blogs.sqlite"))
    info = {u: (src, d) for u, src, d in con.execute("SELECT url, source, first_date FROM images")}
    todo = [u for u, m in man.items() if m.get("file") and m.get("kind") != "ui" and not m.get("same_as")
            and u not in synced and u in info]
    print(f"送る画像 {len(todo)} 枚（送り済み {len(synced)}）", flush=True)
    if args.list or not todo:
        return
    HOST, TOKEN = pcloud_cfg()
    used = {v["path"] for v in synced.values()}
    for i, u in enumerate(todo, 1):
        src, date = info[u]
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(u.split("?")[0]))[-80:] or "image"
        name = f"{date}_{base}"
        dest = f"{PCLOUD_ROOT}/{src}/{date[:4]}"
        if f"{dest}/{name}" in used:
            stem, ext = os.path.splitext(name)
            name = f"{stem}_{len(used)}{ext}"
        folder(dest)
        data = open(os.path.join(IMG_DIR, man[u]["file"]), "rb").read()
        fid = upload(dest, name, data)
        synced[u] = {"path": f"{dest}/{name}", "fileid": fid}
        used.add(f"{dest}/{name}")
        if i % 25 == 0 or i == len(todo):
            json.dump(synced, open(SYNCED, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=0)
            print(f"[{i}/{len(todo)}] {dest}/{name}", flush=True)
    json.dump(synced, open(SYNCED, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=0)
    # pCloud 側にも目録を置く（どの画像がどの記事に出たか）。Excel で開けるよう BOM 付き
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["pCloudの場所", "日付", "置き場所", "記事の題", "連載", "元の画像のURL", "記事のページ"])
    for u, v in sorted(synced.items(), key=lambda kv: kv[1]["path"]):
        r = con.execute("""SELECT e.date, e.source, e.title, e.series, e.page_url FROM images i
                           JOIN entry_images x ON x.image_id = i.id JOIN entries e ON e.id = x.entry_id
                           WHERE i.url = ? ORDER BY e.date LIMIT 1""", (u,)).fetchone()
        if r:
            w.writerow([v["path"], r[0], r[1], r[2], r[3], u, r[4]])
    upload(PCLOUD_ROOT, "index.csv", ("﻿" + out.getvalue()).encode("utf-8"))
    print(f"完了: pCloud に {len(synced)} 枚（目録 {PCLOUD_ROOT}/index.csv）", flush=True)


if __name__ == "__main__":
    main()
