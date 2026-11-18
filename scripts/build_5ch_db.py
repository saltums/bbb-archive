#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data/5ch-archive/raw の生HTMLを読み、検索用の SQLite（data/5ch-archive/bbb5ch.sqlite）を作り直す。

  python scripts/build_5ch_db.py
"""
import html as htmllib
import datetime, json, os, re, sqlite3, sys, unicodedata

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "5ch-archive")
RAW = os.path.join(OUT, "raw")
DB = os.path.join(OUT, "bbb5ch.sqlite")

DATE = re.compile(r"(\d{2,4})/(\d{1,2})/(\d{1,2})(?:\([^)]*\))?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?")
NEW_POST = re.compile(r'<div id="(\d+)" data-date="[^"]*" data-userid="[^"]*" data-id="\d+" class="clear post">')
OLD_POST = re.compile(r"<dt>(\d+) ：(.*?)：([^<]*?(?:<[^d][^>]*>[^<]*)*?)<dd>(.*?)(?=<dt>\d+ ：|</dl>)", re.S)


BAND = re.compile(r"baseballbear|ベボベ|ベースボールベア|小出祐介|関根史織|関根詩織|堀之内大介|湯浅将平")
MUSIC_BOARDS = {"musicjg", "minor", "musicj", "mjsaloon", "compose", "uwasa", "karaok"}
# 重複して立ったスレを後から再利用したため、題名の番号と実際の順番が違うもの
VOL_OVERRIDE = {"1070612450": 1, "1326571329": 44, "1361607525": 49, "1481244698": 66, "1492066988": 72}


def squash(title):
    t = unicodedata.normalize("NFKC", title).lower()
    return re.sub(r"[\s　】【\[\]]+", "", t)


def kind_of(board, title, vol):
    """main=本スレ / related=音楽系の板の関連スレ / other=それ以外の板の単発スレ"""
    if board in ("musicjg", "minor") and vol is not None and "baseballbear" in squash(title):
        return "main"
    return "related" if board in MUSIC_BOARDS else "other"


def cf_decode(hexstr):
    """Cloudflare のメール保護（メール欄の sage など）を元に戻す。"""
    try:
        b = bytes.fromhex(hexstr)
        return bytes(c ^ b[0] for c in b[1:]).decode("utf-8", errors="replace")
    except ValueError:
        return ""


def text_of(fragment):
    s = re.sub(r"<br\s*/?>", "\n", fragment)
    s = re.sub(r"<[^>]+>", "", s)
    s = htmllib.unescape(s)
    lines = [ln.strip(" \t\r") for ln in s.split("\n")]
    return "\n".join(lines).strip("\n")


def iso_date(raw):
    m = DATE.search(raw)
    if not m:
        # 2013年夏の「NY:AN:NY.AN」のように時刻だけ伏せられた投稿は、日付だけ生かす
        d = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", raw)
        return f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d} 00:00:00" if d else None
    y, mo, d, h, mi, sec = m.groups()
    y = int(y)
    if y < 100:
        y += 2000 if y < 70 else 1900
    if y > 2600:  # 2005年4月1日のエイプリルフール表示（皇紀2665年）
        y -= 660
    return f"{y:04d}-{int(mo):02d}-{int(d):02d} {int(h):02d}:{mi}:{sec or '00'}"


def uid_of(raw):
    m = re.search(r"ID:(\S+)", raw)
    if not m:
        return None
    return re.sub(r"\.(net|sc)$", "", m.group(1))


def parse_new(html):
    posts = []
    marks = list(NEW_POST.finditer(html))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(html)
        chunk = html[m.end():end]
        name_m = re.search(r'<span class="postusername">(.*?)</span>', chunk, re.S)
        date_m = re.search(r'<span class="date">(.*?)</span>', chunk, re.S)
        uid_m = re.search(r'<span class="uid">(.*?)</span>', chunk, re.S)
        body_m = re.search(r'<(?:div|section) class="post-content">(.*)', chunk, re.S)
        name_html = name_m.group(1) if name_m else ""
        mail = ""
        mm = re.search(r'email-protection#([0-9a-f]+)', name_html)
        if mm:
            mail = cf_decode(mm.group(1))
        else:
            mm = re.search(r'href="mailto:([^"]*)"', name_html)
            if mm:
                mail = htmllib.unescape(mm.group(1))
        body = body_m.group(1) if body_m else ""
        end_m = re.search(r"</(?:div|section)></div>", body)
        if end_m:
            body = body[:end_m.start()]
        date_raw = text_of(date_m.group(1)) if date_m else ""
        uid_raw = text_of(uid_m.group(1)) if uid_m else ""
        posts.append({"no": int(m.group(1)), "name": text_of(name_html), "mail": mail,
                      "date_raw": (date_raw + " " + uid_raw).strip(), "posted_at": iso_date(date_raw),
                      "uid": uid_of(uid_raw), "body": text_of(body)})
    return posts


def parse_old(html):
    posts = []
    for m in OLD_POST.finditer(html):
        name_html, info, body = m.group(2), m.group(3), m.group(4)
        mm = re.search(r'href="mailto:([^"]*)"', name_html)
        info_text = text_of(info)
        posts.append({"no": int(m.group(1)), "name": text_of(name_html),
                      "mail": htmllib.unescape(mm.group(1)) if mm else "",
                      "date_raw": info_text, "posted_at": iso_date(info_text),
                      "uid": uid_of(info_text), "body": text_of(body)})
    return posts


def volume_of(title):
    t = title.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    t = re.sub(r"\[無断転載禁止\]|&#169;\S+|©\S+", "", t)
    for pat in (r"vol\.?\s*(\d+)", r"part\.?\s*(\d+)", r"その\s*(\d+)", r"(\d+)\s*(?:曲目|枚目|本目|球目|匹目|頭目|回目|スレ目)", r"(\d+)\D*$"):
        m = re.search(pat, t, re.I)
        if m and int(m.group(1)) < 500:
            return int(m.group(1))
    return None


def main():
    man = json.load(open(os.path.join(OUT, "manifest.json"), encoding="utf-8"))
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE threads(
      key TEXT PRIMARY KEY, board TEXT, sub TEXT, title TEXT, vol INTEGER,
      source TEXT, post_count INTEGER, first_at TEXT, last_at TEXT, kind TEXT);
    CREATE TABLE posts(
      id INTEGER PRIMARY KEY, thread_key TEXT, no INTEGER, name TEXT, mail TEXT,
      date_raw TEXT, posted_at TEXT, uid TEXT, body TEXT);
    CREATE INDEX posts_thread ON posts(thread_key, no);
    CREATE INDEX posts_at ON posts(posted_at);
    CREATE INDEX posts_uid ON posts(uid);
    CREATE VIRTUAL TABLE posts_fts USING fts5(body, content='posts', content_rowid='id', tokenize='trigram');
    """)
    total = 0
    problems = []
    skipped = []
    for key in sorted(man):
        e = man[key]
        if e.get("status") != "ok":
            continue
        raw = open(os.path.join(RAW, f"{e['board']}_{key}.html"), "rb").read()
        html = raw.decode("cp932", errors="replace")
        posts = parse_new(html) if NEW_POST.search(html) else parse_old(html)
        title = re.sub(r"\s*\[(?:無断)?転載禁止\]|\s*(?:&#169;|©)\S+", "", htmllib.unescape(e.get("title", ""))).strip()
        if not BAND.search(squash(title)):
            skipped.append(f"{key}: {title}")
            continue
        vol = VOL_OVERRIDE.get(key, volume_of(title) if e["board"] in MUSIC_BOARDS else None)
        # 末尾の「このスレッドは1000を超えました」は日付を持たないので、直前の投稿の時刻を借りる
        for prev, p in zip(posts, posts[1:]):
            if not p["posted_at"] and "Over 1000" in p["date_raw"]:
                p["posted_at"] = prev["posted_at"]
        dates = [p["posted_at"] for p in posts if p["posted_at"]]
        # スレッドキーは立った時刻（UNIX秒）。>>1 の日付が失われている古いスレの開始日に使う
        born = (datetime.datetime.fromtimestamp(int(key), datetime.timezone.utc)
                + datetime.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")
        if posts and not posts[0]["posted_at"]:
            dates.append(born)
        if len(posts) != e.get("posts"):
            problems.append(f"{key}: HTML上 {e.get('posts')} 件に対し解析 {len(posts)} 件")
        nodate = sum(1 for p in posts if not p["posted_at"])
        if nodate > max(3, len(posts) // 50):
            problems.append(f"{key}: 日付を読めない投稿が {nodate} 件")
        con.execute("INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (key, e["board"], e["sub"], title, vol, e.get("source"), len(posts),
                     min(dates) if dates else None, max(dates) if dates else None, kind_of(e["board"], title, vol)))
        con.executemany(
            "INSERT INTO posts(thread_key,no,name,mail,date_raw,posted_at,uid,body) VALUES(?,?,?,?,?,?,?,?)",
            [(key, p["no"], p["name"], p["mail"], p["date_raw"], p["posted_at"], p["uid"], p["body"]) for p in posts])
        total += len(posts)
    con.execute("INSERT INTO posts_fts(rowid, body) SELECT id, body FROM posts")
    con.commit()
    con.execute("VACUUM")
    n_threads = con.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
    span = con.execute("SELECT MIN(posted_at), MAX(posted_at) FROM posts").fetchone()
    con.close()
    print(f"スレッド {n_threads} 本 / 投稿 {total} 件 / 期間 {span[0]} 〜 {span[1]}")
    print(f"DB: {DB} ({os.path.getsize(DB) / 1024 / 1024:.1f} MB)")
    if problems:
        print("\n要確認:")
        for p in problems:
            print(" ", p)


if __name__ == "__main__":
    main()
