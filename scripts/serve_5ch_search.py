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


ROUTES = {"/api/search": search, "/api/suggest": suggest, "/api/thread": thread, "/api/posts": some_posts,
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
