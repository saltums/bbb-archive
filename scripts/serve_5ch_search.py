#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5ch アーカイブの検索画面を手元だけで開く（127.0.0.1 のみ、外には出さない）。

  python scripts/serve_5ch_search.py [ポート]
"""
import json, os, re, sqlite3, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "5ch-archive", "bbb5ch.sqlite")
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "5ch_search.html")
PORT = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8770))
sys.stdout.reconfigure(encoding="utf-8")
PAGE_SIZE = 50


def db():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def like_escape(term):
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(q):
    terms = [t for t in re.split(r"[\s　]+", q.get("q", [""])[0].strip()) if t]
    where, args = ["1=1"], []
    kind = q.get("kind", [""])[0].strip()
    if kind in ("main", "related", "other"):
        where.append("t.kind = ?")
        args.append(kind)
    # 3文字以上の語は全文検索の索引、2文字以下（「小出」「野音」など）は総当たりで探す
    long_terms = [t for t in terms if len(t) >= 3]
    short_terms = [t for t in terms if len(t) < 3]
    if long_terms:
        match = " AND ".join('"' + t.replace('"', '""') + '"' for t in long_terms)
        where.append("p.id IN (SELECT rowid FROM posts_fts WHERE posts_fts MATCH ?)")
        args.append(match)
    for t in short_terms:
        where.append("p.body LIKE ? ESCAPE '\\'")
        args.append("%" + like_escape(t) + "%")
    for name, col, op in (("from", "p.posted_at", ">="), ("to", "p.posted_at", "<=")):
        v = q.get(name, [""])[0].strip()
        if v:
            where.append(f"{col} {op} ?")
            args.append(v + (" 00:00:00" if op == ">=" else " 23:59:59"))
    if q.get("nodate", [""])[0]:
        where.append("p.posted_at IS NULL")
    for name, col in (("thread", "p.thread_key"), ("uid", "p.uid")):
        v = q.get(name, [""])[0].strip()
        if v:
            where.append(f"{col} = ?")
            args.append(v)
    order = "p.posted_at ASC, p.id ASC" if q.get("order", ["new"])[0] == "old" else "p.posted_at DESC, p.id DESC"
    page = max(1, int(q.get("page", ["1"])[0] or 1))
    cond = " AND ".join(where)
    con = db()
    total = con.execute(f"SELECT COUNT(*) FROM posts p JOIN threads t ON t.key=p.thread_key WHERE {cond}", args).fetchone()[0]
    rows = con.execute(
        f"""SELECT p.thread_key, p.no, p.name, p.mail, p.date_raw, p.posted_at, p.uid, p.body, t.title, t.vol, t.kind, t.board
            FROM posts p JOIN threads t ON t.key=p.thread_key
            WHERE {cond} ORDER BY {order} LIMIT ? OFFSET ?""",
        args + [PAGE_SIZE, (page - 1) * PAGE_SIZE]).fetchall()
    years = con.execute(
        f"""SELECT substr(p.posted_at,1,4) y, COUNT(*) n FROM posts p JOIN threads t ON t.key=p.thread_key
            WHERE {cond} AND p.posted_at IS NOT NULL GROUP BY y ORDER BY y""", args).fetchall()
    nodate = con.execute(
        f"""SELECT COUNT(*) FROM posts p JOIN threads t ON t.key=p.thread_key
            WHERE {cond} AND p.posted_at IS NULL""", args).fetchone()[0]
    con.close()
    return {"total": total, "page": page, "page_size": PAGE_SIZE, "terms": terms, "nodate": nodate,
            "posts": [dict(r) for r in rows], "years": [[r["y"], r["n"]] for r in years]}


def threads():
    con = db()
    rows = con.execute("""SELECT key, board, title, vol, kind, source, post_count, first_at, last_at
                          FROM threads ORDER BY first_at DESC""").fetchall()
    stats = con.execute("""SELECT (SELECT COUNT(*) FROM posts) n, (SELECT MIN(first_at) FROM threads) a,
                                  (SELECT MAX(posted_at) FROM posts) b""").fetchone()
    con.close()
    return {"threads": [dict(r) for r in rows], "posts": stats["n"], "first": stats["a"], "last": stats["b"]}


def thread(key):
    con = db()
    t = con.execute("SELECT * FROM threads WHERE key = ?", (key,)).fetchone()
    rows = con.execute("SELECT no, name, mail, date_raw, posted_at, uid, body FROM posts WHERE thread_key = ? ORDER BY no", (key,)).fetchall()
    con.close()
    return {"thread": dict(t) if t else None, "posts": [dict(r) for r in rows]}


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
        q = parse_qs(u.query)
        try:
            if u.path == "/":
                self.send(open(PAGE, "rb").read(), "text/html; charset=utf-8")
            elif u.path == "/api/search":
                self.send(json.dumps(search(q), ensure_ascii=False), "application/json; charset=utf-8")
            elif u.path == "/api/threads":
                self.send(json.dumps(threads(), ensure_ascii=False), "application/json; charset=utf-8")
            elif u.path == "/api/thread":
                self.send(json.dumps(thread(q.get("key", [""])[0]), ensure_ascii=False), "application/json; charset=utf-8")
            else:
                self.send("not found", "text/plain; charset=utf-8", 404)
        except Exception as e:
            self.send(json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8", 500)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"http://127.0.0.1:{PORT}/ で検索画面を開けます（Ctrl+C で終了）", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
