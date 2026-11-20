#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data/blog-archive/raw の保存ページから日記・ブログの記事を取り出し、
data/blog-archive/blogs.sqlite を作り直す。

  python scripts/build_blog_db.py
"""
import collections, hashlib, html as htmllib, json, os, re, sqlite3, sys, unicodedata

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "blog-archive")
RAW = os.path.join(OUT, "raw")
DB = os.path.join(OUT, "blogs.sqlite")

MEMBERS = ["小出祐介", "関根史織", "湯浅将平", "堀之内大介"]
DATE_JP = re.compile(r"(20\d\d|19\d\d)\s*[年/.\-]\s*(\d{1,2})\s*[月/.\-]\s*(\d{1,2})")


def decode(raw):
    head = raw[:4000].decode("ascii", "ignore").lower()
    m = re.search(r'charset=["\']?([\w-]+)', head)
    cs = (m.group(1) if m else "").replace("x-sjis", "cp932").replace("shift_jis", "cp932").replace("euc-jp", "euc_jp")
    for enc in ([cs] if cs else []) + ["utf-8", "cp932", "euc_jp"]:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("cp932", errors="replace")


def text_of(fragment):
    s = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", fragment, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</div>|<p[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<img[^>]*>", "［画像］", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = htmllib.unescape(s).replace("　", "　")
    lines = [ln.rstrip() for ln in s.split("\n")]
    out, blank = [], 0
    for ln in lines:
        blank = blank + 1 if not ln.strip() else 0
        if blank <= 1:
            out.append(ln.strip())
    return "\n".join(out).strip()


def tidy_lines(body):
    """HTML の書き方のせいで1行ごとに空行が挟まっている本文は、空行を1つ詰める。"""
    body = body.strip()
    singles = len(re.findall(r"(?<!\n)\n(?!\n)", body))
    doubles = len(re.findall(r"(?<!\n)\n\n(?!\n)", body))
    if doubles > 3 and doubles > singles * 2:
        body = re.sub(r"\n\n(?!\n)", "\n", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def iso(y, mo, d):
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def author_from(text, default=""):
    for full in MEMBERS:
        if full in text or full[:2] in text:
            return full
    return default


# ---- 記事ごとの取り出し方 ----

def parse_mt(page):
    """Movable Type / seesaa / livedoor 型（記事ごとに RDF のメタ情報が付いている）。"""
    entries = []
    blocks = re.split(r"<rdf:RDF", page)[1:]
    for b in blocks:
        meta = {k: htmllib.unescape(v) for k, v in re.findall(r'(dc:title|dc:date|dc:subject|dc:creator|rdf:about)="([^"]*)"', b)}
        if "dc:date" not in meta:
            continue
        body_m = re.search(r'<div class="(?:text|main|entry-content|entry-body|entry-body-text)"[^>]*>(.*?)(?=<div class="(?:posted|entry-footer|menu)|<p class="entry-footer|<a name="more"></a>\s*<div class="posted)', b, re.S)
        if not body_m:
            continue
        body = text_of(body_m.group(1))
        if not body:
            continue
        entries.append({"date": meta["dc:date"][:10], "time": meta["dc:date"][11:16], "title": meta.get("dc:title", ""),
                        "body": body, "url": meta.get("rdf:about", ""),
                        "author": author_from(meta.get("dc:subject", "")) or author_from(meta.get("dc:creator", ""))})
    return entries


def parse_cgi_diary(page):
    """公式サイトの日記 CGI（■2006年02月03日 (Fri) 題名 → 本文）。"""
    entries = []
    parts = re.split(r"■\s*(?=(?:19|20)\d\d年)", page)[1:]
    for p in parts:
        m = DATE_JP.match(p)
        if not m:
            continue
        t = re.search(r"<b>(.*?)</b>", p[:600], re.S)
        body_m = re.search(r'<font color="#424242">(.*?)</font>\s*(?:</div>|</td>)', p, re.S)
        if not body_m:
            continue
        imgs = "［画像］\n" if re.search(r"<img[^>]+/up/", p[:body_m.start()]) else ""
        entries.append({"date": iso(*m.groups()), "time": "", "title": text_of(t.group(1)) if t else "",
                        "body": imgs + text_of(body_m.group(1)), "url": "", "author": ""})
    return entries


def parse_dated_text(page, ts=""):
    """日付の見出しで区切られた手書きの日記ページ（旧ホームページなど）。
    「2003年6月21日」「6月21日(土)」「9月。→4日、」のどれでも日ごとに切る。年が書かれていなければ保存時期から補う。"""
    body = re.search(r"<body[^>]*>(.*)</body>", page, re.S | re.I)
    raw_html = body.group(1) if body else page
    head = re.search(r"<b>(.*?)</b>", raw_html, re.S | re.I)
    series = unicodedata.normalize("NFKC", text_of(head.group(1))).strip() if head else ""
    txt = unicodedata.normalize("NFKC", text_of(raw_html))

    # 見出しになる日付の行だけを拾う（本文中の「12月8日のライブに…」は拾わない）
    entries, cur, month = [], None, 0
    for ln in txt.split("\n"):
        s_ = ln.strip()
        full = re.match(r"^(20\d\d|19\d\d)\s*[年/.\-]\s*(\d{1,2})\s*[月/.\-]\s*(\d{1,2})日?\s*(?:[(（][^)）]{1,4}[)）])?\s*$", s_)
        md = re.match(r"^(\d{1,2})月(\d{1,2})日\s*(?:[(（]([月火水木金土日祝・]+)[)）])?\s*$", s_) or \
            re.match(r"^(\d{1,2})月(\d{1,2})日\s*[(（]([月火水木金土日祝・]+)[)）]\s*(.{0,30})$", s_)
        mon = re.match(r"^(\d{1,2})月[。.、]?$", s_)
        day = re.match(r"^(\d{1,2})日[、,。]\s*(.*)$", s_) if month else None
        ymd = rest = None
        if full:
            ymd = (int(full.group(1)), int(full.group(2)), int(full.group(3)))
        elif md:
            ymd, rest = (0, int(md.group(1)), int(md.group(2))), (md.group(4) if md.lastindex and md.lastindex >= 4 else "")
        elif mon:
            month = int(mon.group(1))
            continue
        elif day:
            ymd, rest = (0, month, int(day.group(1))), day.group(2)
        if ymd:
            if cur and cur["body"].strip():
                entries.append(cur)
            rest = rest or ""
            cur = {"ymd": ymd, "time": "", "title": rest.strip(" ()（）:：-") if len(rest) < 30 else "",
                   "body": "" if len(rest) < 30 else rest + "\n", "url": "", "author": "", "series": series}
        elif cur is not None:
            cur["body"] += s_ + "\n"
    if cur and cur["body"].strip():
        entries.append(cur)
    # 年の書かれていない日付は、ページ内で月が戻ったら年を進める形で並べ、仮に保存時期に収まるいちばん新しい年を当てる。
    # 連載の前後の回とのつながりは、全ページを読んだあとで main() が直す。
    for e in entries:
        e["capture"] = ts
    assign_years(entries, ts)
    if not entries and len(txt.strip()) > 40:
        # 日付の見出しが見つからないページは、1ページを1件として残す（日付は保存時期）
        d = DATE_JP.search(txt)
        date = iso(*d.groups()) if d else (f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if ts else "")
        entries.append({"date": date, "time": "", "title": series, "body": txt.strip(), "url": "", "author": "",
                        "series": series, "approx": not d})
    for e in entries:
        e["body"] = tidy_lines(e["body"])
    return entries


def assign_years(entries, ts, start_year=None):
    """年の無い (0, 月, 日) に年を当てる。start_year が無ければ、最後の日付が保存時期を越えない最大の年。"""
    undated = [e for e in entries if "ymd" in e]
    if not undated:
        return
    cap = ts[:8] if ts else "99999999"

    def build(base):
        y, prev_m, out = base, None, []
        for e in undated:
            yy, m, d = e["ymd"]
            if yy:
                y = yy
            elif prev_m and m < prev_m:
                y += 1
            out.append((y if not yy else yy, m, d))
            prev_m = m
        return out

    if start_year is None:
        base = int(cap[:4]) if ts else 2000
        while base > 1990 and f"{build(base)[-1][0]:04d}{build(base)[-1][1]:02d}{build(base)[-1][2]:02d}" > cap:
            base -= 1
    else:
        base = start_year
    for e, (y, m, d) in zip(undated, build(base)):
        e["date"] = iso(y, m, d)
        e["base"] = base


def fix_series_years(rows):
    """連載（「曖昧Diary 第N回」など）は回の順に日付が続くはずなので、
    各回の最初の日が前の回の最後の日より前にならない、いちばん早い年に揃える。"""
    def family(series):
        m = re.match(r"^(.*?)(?:第\s*(\d+)\s*回|Part\s*(\d+)|vol\.?\s*(\d+)|(\d+))", series or "", re.I)
        if not m:
            return None, None
        num = next((g for g in m.groups()[1:] if g), None)
        return m.group(1).strip(), int(num) if num else None

    groups = collections.defaultdict(list)
    for page in rows:
        fam, num = family(page["series"])
        if fam is not None and num is not None and any("ymd" in e for e in page["entries"]):
            groups[fam].append((num, page))
    for fam, pages in groups.items():
        pages.sort(key=lambda x: x[0])
        prev_last = None
        for _, page in pages:
            es = [e for e in page["entries"] if "ymd" in e]
            if prev_last:
                y = int(prev_last[:4])
                assign_years(page["entries"], page["ts"], y)
                if es[0]["date"] < prev_last:
                    assign_years(page["entries"], page["ts"], y + 1)
            prev_last = max(e["date"] for e in es)


PARSERS = {
    "bokuburo": parse_mt, "livedoor": parse_mt, "jfn": parse_mt,
}


def parse(source, url, page, ts=""):
    if source in PARSERS:
        return PARSERS[source](page), "blog"
    if source.startswith("official") and re.search(r"cgi-bin/(diary|hamripo)", url):
        return parse_cgi_diary(page), "blog"
    if source.startswith("official") and "epad" in url:
        return [], "bbs"
    if source.startswith("playlog"):
        return parse_playlog(page, ts), "blog"
    if source == "seiryu":
        return parse_dated_text(page, ts), "blog"
    return parse_dated_text(page, ts), "page"


def parse_playlog(page, ts=""):
    """playlog の記事ページ（形式は取得後に確かめて、合わなければ日付区切りで拾う）。"""
    m = re.search(r'<div class="entry[^"]*"[^>]*>(.*?)<div class="entry-footer', page, re.S)
    if m:
        d = DATE_JP.search(m.group(1)) or DATE_JP.search(page)
        t = re.search(r"<h\d[^>]*>(.*?)</h\d>", m.group(1), re.S)
        if d:
            return [{"date": iso(*d.groups()), "time": "", "title": text_of(t.group(1)) if t else "",
                     "body": text_of(m.group(1)[t.end():] if t else m.group(1)), "url": "", "author": ""}]
    return parse_dated_text(page, ts)


def main():
    man = json.load(open(os.path.join(OUT, "manifest.json"), encoding="utf-8"))
    sources = man.get("sources", {})
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE sources(id TEXT PRIMARY KEY, label TEXT, author TEXT, prefix TEXT, pages INTEGER, entries INTEGER);
    CREATE TABLE entries(id INTEGER PRIMARY KEY, source TEXT, author TEXT, date TEXT, time TEXT, title TEXT,
      body TEXT, url TEXT, page_url TEXT, wayback_ts TEXT, kind TEXT, series TEXT, approx INTEGER);
    CREATE INDEX entries_date ON entries(date);
    CREATE INDEX entries_source ON entries(source, date);
    CREATE VIRTUAL TABLE entries_fts USING fts5(title, body, content='entries', content_rowid='id', tokenize='trigram');
    """)
    seen = set()
    count = collections.Counter()
    pages = collections.Counter()
    parsed = []
    for key, p in sorted(man["pages"].items(), key=lambda kv: kv[1]["ts"], reverse=True):
        if not p.get("file"):
            continue
        page = decode(open(os.path.join(RAW, p["file"]), "rb").read())
        entries, kind = parse(p["source"], p["url"], page, p["ts"])
        pages[p["source"]] += 1
        parsed.append({"p": p, "kind": kind, "entries": entries, "ts": p["ts"],
                       "series": entries[0].get("series", "") if entries else ""})
    fix_series_years([x for x in parsed if x["p"]["source"] == "seiryu"])
    for x in parsed:
        p, kind, entries = x["p"], x["kind"], x["entries"]
        src = sources.get(p["source"], {})
        for e in entries:
            if not e.get("date"):
                continue
            body = tidy_lines(e["body"])
            if len(body) < 8:
                continue
            h = hashlib.sha1(f'{p["source"]}|{e["date"]}|{re.sub(r"\s+", "", body)[:400]}'.encode("utf-8")).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            author = e["author"] or src.get("author", "")
            con.execute("INSERT INTO entries(source,author,date,time,title,body,url,page_url,wayback_ts,kind,series,approx) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (p["source"], author, e["date"], e["time"], e["title"], body, e["url"] or p["url"], p["url"], p["ts"], kind,
                         e.get("series", ""), int(bool(e.get("approx")))))
            count[p["source"]] += 1
    for sid, s in sources.items():
        con.execute("INSERT INTO sources VALUES(?,?,?,?,?,?)", (sid, s["label"], s["author"], s["prefix"], pages[sid], count[sid]))
    con.execute("INSERT INTO entries_fts(rowid, title, body) SELECT id, title, body FROM entries")
    con.commit()
    total = con.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM entries").fetchone()
    print(f"記事 {total[0]} 件 / {total[1]} 〜 {total[2]}")
    for sid, s in sources.items():
        print(f"  {s['label']}: ページ {pages[sid]} → 記事 {count[sid]}")
    con.close()


if __name__ == "__main__":
    main()
