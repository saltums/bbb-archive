#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5ch アーカイブの検索画面を手元だけで開く（127.0.0.1 のみ、外には出さない）。

  python scripts/serve_5ch_search.py [ポート]
"""
import collections, json, math, os, re, sqlite3, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bbb_terms import Extractor, norm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "5ch-archive", "bbb5ch.sqlite")
WORKS = os.path.join(ROOT, "data", "5ch-archive", "works")
SONGS = os.path.join(ROOT, "data", "songs.json")
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "5ch_search.html")
PORT = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8770))
sys.stdout.reconfigure(encoding="utf-8")
PAGE_SIZE = 40
SAMPLE = 3000          # 関連ワードを数えるときに読む投稿の上限
POST_COLS = "p.thread_key, p.no, p.name, p.mail, p.date_raw, p.posted_at, p.uid, p.body"

EX = Extractor()
VOCAB = {"mtime": None, "terms": {}, "ordered": [], "posts": 1}


def db():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def vocab():
    """ことばの表を読み込む。データベースを作り直したら読み直す。"""
    mtime = os.path.getmtime(DB)
    if VOCAB["mtime"] != mtime:
        con = db()
        rows = con.execute("SELECT key, display, kind, df FROM terms ORDER BY df DESC").fetchall()
        VOCAB.update(mtime=mtime, terms={r["key"]: (r["display"], r["kind"], r["df"]) for r in rows},
                     ordered=[(r["key"], r["display"], r["kind"], r["df"]) for r in rows],
                     posts=con.execute("SELECT COUNT(*) FROM posts").fetchone()[0] or 1)
        con.close()
    return VOCAB


def like_escape(term):
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def first(q, name):
    return q.get(name, [""])[0].strip()


def conditions(q):
    terms = [t for t in re.split(r"[\s　]+", first(q, "q")) if t]
    where, args = ["1=1"], []
    if first(q, "kind") in ("main", "related", "other"):
        where.append("t.kind = ?")
        args.append(first(q, "kind"))
    # 3文字以上の語は全文検索の索引、2文字以下（「小出」「野音」など）は総当たりで探す
    long_terms = [t for t in terms if len(t) >= 3]
    if long_terms:
        where.append("p.id IN (SELECT rowid FROM posts_fts WHERE posts_fts MATCH ?)")
        args.append(" AND ".join('"' + t.replace('"', '""') + '"' for t in long_terms))
    for t in terms:
        if len(t) < 3:
            where.append("p.body LIKE ? ESCAPE '\\'")
            args.append("%" + like_escape(t) + "%")
    if first(q, "from"):
        where.append("p.posted_at >= ?")
        args.append(first(q, "from") + " 00:00:00")
    if first(q, "to"):
        where.append("p.posted_at <= ?")
        args.append(first(q, "to") + " 23:59:59")
    if first(q, "nodate"):
        where.append("p.posted_at IS NULL")
    for name, col in (("thread", "p.thread_key"), ("uid", "p.uid")):
        if first(q, name):
            where.append(f"{col} = ?")
            args.append(first(q, name))
    return terms, " AND ".join(where), args


def related(con, terms, total):
    """当てはまった投稿に、ふだんより目立って多く出てくる語を返す。"""
    v = vocab()
    bodies = [r[0] for r in con.execute(
        "SELECT body FROM posts WHERE id IN (SELECT id FROM hits ORDER BY (id * 2654435761) % 1000003 LIMIT ?)",
        (SAMPLE,))]
    n = len(bodies)
    if n < 5:
        return {"songs": [], "words": []}
    counts = collections.Counter()
    for body in bodies:
        counts.update(EX.terms(body).keys())
    asked = [norm(t) for t in terms]
    scored = []
    for key, c in counts.items():
        entry = v["terms"].get(key)
        if not entry or any(key in a or a in key for a in asked):
            continue
        display, kind, df = entry
        named = kind in ("song", "album")
        if c < max(2 if named else 3, n * (0.003 if named else 0.005)):
            continue
        lift = (c / n) / (df / v["posts"])
        if lift < 1.5:
            continue
        scored.append((c * min(math.log2(lift), 5), display, kind, round(c * total / n)))
    scored.sort(reverse=True)
    pick = lambda kinds, limit: [{"t": d, "k": k, "n": c} for _, d, k, c in scored if k in kinds][:limit]
    return {"songs": pick(("song", "album"), 10), "words": pick(("word", "member"), 16)}


def search(q):
    terms, cond, args = conditions(q)
    order = "ASC" if first(q, "order") == "old" else "DESC"
    page = max(1, int(first(q, "page") or 1))
    con = db()
    con.execute(f"""CREATE TEMP TABLE hits AS SELECT p.id, p.thread_key, p.posted_at
                    FROM posts p JOIN threads t ON t.key = p.thread_key WHERE {cond}""", args)
    total = con.execute("SELECT COUNT(*) FROM hits").fetchone()[0]
    rows = con.execute(
        f"""SELECT {POST_COLS}, t.title, t.vol, t.kind, t.board
            FROM hits h JOIN posts p ON p.id = h.id JOIN threads t ON t.key = p.thread_key
            ORDER BY h.posted_at {order}, h.id {order} LIMIT ? OFFSET ?""",
        (PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
    years = con.execute("""SELECT substr(posted_at,1,4) y, COUNT(*) n FROM hits
                           WHERE posted_at IS NOT NULL GROUP BY y ORDER BY y""").fetchall()
    months = []
    if first(q, "from")[:4] and first(q, "from")[:4] == first(q, "to")[:4]:
        months = con.execute("""SELECT substr(posted_at,6,2) m, COUNT(*) n FROM hits
                                WHERE posted_at IS NOT NULL GROUP BY m ORDER BY m""").fetchall()
    nodate = con.execute("SELECT COUNT(*) FROM hits WHERE posted_at IS NULL").fetchone()[0]
    top_threads = con.execute(
        """SELECT t.key, t.title, t.vol, t.kind, COUNT(*) n FROM hits h JOIN threads t ON t.key = h.thread_key
           GROUP BY t.key ORDER BY n DESC LIMIT 6""").fetchall()
    narrowed = bool(terms or any(first(q, k) for k in ("from", "to", "uid", "thread", "nodate")))
    rel = related(con, terms, total) if page == 1 and narrowed else None
    con.close()
    return {"total": total, "page": page, "page_size": PAGE_SIZE, "terms": terms, "nodate": nodate,
            "posts": [dict(r) for r in rows], "years": [[r["y"], r["n"]] for r in years],
            "months": [[r["m"], r["n"]] for r in months], "top_threads": [dict(r) for r in top_threads],
            "related": rel}


def suggest(q):
    """入力中の語に続く候補（曲名・作品名・よく出る語）。"""
    word = norm(re.split(r"[\s　]+", first(q, "q"))[-1] if first(q, "q") else "")
    if not word:
        return {"items": []}
    head, inner = [], []
    for key, display, kind, df in vocab()["ordered"]:
        if key == word:
            continue
        if key.startswith(word):
            head.append({"t": display, "k": kind, "n": df})
        elif word in key and len(inner) < 8:
            inner.append({"t": display, "k": kind, "n": df})
        if len(head) >= 8:
            break
    return {"items": (head + inner)[:8]}


def home():
    v = vocab()
    top = lambda kind, limit: [{"t": d, "k": k, "n": n} for _, d, k, n in v["ordered"] if k == kind][:limit]
    members = [{"t": name, "k": "member", "n": v["terms"].get(norm(name), ("", "", 0))[2]}
               for name in ("小出", "関根", "堀之内", "湯浅")]
    return {"songs": top("song", 18), "albums": top("album", 12), "members": members}


def threads():
    con = db()
    rows = con.execute("""SELECT key, board, title, vol, kind, source, post_count, first_at, last_at
                          FROM threads ORDER BY first_at DESC""").fetchall()
    stats = con.execute("""SELECT (SELECT COUNT(*) FROM posts) n, (SELECT MIN(first_at) FROM threads) a,
                                  (SELECT MAX(posted_at) FROM posts) b""").fetchone()
    con.close()
    return {"threads": [dict(r) for r in rows], "posts": stats["n"], "first": stats["a"], "last": stats["b"]}


def thread(q):
    key = first(q, "key")
    con = db()
    t = con.execute("SELECT * FROM threads WHERE key = ?", (key,)).fetchone()
    rows = con.execute(f"SELECT {POST_COLS} FROM posts p WHERE p.thread_key = ? ORDER BY p.no", (key,)).fetchall()
    prev = nxt = None
    if t and t["kind"] == "main":
        near = lambda vol: con.execute("SELECT key, vol FROM threads WHERE kind = 'main' AND vol = ?", (vol,)).fetchone()
        prev, nxt = near(t["vol"] - 1), near(t["vol"] + 1)
    con.close()
    return {"thread": dict(t) if t else None, "posts": [dict(r) for r in rows],
            "prev": dict(prev) if prev else None, "next": dict(nxt) if nxt else None}


def some_posts(q):
    """前後を見る・アンカーの吹き出し用に、スレの中の番号の範囲を返す。"""
    lo, hi = int(first(q, "from") or 1), int(first(q, "to") or first(q, "from") or 1)
    con = db()
    rows = con.execute(f"""SELECT {POST_COLS} FROM posts p WHERE p.thread_key = ? AND p.no BETWEEN ? AND ?
                           ORDER BY p.no LIMIT 30""", (first(q, "key"), lo, hi)).fetchall()
    con.close()
    return {"posts": [dict(r) for r in rows]}


def load_works():
    out = {}
    if os.path.isdir(WORKS):
        for name in sorted(os.listdir(WORKS)):
            if name.endswith(".json"):
                w = json.load(open(os.path.join(WORKS, name), encoding="utf-8"))
                out[w["id"]] = w
    return out


def tracks_of(album_title):
    if not os.path.exists(SONGS):
        return []
    for r in json.load(open(SONGS, encoding="utf-8")):
        if r.get("album_title") == album_title:
            return [t["title"] if isinstance(t, dict) else t for t in r.get("tracks", [])]
    return []


def stance_counts(refs):
    c = collections.Counter(ref[2] for ref in refs)
    return {k: c.get(k, 0) for k in ("pos", "mixed", "neutral", "neg")}


def works(q):
    items = []
    for w in load_works().values():
        refs = [r for t in w["topics"] for r in t["refs"]]
        items.append({"id": w["id"], "title": w["album_title"], "label": w.get("label", ""),
                      "release_date": w.get("release_date", ""), "overview": w.get("overview", ""),
                      "topics": len(w["topics"]), "stance": stance_counts(refs),
                      "mentions": sum(n for _, n in w.get("mentions_by_year", []))})
    items.sort(key=lambda x: x["release_date"])
    return {"works": items}


def work(q):
    w = load_works().get(first(q, "id"))
    if not w:
        return {"work": None}
    con = db()
    for t in w["topics"]:
        posts = []
        for key, no, stance in t["refs"]:
            r = con.execute(f"""SELECT {POST_COLS}, t.title, t.vol, t.kind, t.board FROM posts p
                                JOIN threads t ON t.key = p.thread_key WHERE p.thread_key = ? AND p.no = ?""",
                            (key, no)).fetchone()
            if r:
                posts.append(dict(r, stance=stance))
        t["posts"] = posts
        t["stance"] = stance_counts(t["refs"])
    con.close()
    w["tracks"] = tracks_of(w["album_title"])
    w["stance"] = stance_counts([r for t in w["topics"] for r in t["refs"]])
    return {"work": w}


BLOG_DB = os.path.join(ROOT, "data", "blog-archive", "blogs.sqlite")
DIARY_PAGE = 30


def blog_db():
    con = sqlite3.connect(f"file:{BLOG_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def diary(q):
    """取り戻した日記・ブログの記事を絞り込んで返す。"""
    if not os.path.exists(BLOG_DB):
        return {"missing": True}
    where, args = ["e.kind = 'blog'"], []
    for name, col in (("author", "e.author"), ("source", "e.source")):
        v = first(q, name)
        if v == "-":
            where.append(f"({col} IS NULL OR {col} = '')")
        elif v:
            where.append(f"{col} = ?")
            args.append(v)
    terms = [t for t in re.split(r"[\s　]+", first(q, "q")) if t]
    long_terms = [t for t in terms if len(t) >= 3]
    if long_terms:
        where.append("e.id IN (SELECT rowid FROM entries_fts WHERE entries_fts MATCH ?)")
        args.append(" AND ".join('"' + t.replace('"', '""') + '"' for t in long_terms))
    for t in terms:
        if len(t) < 3:
            where.append("(e.body LIKE ? ESCAPE '\\' OR e.title LIKE ? ESCAPE '\\')")
            args += ["%" + like_escape(t) + "%"] * 2
    if first(q, "from"):
        where.append("e.date >= ?")
        args.append(first(q, "from"))
    if first(q, "to"):
        where.append("e.date <= ?")
        args.append(first(q, "to"))
    cond = " AND ".join(where)
    order = "DESC" if first(q, "order") == "new" else "ASC"
    page = max(1, int(first(q, "page") or 1))
    con = blog_db()
    total = con.execute(f"SELECT COUNT(*) FROM entries e WHERE {cond}", args).fetchone()[0]
    rows = con.execute(f"""SELECT e.id, e.source, e.author, e.date, e.time, e.title, e.body, e.url, e.series, e.wayback_ts
                           FROM entries e WHERE {cond} ORDER BY e.date {order}, e.id {order} LIMIT ? OFFSET ?""",
                       args + [DIARY_PAGE, (page - 1) * DIARY_PAGE]).fetchall()
    years = con.execute(f"""SELECT substr(e.date,1,4) y, COALESCE(NULLIF(e.author,''),'-') a, COUNT(*) n
                            FROM entries e WHERE {cond} GROUP BY y, a ORDER BY y""", args).fetchall()
    base = con.execute("""SELECT s.id, s.label, s.author, s.pages, COUNT(e.id) n, MIN(e.date) a, MAX(e.date) b
                          FROM sources s LEFT JOIN entries e ON e.source = s.id AND e.kind = 'blog'
                          GROUP BY s.id ORDER BY MIN(e.date)""").fetchall()
    authors = con.execute("""SELECT COALESCE(NULLIF(author,''),'-') a, COUNT(*) n FROM entries WHERE kind='blog'
                             GROUP BY a ORDER BY n DESC""").fetchall()
    con.close()
    return {"total": total, "page": page, "page_size": DIARY_PAGE, "terms": terms,
            "entries": [dict(r) for r in rows], "years": [list(r) for r in years],
            "sources": [dict(r) for r in base], "authors": [list(r) for r in authors]}


# 整理が済んで、確認してもらえる置き場所（ほかは取得・整理の途中）
OA_READY = {"seiryu", "official-com", "official-net", "playlog-koide", "playlog-sekine", "playlog-syohei", "playlog-hori",
            "livedoor", "bokuburo", "jfn", "universal", "emi", "emi2", "tumblr"}
CATEGORY_ORDER = ["日記", "ブログ", "スタッフ", "メンバーのコーナー", "連載", "ラジオ", "歌詞", "お知らせ", "ライブ",
                  "ライブ・リリースの告知", "作品", "プロフィール", "メディア", "写真", "グッズ", "特設ページ", "トップページ", "その他"]


def part_num(part):
    m = re.search(r"(\d+)", part or "")
    return int(m.group(1)) if m and "番外" not in (part or "") else None


def oa_tree(q):
    """置き場所 › カテゴリー › 連載 の一覧（件数・期間・残っていない回）。"""
    if not os.path.exists(BLOG_DB):
        return {"missing": True}
    con = blog_db()
    srcs = [dict(r) for r in con.execute("""SELECT s.id, s.label, s.prefix, COUNT(e.id) n, MIN(e.date) a, MAX(e.date) b
        FROM sources s JOIN entries e ON e.source = s.id GROUP BY s.id ORDER BY MIN(e.date)""")]
    rows = con.execute("""SELECT source, category, series,
        CASE WHEN COUNT(DISTINCT NULLIF(author,'')) > 1 THEN 'メンバー全員' ELSE COALESCE(MAX(NULLIF(author,'')),'-') END author, COUNT(*) n,
        MIN(date) a, MAX(date) b, SUM(approx) approx, GROUP_CONCAT(DISTINCT part) parts
        FROM entries GROUP BY source, category, series""").fetchall()
    con.close()
    by_src = {s["id"]: s for s in srcs}
    for s in srcs:
        s["categories"] = []
        s["ready"] = s["id"] in OA_READY
    for r in rows:
        nums = sorted({part_num(p) for p in (r["parts"] or "").split(",") if part_num(p) is not None})
        missing = [n for n in range(nums[0], nums[-1] + 1) if n not in set(nums)] if nums else []
        sample = next((p for p in (r["parts"] or "").split(",") if part_num(p) is not None), "")
        item = {"series": r["series"], "author": r["author"], "n": r["n"], "a": r["a"], "b": r["b"],
                "approx": bool(r["approx"] and r["approx"] == r["n"]), "parts": len(nums),
                "missing": [re.sub(r"\d+", str(n), sample, count=1) for n in missing]}
        cats = by_src[r["source"]]["categories"]
        cat = next((c for c in cats if c["name"] == r["category"]), None)
        if not cat:
            cat = {"name": r["category"], "series": []}
            cats.append(cat)
        cat["series"].append(item)
    for s in srcs:
        s["categories"].sort(key=lambda c: CATEGORY_ORDER.index(c["name"]) if c["name"] in CATEGORY_ORDER else 99)
        for c in s["categories"]:
            c["series"].sort(key=lambda x: x["a"] or "")
    con = blog_db()
    has_items = con.execute("SELECT name FROM sqlite_master WHERE name = 'items'").fetchone()
    counts = {k: n for k, n in con.execute("SELECT kind, COUNT(*) FROM items GROUP BY kind")} if has_items else {}
    con.close()
    collections_ = [{"kind": k, "label": v, "n": counts.get(k, 0)} for k, v in ITEM_KINDS.items() if counts.get(k)]
    return {"sources": srcs, "collections": collections_}


OA_COLS = "id, source, category, series, part, author, date, approx, title, heading, wayback_ts, url"


def oa_series(q):
    """1つの連載の目次（日付順）。"""
    con = blog_db()
    rows = con.execute(f"""SELECT {OA_COLS}, substr(body, 1, 90) head FROM entries
        WHERE source = ? AND series = ? ORDER BY date, id""", (first(q, "s"), first(q, "r"))).fetchall()
    con.close()
    return {"entries": [dict(r) for r in rows]}


def oa_doc(q):
    """1件の本文と、同じ連載の前後の記事。"""
    con = blog_db()
    e = con.execute(f"SELECT {OA_COLS}, body FROM entries WHERE id = ?", (first(q, "id"),)).fetchone()
    if not e:
        con.close()
        return {"doc": None}
    sib = [dict(r) for r in con.execute(f"""SELECT id, date, part, title FROM entries
        WHERE source = ? AND series = ? ORDER BY date, id""", (e["source"], e["series"]))]
    label = con.execute("SELECT label FROM sources WHERE id = ?", (e["source"],)).fetchone()
    con.close()
    i = next(k for k, s in enumerate(sib) if s["id"] == e["id"])
    return {"doc": dict(e), "source_label": label[0] if label else e["source"], "index": i, "count": len(sib),
            "prev": sib[i - 1] if i > 0 else None, "next": sib[i + 1] if i + 1 < len(sib) else None}


ITEM_KINDS = {"lyric": "歌詞", "setlist": "セットリスト", "release": "作品"}


def song_key(title):
    """build_blog_db.song_key と同じ（曲名の表記ゆれをならす）。"""
    import unicodedata
    t = unicodedata.normalize("NFKC", title or "").lower()
    t = re.sub(r"[(（\[【].*?[)）\]】]", "", t)
    t = t.replace("二", "2").replace("・", "").replace("’", "'")
    return re.sub(r"[\s\-_:!！?？☆.,、。'\"~〜]", "", t)


def _song_index(con):
    """曲名 → 歌詞の id、曲名 → 演奏した公演、曲名 → 収録作品。"""
    lyrics = {r["song_key"]: r["id"] for r in con.execute("SELECT id, song_key FROM items WHERE kind = 'lyric'")}
    plays, rels = collections.defaultdict(list), collections.defaultdict(list)
    for r in con.execute("SELECT id, kind, title, date, songs FROM items WHERE kind IN ('setlist','release') ORDER BY date"):
        for s in json.loads(r["songs"] or "[]"):
            k = song_key(s["title"])
            (plays if r["kind"] == "setlist" else rels)[k].append({"id": r["id"], "title": r["title"], "date": r["date"]})
    return lyrics, plays, rels


def oa_items(q):
    """まとめの一覧（歌詞・セットリスト・作品）。"""
    con = blog_db()
    kind = first(q, "kind")
    rows = [dict(r) for r in con.execute("""SELECT id, kind, title, sub, date, songs, song_key, source_entry
        FROM items WHERE kind = ? ORDER BY date, source_entry, position""", (kind,))]
    lyrics, plays, rels = _song_index(con)
    counts = {k: n for k, n in con.execute("SELECT kind, COUNT(*) FROM items GROUP BY kind")}
    con.close()
    for r in rows:
        songs = json.loads(r.pop("songs") or "[]")
        r["n_songs"] = len(songs)
        r["preview"] = [s["title"] for s in songs[:4]]
        if kind == "lyric":
            r["plays"] = len(plays.get(r["song_key"], []))
            r["releases"] = [x["title"] for x in rels.get(r["song_key"], [])]
            r["release_date"] = (rels.get(r["song_key"]) or [{"date": "9999"}])[0]["date"]
    return {"kind": kind, "label": ITEM_KINDS.get(kind, kind), "items": rows, "counts": counts}


def oa_item(q):
    """まとめの1件と、出典（元のページ）、曲ごとのつながり。"""
    con = blog_db()
    it = con.execute("SELECT * FROM items WHERE id = ?", (first(q, "id"),)).fetchone()
    if not it:
        con.close()
        return {"item": None}
    it = dict(it)
    src = con.execute("""SELECT e.id, e.series, e.category, e.url, e.wayback_ts, e.source, s.label FROM entries e
        LEFT JOIN sources s ON s.id = e.source WHERE e.id = ?""", (it["source_entry"],)).fetchone()
    sib = [r[0] for r in con.execute("SELECT id FROM items WHERE kind = ? ORDER BY date, source_entry, position", (it["kind"],))]
    lyrics, plays, rels = _song_index(con)
    con.close()
    songs = json.loads(it.pop("songs") or "[]")
    for s in songs:
        s["lyric"] = lyrics.get(song_key(s["title"]))
        s["plays"] = len(plays.get(song_key(s["title"]), []))
    i = sib.index(it["id"])
    out = {"item": it, "songs": songs, "source": dict(src) if src else None, "index": i, "count": len(sib),
           "prev": sib[i - 1] if i > 0 else None, "next": sib[i + 1] if i + 1 < len(sib) else None}
    if it["kind"] == "lyric":
        out["plays"] = plays.get(it["song_key"], [])
        out["releases"] = rels.get(it["song_key"], [])
    return out


def day_count(q):
    """日記の日付ごとに、同じ日の 5ch の書き込み数（「この日のスレを見る」用）。dates=2004-12-01,2004-12-02"""
    dates = [d for d in first(q, "dates").split(",") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)][:100]
    con = db()
    out = {}
    for d in dates:
        out[d] = con.execute("SELECT COUNT(*) FROM posts WHERE posted_at BETWEEN ? AND ?",
                             (d + " 00:00:00", d + " 23:59:59")).fetchone()[0]
    con.close()
    return {"counts": out}


ROUTES = {"/api/oa/items": oa_items, "/api/oa/item": oa_item, "/api/oa/tree": oa_tree, "/api/oa/series": oa_series, "/api/oa/doc": oa_doc, "/api/diary": diary, "/api/daycount": day_count, "/api/works": works, "/api/work": work, "/api/search": search, "/api/suggest": suggest, "/api/thread": thread, "/api/posts": some_posts,
          "/api/threads": lambda q: threads(), "/api/home": lambda q: home()}


class Handler(BaseHTTPRequestHandler):
    def send(self, body, ctype, status=200):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        try:
            if u.path == "/":
                self.send(open(PAGE, "rb").read(), "text/html; charset=utf-8")
            elif u.path in ROUTES:
                self.send(json.dumps(ROUTES[u.path](parse_qs(u.query)), ensure_ascii=False),
                          "application/json; charset=utf-8")
            else:
                self.send("not found", "text/plain; charset=utf-8", 404)
        except Exception as e:
            self.send(json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8", 500)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"http://127.0.0.1:{PORT}/ で検索画面を開けます（Ctrl+C で終了）", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
