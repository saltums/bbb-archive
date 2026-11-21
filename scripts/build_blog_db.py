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


def part_number(part):
    """「Vol.59」「Part12」「第6回」→ 59, 12, 6。番外編などは None。"""
    if not part or "番外" in part:
        return None
    m = re.search(r"(\d+)", part)
    return int(m.group(1)) if m else None


def fix_series_years(rows):
    """連載（「曖昧Diary 第N回」など）は回の順に日付が続くはずなので、
    各回の最初の日が前の回の最後の日より前にならない、いちばん早い年に揃える。"""
    groups = collections.defaultdict(list)
    for page in rows:
        num = part_number(page.get("part"))
        if page.get("series") and num is not None and any("ymd" in e for e in page["entries"]):
            groups[page["series"]].append((num, page))
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

# 置き場所ごとの、カテゴリーと連載の決まった名前（記事ごとに決まらないもの）
DEFAULTS = {
    "playlog-koide": ("日記", "小出メッセ"),
    "playlog-sekine": ("日記", "しおり暮らし"),
    "playlog-syohei": ("日記", "湯浅将平のブログ"),
    "playlog-hori": ("日記", "堀之内大介のブログ"),
    "bokuburo": ("ブログ", "ボクブロ"),
    "livedoor": ("日記", "livedoor ブログ"),
    "jfn": ("ラジオ", "JFN 番組ブログ"),
}

# 記事に書いた人が書かれていない置き場所の、書いた人（本文の名乗りで確かめたもの）
AUTHOR_DEFAULT = {"livedoor": "堀之内大介"}

# ---- 旧ホームページ（www.venus.dti.ne.jp/~seiryu/）の分類 ----
# (ファイル名, カテゴリー, 連載の名前, 書いた人, 種類)  連載の名前が空なら見出しから作る。種類 diary は日ごとに切る
SEIRYU = [
    (r"^nikki\d*\.html$", "日記", "小出日記", "小出祐介", "diary"),
    (r"^neonikki\d*\.html$", "日記", "ネオ小出日詩", "小出祐介", "diary"),
    (r"^aimainikki(bangai)?\d*\.html?$", "日記", "小出AIMAI日記", "小出祐介", "diary"),
    (r"^aimaidiary\d*\.html$", "日記", "曖昧Diary", "小出祐介", "diary"),
    (r"^taberu\d*\.html$", "メンバーのコーナー", "", "堀之内大介", "page"),
    (r"^cream\d*\.html$", "メンバーのコーナー", "湯浅CREAM（写真）", "湯浅将平", "page"),
    (r"^namacream\.html$", "メンバーのコーナー", "濃いで!!生クリーム（写真）", "小出祐介", "page"),
    (r"^kakusi\.html$", "メンバーのコーナー", "隠したつもりのページ（写真）", "堀之内大介", "page"),
    (r"^kasi\d*\.html$", "歌詞", "歌詞掲載", "小出祐介", "page"),
    (r"^(index\d*\.html?)?$", "トップページ", "トップページ", "", "page"),
    (r"^set\.html$", "ライブ", "セットリスト", "", "page"),
    (r"^(recohatu|senkou)\.htm$", "ライブ・リリースの告知", "告知ページ", "", "page"),
    (r"^disc\.htm$", "作品", "ディスコグラフィー", "", "page"),
    (r"^demo\.htm$", "作品", "デモ音源の通信販売", "", "page"),
    (r"^sekinemovie\.htm$", "お知らせ", "関根史織 映画『リンダ リンダ リンダ』出演", "", "page"),
]
SEIRYU_SKIP = r"^(koide|sekine|yuasa|horinouti)\.htm|^newpage|^livekan"   # 中身が「戻る」だけのページ

PART = re.compile(r"(Vol\.?\s*\d+|Part\s*\d+|第\s*\d+\s*[回話]|番外編\s*\d*|Lv\.?\s*\d+)", re.I)
HEAD_RANGE = re.compile(r"[(（](\d{1,2})月(\d{1,2})日")


def seiryu_name(url):
    u = url.replace("%7E", "~").replace("%7e", "~")
    u = re.sub(r"^.*?~seiryu/?", "", u) if "~seiryu" in u else re.sub(r"^https?://[^/]+/?", "", u)
    return u.split("?")[0]


def heading_of(page):
    body = re.search(r"<body[^>]*>(.*)</body>", page, re.S | re.I)
    raw_html = body.group(1) if body else page
    head = re.search(r"<b>(.*?)</b>", raw_html, re.S | re.I)
    first = unicodedata.normalize("NFKC", text_of(head.group(1) if head else raw_html)).strip().split("\n")[0]
    return first[:80]


def parse_seiryu(url, page, ts):
    name = seiryu_name(url)
    if re.search(SEIRYU_SKIP, name):
        return [], None
    rule = next((r for r in SEIRYU if re.search(r[0], name)), None)
    category, series, author, mode = (rule[1:] if rule else ("その他", "その他のページ", "", "page"))
    head = heading_of(page)
    part_m = PART.search(head)
    part = re.sub(r"\s+", "", part_m.group(1)) if part_m else ""
    if not series:
        series = re.sub(r"[『』]", "", PART.split(head)[0]).strip(" ・…!") or head
    meta = {"category": category, "series": series, "author": author, "part": part, "heading": head}
    if mode == "diary":
        # 見出しに日付が1日だけの回（「小出日記Vol.58(12月30日)」）は1日分の日記。
        # 本文中の「3月」「10日、」は振り返りや小見出しなので、分けずに見出しの日付で1件にする
        single = re.search(r"[(（]\d{1,2}月\d{1,2}日[)）]", head)
        entries = [] if single else parse_dated_text(page, ts)
        if not any("ymd" in e for e in entries):
            # 日付の見出しが無い回（「小出日記Vol.59(12月31日)」など）は、見出しの日付で1件にする
            hm = HEAD_RANGE.search(head)
            if hm:
                txt = unicodedata.normalize("NFKC", text_of(re.search(r"<body[^>]*>(.*)</body>", page, re.S | re.I).group(1)
                                                             if re.search(r"<body", page, re.I) else page))
                body = txt.split("\n", 1)[1] if "\n" in txt else txt
                entries = [{"ymd": (0, int(hm.group(1)), int(hm.group(2))), "time": "", "title": "", "body": body,
                            "url": "", "author": ""}]
                assign_years(entries, ts)
        for e in entries:
            e.update({k: v for k, v in meta.items() if k != "heading"})
            e["series_heading"] = head
        return entries, meta
    # 日記以外は1ページを1件。日付は保存された日（おおよそ）
    txt = tidy_lines(unicodedata.normalize("NFKC", text_of(re.search(r"<body[^>]*>(.*)</body>", page, re.S | re.I).group(1)
                                                                if re.search(r"<body", page, re.I) else page)))
    if len(re.sub(r"\s|戻る|☆|前の写真|次の写真", "", txt)) < 10:
        return [], None
    title = head if series in ("トップページ",) else head
    entry = {"date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "time": "", "title": title, "body": txt, "url": "", "approx": True}
    entry.update({k: v for k, v in meta.items() if k != "heading"})
    return [entry], meta


# ---- 公式サイト・レーベル・tumblr のページの分類（URL で決める） ----
# (置き場所の正規表現, URL の正規表現, カテゴリー, 連載の名前, 書いた人, 読み方)  読み方 skip は取り込まない
PAGE_RULES = [
    (r"^official", r"cgi-bin/diary", "日記", "公式サイトの小出日記", "小出祐介", "cgi"),
    (r"^official", r"cgi-bin/hamripo|/ham/", "スタッフ", "ハムリポ（マネージャー）", "", "cgi"),
    (r"^official", r"epad|/bbs/|upgrade_flash|/movie/", "", "", "", "skip"),   # 掲示板・旧HPの写し・Flash
    (r"^official", r"/news/", "お知らせ", "ニュース", "", "page"),
    (r"^official", r"/artist/profile/", "", "", "", "skip"),   # 事務所(SMA)のページの写し。robots の方針どおり取り込まない
    (r"^official", r"/live/", "ライブ", "ライブ情報", "", "page"),
    (r"^official", r"/dis(c|co)/|/album/", "作品", "ディスコグラフィー", "", "page"),
    (r"^official", r"/bio/", "プロフィール", "バイオグラフィー", "", "page"),
    (r"^official", r"/goods/|/shop/", "グッズ", "グッズ", "", "page"),
    (r"^official", r"/media/", "メディア", "メディア出演", "", "page"),
    (r"^official", r"/sp/", "特設ページ", "特設ページ", "", "page"),
    (r"^official", r".", "トップページ", "トップページ", "", "page"),
    (r"^universal", r"wp-json|xmlrpc|oembed|/discography|/page/\d|/news/?$|/news/(cat|page)/", "", "", "", "skip"),
    (r"^universal", r"/news/", "お知らせ", "ニュース", "", "page"),
    (r"^universal", r"/products/", "作品", "商品ページ", "", "page"),
    (r"^universal", r"/biography", "プロフィール", "バイオグラフィー", "", "page"),
    (r"^universal", r".", "トップページ", "トップページ", "", "page"),
    (r"^emi", r"variety/backnumber", "連載", "バラエティ（バックナンバー）", "", "page"),
    (r"^emi", r"about_band_b", "作品", "小冊子「バンドBについて」", "", "page"),
    (r"^emi", r"about_album_c|c_archive", "作品", "『C』特設ページ", "", "page"),
    (r"^emi", r"girlfriend|standbyme|electricsummer", "作品", "作品の特設ページ", "", "page"),
    (r"^emi", r"profile|artistinfo", "プロフィール", "プロフィール", "", "page"),
    (r"^emi", r"liveinfo", "ライブ", "ライブ情報", "", "page"),
    (r"^emi", r"sstv", "メディア", "SSTV", "", "page"),
    (r"^emi", r"comment", "お知らせ", "コメント", "", "page"),
    (r"^emi", r"bloger", "その他", "その他のページ", "", "page"),
    (r"^emi", r".", "トップページ", "トップページ", "", "page"),
    (r"^tumblr", r"/post/\d+", "写真", "ライブ写真（tumblr）", "", "tumblr"),
    (r"^tumblr", r".", "", "", "", "skip"),
    (r"^jfn", r"\.xml$", "", "", "", "skip"),
]
TITLE_TAIL = re.compile(r"\s*[-|｜/]\s*(UNIVERSAL MUSIC JAPAN|Base Ball Bear.*|BaseBallBear.*|ベースボールベアー.*)$")
MAIN_BLOCK = re.compile(r'<(?:div|article|section)[^>]+class="(?:[^"]*\b)?(newsArticle|main-editor-content|disco-main|oneInfo|infoDet|post)\b[^"]*"', re.I)


def page_rule(source, url):
    return next((r for r in PAGE_RULES if re.search(r[0], source) and re.search(r[1], url)), None)


def page_title(page):
    t = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
    s = unicodedata.normalize("NFKC", htmllib.unescape(t.group(1))).strip() if t else ""
    for _ in range(2):
        s = TITLE_TAIL.sub("", s).strip()
    return s


def parse_page(url, page, ts):
    """お知らせ・作品・プロフィールなどのページを1件に。本文は記事部分があればそこだけ、無ければ body 全体。"""
    body = re.search(r"<body[^>]*>(.*)</body>", page, re.S | re.I)
    raw_html = body.group(1) if body else page
    m = MAIN_BLOCK.search(raw_html)
    if m:
        raw_html = raw_html[m.start():]
        raw_html = re.split(r'<(?:div|footer)[^>]+(?:class|id)="(?:footer|footerWrap|local-footer|notes|social)', raw_html)[0]
    txt = tidy_lines(unicodedata.normalize("NFKC", text_of(raw_html)).replace("ご使用のブラウザはJavascriptに対応していません", ""))
    if len(re.sub(r"\s|［画像］", "", txt)) < 20 or "ページが見つかりません" in txt:
        return []
    d = re.search(r"/(20\d\d)/(\d\d)/(\d\d)/?$", url) or re.search(r"/(20\d\d)-(\d\d)-(\d\d)", url)
    date, approx = (iso(*d.groups()), False) if d else (f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", True)
    title = page_title(page) or next((ln.strip()[:40] for ln in txt.splitlines()
                                      if ln.strip() and ln.strip() != "［画像］"), "")
    return [{"date": date, "time": "", "title": title, "body": txt, "url": "", "author": "", "approx": approx}]


def parse_tumblr(url, page, ts):
    t = page_title(page)
    title = t.split(",", 1)[1].strip() if "," in t else t
    m = re.search(r'<div class="post[^"]*">(.*?)<div class="(?:notecontainer|notes|footer)', page, re.S)
    txt = tidy_lines(text_of(m.group(1))) if m else ""
    txt = re.sub(r"Posted .*? ago|\d+ notes", "", txt).strip()
    d = re.search(r"(20\d\d)(\d\d)(\d\d)", title)
    date, approx = (iso(*d.groups()), False) if d else (f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", True)
    if title and title not in txt:
        txt = (title + "\n" + txt).strip()
    return [{"date": date, "time": "", "title": title, "body": txt or "［画像］", "url": "", "author": "", "approx": approx}]


def parse(source, url, page, ts=""):
    if source in PARSERS:
        if source == "jfn" and re.search(r"\.xml$", url):
            return [], "blog"
        return PARSERS[source](page), "blog"
    if source.startswith("playlog"):
        return parse_playlog(page, ts), "blog"
    if source == "seiryu":
        entries, meta = parse_seiryu(url, page, ts)
        return entries, ("blog" if meta and meta["category"] == "日記" else "page")
    rule = page_rule(source, url)
    if rule:
        _, _, category, series, author, mode = rule
        if mode == "skip":
            return [], "page"
        entries = parse_cgi_diary(page) if mode == "cgi" else parse_tumblr(url, page, ts) if mode == "tumblr" else parse_page(url, page, ts)
        for e in entries:
            e.update({"category": category, "series": series})
            e["author"] = e.get("author") or author
        return entries, ("blog" if mode == "cgi" else "page")
    return parse_dated_text(page, ts), "page"


PLAYLOG_ENTRY = re.compile(r'<div class="title-area(?:-single)?">(.*?)</div>\s*<div class="article">(.*?)</div>\s*<div class="posted">\s*'
                           r'(\d{4})-(\d\d)-(\d\d)\s+(\d\d:\d\d)', re.S)


def parse_playlog(page, ts=""):
    """playlog の記事（1件のページも、月ごとのページも同じ形: 題名 → 本文 → 投稿日時）。見つからないページは捨てる。"""
    if "ページが見つかりません" in page:
        return []
    return [{"date": iso(y, mo, d), "time": hm, "title": text_of(t), "body": text_of(b), "url": "", "author": ""}
            for t, b, y, mo, d, hm in PLAYLOG_ENTRY.findall(page)]


# ---- 見せるためのまとめ（元のページから、歌詞・セットリスト・作品を1件ずつに分ける） ----

# まとめでは要らない、ページの操作用の言葉（「戻る」「前の歌詞」「トップへ」など）
NAV_WORDS = re.compile(r"\[画像\]|戻る|(?:前|次|最新)の(?:歌詞|写真|ページ|記事|日記)|(?:トップ|TOP|top|ページの先頭|上)へ|BACK|HOME|NEXT|PREV|[→←↑↓]")


def clean_nav(text):
    """画像の印と操作用の言葉だけでできた行を落とす（本文の言葉は残す）。元のページには使わない。"""
    lines = [ln for ln in (text or "").split("\n") if NAV_WORDS.sub("", ln).strip(" 　・|｜/")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def song_key(title):
    """曲名の表記ゆれをならす（「かげない2人」「かげない二人」、全角半角、記号、括弧の注記）。"""
    t = unicodedata.normalize("NFKC", title).lower()
    t = re.sub(r"[(（\[【].*?[)）\]】]", "", t)
    t = t.replace("二", "2").replace("・", "").replace("’", "'")
    return re.sub(r"[\s\-_:!！?？☆.,、。'\"~〜]", "", t)


def derive_lyrics(entry):
    """「曲名   作詞・作曲 小出祐介」の行で1曲ずつに切る。"""
    out, cur = [], None
    for ln in entry["body"].split("\n"):
        m = re.match(r"^(.+?)\s*(作詞(?:・作曲)?|作曲)\s*[:：]?\s*(.+)$", ln.strip())
        if m and len(m.group(1)) <= 40:
            if cur:
                out.append(cur)
            cur = {"title": m.group(1).strip(), "sub": f"{m.group(2)} {m.group(3).strip()}", "lines": []}
        elif cur is not None:
            if ln.strip() in ("[画像]", "戻る"):
                continue
            cur["lines"].append(ln)
    if cur:
        out.append(cur)
    return [{"kind": "lyric", "title": x["title"], "sub": x["sub"], "date": "", "body": "\n".join(x["lines"]).strip(),
             "songs": []} for x in out if "\n".join(x["lines"]).strip()]


def derive_setlists(entry):
    """「2004年12月3日(金) 新宿ロフトでのライブセット!!」で公演ごとに切り、曲を順に並べる。"""
    out, cur = [], None
    last = None   # 直前の公演の (年, 月)。一覧は新しい順なので、年の無い行は月が増えたら前の年
    for ln in entry["body"].split("\n"):
        s = ln.strip()
        m = re.match(r"^(?:((?:19|20)\d\d)年)?(\d{1,2})月(\d{1,2})日\s*(?:[(（][^)）]*[)）])?\s*(.*?)(?:での|にて)?ライブ(?:セット)?(?:リスト)?[!！]*\s*$", s)
        if m and (m.group(1) or last):
            month, day = int(m.group(2)), int(m.group(3))
            year = int(m.group(1)) if m.group(1) else (last[0] - 1 if month > last[1] else last[0])
            last = (year, month)
            if cur:
                out.append(cur)
            venue, notes = m.group(4).strip(" 　"), []
            part = re.match(r"^[-‐−ー]?\s*(昼|夜)\s*(.*)$", venue)
            if part:
                venue, notes = part.group(2), [f"{part.group(1)}の部"]
            cur = {"date": iso(year, month, day), "venue": venue, "notes": notes, "songs": []}
            continue
        if cur is None or not s or s in ("[画像]", "戻る"):
            continue
        sm = re.match(r"^(Ec|EC|En|EN|アンコール)?\s*(\d*)\s*[.．:]\s*(.+)$", s)
        if sm and (sm.group(1) or sm.group(2)):
            cur["songs"].append({"no": ("アンコール" + (sm.group(2) or "")) if sm.group(1) else sm.group(2), "title": sm.group(3).strip(),
                                 "encore": bool(sm.group(1))})
        elif "[画像]" not in s and "戻る" not in s:
            cur["notes"].append(s.strip("~〜【】 "))
    if cur:
        out.append(cur)
    return [{"kind": "setlist", "title": x["venue"] or "（会場不明）", "sub": "・".join(x["notes"]), "date": x["date"],
             "body": "\n".join(f'{s["no"]}. {s["title"]}' for s in x["songs"]), "songs": x["songs"]} for x in out if x["songs"]]


def derive_releases(entry):
    """上の年表（いつ・何を・どこで）と、下の【作品名】収録曲 を合わせて、作品ごとにする。"""
    body = entry["body"]
    # 年表の部分: 「2002年7月  デモ音源第一弾『前-front-』『後-back-』(CD-R)」に続く説明の行
    head, _, detail = body.partition("【")
    timeline = []
    for chunk in re.split(r"\n(?=(?:19|20)\d\d年\d{1,2}月)", "\n" + head):
        chunk = chunk.strip()
        m = re.match(r"^((?:19|20)\d\d)年(\d{1,2})月(?:(\d{1,2})日)?\s*(.*)$", chunk, re.S)
        if m:
            text = re.sub(r"\s*\n\s*", " ", m.group(4)).replace("[画像]", "").strip()
            date = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}" + (f"-{int(m.group(3)):02d}" if m.group(3) else "")
            timeline.append({"date": date, "text": text})
    out = []
    for block in ("【" + detail).split("【")[1:]:
        name, _, rest = block.partition("】")
        name = re.sub(r"\s*\n\s*", " ", name).strip()
        tracks, notes = [], []
        for ln in rest.split("\n"):
            s = ln.strip()
            tm = re.match(r"^(\d+)\s*[.．]\s*(.+)$", s)
            if tm:
                tracks.append({"no": tm.group(1), "title": tm.group(2).strip(), "encore": False})
            elif s and s not in ("[画像]", "収録曲", "戻る") and not s.startswith("『"):
                notes.append(s)
        # 年表から、この作品の発売時期と説明を探す。「デモ音源第七弾」「1stシングル」のような種類の名前で突き合わせる
        def flat(x):
            return re.sub(r"\s", "", x)
        kind_name = flat(name.split("『")[0])
        when = next((t for t in timeline if kind_name and kind_name in flat(t["text"])), None)
        out.append({"kind": "release", "title": name, "sub": when["text"] if when else "", "date": when["date"] if when else "",
                    "body": "\n".join(f'{t["no"]}. {t["title"]}' for t in tracks) + ("\n\n" + "\n".join(notes) if notes else ""),
                    "songs": tracks})
    return out


DERIVE = {("seiryu", "歌詞掲載"): derive_lyrics, ("seiryu", "セットリスト"): derive_setlists,
          ("seiryu", "ディスコグラフィー"): derive_releases}


def build_items(con):
    """元のページ（entries）から、見せるための items を作る。出典の記事 id を必ず残す。"""
    con.executescript("""
    CREATE TABLE items(id INTEGER PRIMARY KEY, kind TEXT, title TEXT, sub TEXT, date TEXT, body TEXT, songs TEXT,
      song_key TEXT, source_entry INTEGER, source TEXT, position INTEGER);
    CREATE INDEX items_kind ON items(kind, date);
    """)
    rows = con.execute("SELECT id, source, series, body, wayback_ts, url FROM entries ORDER BY wayback_ts").fetchall()
    seen = set()
    for eid, source, series, body, ts, url in rows:
        fn = DERIVE.get((source, series))
        if not fn:
            continue
        for pos, it in enumerate(fn({"body": body})):
            it["body"], it["sub"] = clean_nav(it["body"]), clean_nav(it["sub"])
            key = (it["kind"], song_key(it["title"]) if it["kind"] == "lyric" else it["title"], it["date"])
            if key in seen:
                continue
            seen.add(key)
            con.execute("INSERT INTO items(kind,title,sub,date,body,songs,song_key,source_entry,source,position) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (it["kind"], it["title"], it["sub"], it["date"], it["body"], json.dumps(it["songs"], ensure_ascii=False),
                         song_key(it["title"]) if it["kind"] == "lyric" else "", eid, source, pos))
    for kind, n in con.execute("SELECT kind, COUNT(*) FROM items GROUP BY kind"):
        print(f"  まとめ {kind}: {n} 件")


def main():
    man = json.load(open(os.path.join(OUT, "manifest.json"), encoding="utf-8"))
    sources = man.get("sources", {})
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE sources(id TEXT PRIMARY KEY, label TEXT, author TEXT, prefix TEXT, pages INTEGER, entries INTEGER);
    CREATE TABLE entries(id INTEGER PRIMARY KEY, source TEXT, author TEXT, date TEXT, time TEXT, title TEXT,
      body TEXT, url TEXT, page_url TEXT, wayback_ts TEXT, kind TEXT, series TEXT, approx INTEGER,
      category TEXT, part TEXT, heading TEXT);
    CREATE INDEX entries_series ON entries(source, category, series, date);
    CREATE INDEX entries_date ON entries(date);
    CREATE INDEX entries_source ON entries(source, date);
    CREATE VIRTUAL TABLE entries_fts USING fts5(title, body, content='entries', content_rowid='id', tokenize='trigram');
    """)
    seen = set()
    count = collections.Counter()
    pages = collections.Counter()
    parsed = []
    for key, p in sorted(man["pages"].items(), key=lambda kv: kv[1]["ts"], reverse=True):
        path = os.path.join(RAW, p["file"]) if p.get("file") else ""
        if not path or not os.path.exists(path):
            continue
        page = decode(open(path, "rb").read())
        if re.search(r"baseballbear\.(com|net)(:\d+)?/aimaidiary", p["url"]):
            # 公式サイトに移された曖昧Diary は旧ホームページの続き（第13回〜）。同じ連載として旧ホームページ側にまとめる
            p = dict(p, source="seiryu", moved=True)
        elif p["source"] == "official-net":
            # baseballbear.net は .com と同じ公式サイト（ドメインが変わっただけ）。同じ日記が二重にならないよう .com にまとめる
            p = dict(p, source="official-com")
        entries, kind = parse(p["source"], p["url"], page, p["ts"])
        pages[p["source"]] += 1
        parsed.append({"p": p, "kind": kind, "entries": entries, "ts": p["ts"],
                       "series": entries[0].get("series", "") if entries else "",
                       "part": entries[0].get("part", "") if entries else ""})
    # 公式サイトの写しのうち、旧ホームページにも残っている回は捨てる（日付の付け方が崩れるため）
    own = {(x["series"], x["part"]) for x in parsed if x["p"]["source"] == "seiryu" and not x["p"].get("moved")}
    parsed = [x for x in parsed if not (x["p"].get("moved") and (x["series"], x["part"]) in own)]
    fix_series_years([x for x in parsed if x["p"]["source"] == "seiryu"])
    # 古い保存から順に入れ、同じ中身（トップページの同じ版など）は最初の1つだけ残す
    parsed.sort(key=lambda x: x["ts"])
    for x in parsed:
        p, kind, entries = x["p"], x["kind"], x["entries"]
        src = sources.get(p["source"], {})
        cat_default, series_default = DEFAULTS.get(p["source"], ("その他", src.get("label", p["source"])))
        for e in entries:
            if not e.get("date"):
                continue
            body = tidy_lines(e["body"])
            if len(body) < 8:
                continue
            key_date = "" if e.get("approx") else e["date"]
            h = hashlib.sha1(f'{p["source"]}|{key_date}|{re.sub(r"\s+", "", body)[:600]}'.encode("utf-8")).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            author = e.get("author") or AUTHOR_DEFAULT.get(p["source"]) or src.get("author", "")
            con.execute("""INSERT INTO entries(source,author,date,time,title,body,url,page_url,wayback_ts,kind,series,approx,category,part,heading)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (p["source"], author, e["date"], e.get("time", ""), e.get("title", ""), body, e.get("url") or p["url"], p["url"],
                         p["ts"], kind, e.get("series") or series_default, int(bool(e.get("approx"))),
                         e.get("category") or cat_default, e.get("part", ""), e.get("series_heading", "")))
            count[p["source"]] += 1
    for sid, s in sources.items():
        con.execute("INSERT INTO sources VALUES(?,?,?,?,?,?)", (sid, s["label"], s["author"], s["prefix"], pages[sid], count[sid]))
    con.execute("INSERT INTO entries_fts(rowid, title, body) SELECT id, title, body FROM entries")
    build_items(con)
    con.commit()
    total = con.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM entries").fetchone()
    print(f"記事 {total[0]} 件 / {total[1]} 〜 {total[2]}")
    for sid, s in sources.items():
        print(f"  {s['label']}: ページ {pages[sid]} → 記事 {count[sid]}")
    con.close()


if __name__ == "__main__":
    main()
