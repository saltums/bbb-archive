#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公式アーカイブ（取り戻した日記・ブログ・特設サイトと画像）を、本人だけが見る静的サイトとして書き出す。
出力は data/private-site/（公開リポジトリには入れない）。Cloudflare Pages ＋ Cloudflare Access（本人のメールでログイン）に置く。

  python scripts/build_private_site.py

  index.html              置き場所と、日記・ブログの年代順
  s/<置き場所>.html        カテゴリーと連載の一覧
  r/<置き場所>-<n>.html    1つの連載の目次（日付順）
  d/<記事id>.html          1件（本文の［画像］の位置に画像）
  o/<ページ>.html          元のページ（保存された HTML。画像は手元のコピーに、ほかのページへのリンクは手元の写しに差し替え）
  img/<画像id>.<拡張子>    画像
  search.html, search.json ことばで探す
"""
import collections, html, json, os, re, shutil, sqlite3, sys, urllib.parse

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bbb_images import IMG_DIR, OUT as ARCH, img_url  # noqa: E402
from build_blog_db import decode  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "data", "private-site")
RAW = os.path.join(ARCH, "raw")
DB = os.path.join(ARCH, "blogs.sqlite")

CATEGORY_ORDER = ["日記", "ブログ", "スタッフ", "メンバーのコーナー", "連載", "ラジオ", "歌詞", "お知らせ", "ライブ",
                  "ライブ・リリースの告知", "作品", "プロフィール", "メディア", "写真", "グッズ", "特設ページ", "トップページ", "その他"]
MEMBER = {"小出祐介": ("小出", "koide"), "関根史織": ("関根", "sekine"), "湯浅将平": ("湯浅", "yuasa"),
          "堀之内大介": ("堀之内", "hori"), "メンバー全員": ("メンバー全員", "all")}
WEEK = "月火水木金土日"
IMG_MARK = re.compile(r"[［\[]画像[］\]]")

CSS = """
:root{--bg:#f4f1ea;--panel:#fffdf8;--sunk:#ebe6db;--ink:#1d1b17;--dim:#5f5a50;--faint:#8f887b;--line:#ddd6c8;
--accent:#b4402a;--koide:#1f5fbf;--sekine:#c2417a;--yuasa:#2f8a4a;--hori:#c96a12;--all:#6b5bb5;--none:#7d8794}
@media (prefers-color-scheme:dark){:root{--bg:#14130f;--panel:#1c1a16;--sunk:#24221d;--ink:#ece7dc;--dim:#b1a998;--faint:#7f786b;
--line:#332f28;--accent:#f0795f;--koide:#79a9f5;--sekine:#f08cb7;--yuasa:#6fcf8d;--hori:#f2a65a;--all:#a99af0;--none:#9aa4b2;color-scheme:dark}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.75 "Hiragino Sans","Noto Sans JP","Yu Gothic UI",sans-serif}
a{color:inherit}a:hover{color:var(--accent)}
.wrap{max-width:60rem;margin:0 auto;padding:1.2rem max(16px,env(safe-area-inset-right)) 4rem max(16px,env(safe-area-inset-left))}
header.top{display:flex;gap:1rem;align-items:baseline;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:.7rem;margin-bottom:1.2rem}
header.top .brand{font-weight:800;letter-spacing:.04em;text-decoration:none;font-size:1.05rem}
header.top nav{display:flex;gap:1rem;font-size:.88rem;color:var(--dim)}
header.top nav a{text-decoration:none}
h1{font-size:1.5rem;line-height:1.45;margin:.2rem 0 .4rem;text-wrap:balance}
h2{font-size:1.02rem;margin:2rem 0 .6rem;padding-bottom:.3rem;border-bottom:1px solid var(--line)}
.crumbs{font-size:.8rem;color:var(--faint);display:flex;flex-wrap:wrap;gap:.2rem .5rem}
.crumbs a{text-decoration:none}.crumbs span:before{content:"›";margin-right:.5rem}
.meta{color:var(--dim);font-size:.85rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:.7rem}
.card{display:block;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.8rem .9rem;text-decoration:none}
.card b{display:block;line-height:1.4}.card small{color:var(--faint);font-size:.78rem}
.list{list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}
.list li{border-bottom:1px solid var(--line)}
.list a{display:grid;grid-template-columns:6.5rem 1fr;gap:.8rem;padding:.55rem .2rem;text-decoration:none}
.list .d{font-variant-numeric:tabular-nums;color:var(--dim);font-size:.85rem}
.list .t{min-width:0}.list .t small{display:block;color:var(--faint);font-size:.8rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.list .ic{font-size:.72rem;color:var(--faint);margin-left:.4rem}
.dot{display:inline-block;width:.55rem;height:.55rem;border-radius:50%;margin-right:.35rem;background:var(--c,var(--none))}
.reader{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--c,var(--line));border-radius:12px;padding:1.4rem clamp(1rem,4vw,2.4rem) 1.6rem}
.r-date{font-size:.9rem;color:var(--dim)}.r-date b{font-size:2rem;margin-right:.35rem;color:var(--ink);font-variant-numeric:tabular-nums}
.r-body{margin-top:1.2rem;white-space:pre-wrap;overflow-wrap:anywhere;font-size:1.03rem;line-height:2}
.r-foot{margin-top:1.4rem;padding-top:.8rem;border-top:1px dashed var(--line);font-size:.8rem;color:var(--faint);display:flex;flex-wrap:wrap;gap:.4rem 1.2rem}
.oa-img{display:inline-block;vertical-align:top;max-width:100%;margin:.3rem .4rem .3rem 0;line-height:0;border-radius:6px;overflow:hidden;box-shadow:0 0 0 1px var(--line)}
.oa-img img{display:block;max-width:100%;height:auto;max-height:min(70vh,32rem);width:auto}
.oa-img.small img{max-height:9rem}
.ph{display:inline-block;font-size:.78em;color:var(--faint);border:1px dashed var(--line);border-radius:4px;padding:0 .4em;line-height:1.6}
.pn{display:grid;grid-template-columns:1fr auto 1fr;gap:.6rem;margin-top:1rem;font-size:.85rem;align-items:center}
.pn a{text-decoration:none;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:.5rem .7rem;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pn .n{text-align:right}.pn .m{color:var(--faint)}
.tl{display:grid;gap:.25rem}
.tl a{display:grid;grid-template-columns:minmax(8rem,14rem) 1fr;gap:.6rem;align-items:center;text-decoration:none;font-size:.84rem}
.tl .bar{position:relative;height:.7rem;background:var(--sunk);border-radius:4px}
.tl .bar i{position:absolute;top:0;bottom:0;border-radius:4px;background:var(--c,var(--none))}
.tl .lab{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.axis{display:grid;grid-template-columns:minmax(8rem,14rem) 1fr;gap:.6rem;font-size:.72rem;color:var(--faint)}
.axis div{display:flex;justify-content:space-between}
.search{display:flex;gap:.5rem;margin:.6rem 0 1rem}
.search input{flex:1;min-width:0;font:inherit;padding:.55rem .8rem;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink)}
mark{background:color-mix(in srgb,var(--accent) 25%,transparent);color:inherit;border-radius:2px}
@media (max-width:560px){.list a{grid-template-columns:5.2rem 1fr}.tl a,.axis{grid-template-columns:7rem 1fr}}
"""


def esc(s):
    return html.escape(s or "", quote=True)


def page(title, body, depth=1, extra_head=""):
    up = "../" * depth
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow"><title>{esc(title)} — BBB 公式アーカイブ</title>
<link rel="stylesheet" href="{up}style.css">{extra_head}</head><body><div class="wrap">
<header class="top"><a class="brand" href="{up}index.html">BBB 公式アーカイブ</a>
<nav><a href="{up}index.html">置き場所</a><a href="{up}search.html">ことばで探す</a></nav></header>
{body}</div></body></html>"""


def write(rel, text):
    path = os.path.join(SITE, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8", newline="\n").write(text)


def jp_date(d, approx=False):
    y, mo, dd = (d.split("-") + ["", ""])[:3]
    import datetime
    try:
        wd = WEEK[datetime.date(int(y), int(mo), int(dd)).weekday()]
    except ValueError:
        wd = ""
    return y, int(mo or 0), int(dd or 0), wd


def color(author):
    return f"--{MEMBER.get(author, ('', 'none'))[1]}"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    if os.path.exists(SITE):
        for name in os.listdir(SITE):   # img/ は残して差分だけ写す（数百MB を毎回写し直さない）
            if name not in ("img", "a"):
                p = os.path.join(SITE, name)
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    os.makedirs(os.path.join(SITE, "img"), exist_ok=True)
    write("style.css", CSS.strip() + "\n")
    write("_headers", "/*\n  X-Robots-Tag: noindex, nofollow\n  Referrer-Policy: no-referrer\n")

    # ---- 画像 ----
    imgs = {}
    for r in con.execute("SELECT * FROM images"):
        imgs[r["id"]] = dict(r)
    by_sha_file = {}
    copied = 0
    for i, m in imgs.items():
        if not m["file"] or m["kind"] == "ui":
            continue
        src = os.path.join(IMG_DIR, m["file"])
        if not os.path.exists(src):
            continue
        ext = os.path.splitext(m["file"])[1].lower() or ".img"
        rel = f"img/{i}{ext}"
        dst = os.path.join(SITE, rel)
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)
            copied += 1
        m["rel"] = rel
        by_sha_file[m["url"]] = rel
    eimgs = collections.defaultdict(dict)
    for r in con.execute("SELECT entry_id, pos, image_id FROM entry_images"):
        eimgs[r[0]][r[1]] = imgs.get(r[2])

    def body_html(eid, body, up):
        at = eimgs.get(eid, {})
        k = [0]

        def rep(mk):
            x = at.get(k[0])
            k[0] += 1
            if not x:
                return '<span class="ph">［画像］</span>'
            if x["kind"] == "ui":
                return ""
            if not x.get("rel"):
                return '<span class="ph">［画像・保存なし］</span>' if x["status"] in (404, -1) else '<span class="ph">［画像］</span>'
            small = x["width"] and x["height"] and max(x["width"], x["height"]) < 200
            wh = f' width="{x["width"]}" height="{x["height"]}"' if x["width"] else ""
            return (f'<a class="oa-img{" small" if small else ""}" href="{up}{x["rel"]}"><img src="{up}{x["rel"]}" '
                    f'loading="lazy" alt=""{wh}></a>')
        out = IMG_MARK.sub(lambda m: rep(m), esc(body))
        out = re.sub(r'(</a>|<span class="ph">[^<]*</span>)[ \t　]*\n[\s　]*(?=<a class="oa-img|<span class="ph")', r"\1 ", out)
        return re.sub(r"\n{2,}(?=<a class=\"oa-img)", "\n", out)

    # ---- 元のページ（保存された HTML） ----
    man = json.load(open(os.path.join(ARCH, "manifest.json"), encoding="utf-8"))
    def norm(u):
        u = re.sub(r"^https?://", "", u or "")
        u = re.sub(r":80(?=/)", "", u)
        h, _, rest = u.partition("/")
        return (h.lower().removeprefix("www.") + "/" + rest).split("#")[0].rstrip("/")
    files = {}           # (url, ts) → raw のファイル
    latest = {}          # 正規化したURL → いちばん新しい raw のファイル
    for p in man["pages"].values():
        if p.get("file") and os.path.exists(os.path.join(RAW, p["file"])) and "epad" not in p["file"]:
            files[(p["url"], p["ts"])] = p["file"]
            k = norm(p["url"])
            if k not in latest or latest[k][0] < p["ts"]:
                latest[k] = (p["ts"], p["file"])
    def oname(f):
        return "o/" + re.sub(r"[^A-Za-z0-9._-]+", "_", f.replace("/", "__"))[:200].removesuffix(".html") + ".html"
    used_raw = set()
    entries = [dict(r) for r in con.execute("SELECT * FROM entries ORDER BY date, id")]
    for e in entries:
        f = files.get((e["page_url"], e["wayback_ts"]))
        e["raw"] = oname(f) if f else ""
        if f:
            used_raw.add(f)
    # CSS と背景画像（fetch_wayback_assets.py で取ったもの）。a/ に写し、CSS の中の参照も手元に向ける
    from fetch_wayback_assets import ASSETS, MANIFEST as ASSET_MAN, absolute
    assets = json.load(open(ASSET_MAN, encoding="utf-8")) if os.path.exists(ASSET_MAN) else {}
    asset_rel = {u: "a/" + r["file"] for u, r in assets.items() if r.get("file")}
    os.makedirs(os.path.join(SITE, "a"), exist_ok=True)
    for u, rel in asset_rel.items():
        data = open(os.path.join(ASSETS, assets[u]["file"]), "rb").read()
        if u.split("?")[0].endswith(".css") or "css" in (assets[u].get("type") or ""):
            text = data.decode("utf-8", "ignore")
            def css_ref(m, base=u):
                v = absolute(base, m.group(1))
                return f'url("{asset_rel[v][2:]}")' if v and v in asset_rel else "url()"
            text = re.sub(r"url\(([^)]+)\)", css_ref, text)
            text = re.sub(r'@import\s+["\']([^"\']+)["\']', lambda m, base=u: (
                f'@import "{asset_rel[absolute(base, m.group(1))][2:]}"' if absolute(base, m.group(1)) in asset_rel else ""), text)
            data = text.encode("utf-8")
        open(os.path.join(SITE, rel), "wb").write(data)
    img_by_url = {m["url"]: m.get("rel") for m in imgs.values() if m.get("rel")}
    img_by_url.update({m["thumb"]: m.get("rel") for m in imgs.values() if m.get("rel") and m.get("thumb")})
    raw_by_file = {f: (u, ts) for (u, ts), f in files.items()}
    n_raw = 0
    for f in sorted(used_raw):
        url, ts = raw_by_file[f]
        doc = decode(open(os.path.join(RAW, f), "rb").read())
        doc = re.sub(r"<script\b.*?</script>|<noscript\b.*?</noscript>|<iframe\b.*?</iframe>|<embed\b[^>]*>|<object\b.*?</object>",
                     "", doc, flags=re.S | re.I)
        doc = re.sub(r"<meta[^>]+charset[^>]*>", "", doc, flags=re.I)
        def link_rep(m):
            h = re.search(r'href\s*=\s*["\']?([^"\'\s>]+)', m.group(0), re.I)
            v = absolute(url, h.group(1)) if h else None
            return f'<link rel="stylesheet" href="../{asset_rel[v]}">' if v in asset_rel else ""
        doc = re.sub(r"<link\b[^>]*stylesheet[^>]*>", link_rep, doc, flags=re.I)

        def any_url(ref):
            v = absolute(url, ref)
            return ("../" + asset_rel[v]) if v in asset_rel else ("../" + img_by_url[v]) if v in img_by_url else ""
        doc = re.sub(r'(\sbackground\s*=\s*)["\']?([^"\'\s>]+)["\']?', lambda m: f'{m.group(1)}"{any_url(m.group(2))}"', doc, flags=re.I)
        doc = re.sub(r"url\(([^)]+)\)", lambda m: f'url("{any_url(m.group(1))}")', doc, flags=re.I)
        doc = re.sub(r'@import\s+["\']([^"\']+)["\']', lambda m: f'@import "{any_url(m.group(1))}"', doc, flags=re.I)

        def img_rep(m):
            u = img_url(url, html.unescape(m.group(2)))
            rel = img_by_url.get(u) if u else None
            return f'{m.group(1)}"../{rel}"' if rel else f'{m.group(1)}""'
        doc = re.sub(r'(<img\b[^>]*?\ssrc\s*=\s*)["\']?([^"\'\s>]+)["\']?', img_rep, doc, flags=re.I)

        def href_rep(m):
            target = html.unescape(m.group(2))
            if target.startswith(("#", "mailto:", "javascript:")):
                return m.group(0)
            u = urllib.parse.urljoin(url if re.match(r"https?://", url) else "http://" + url, target)
            hit = latest.get(norm(u))
            if hit and hit[1] in used_raw:
                return f'{m.group(1)}"../{oname(hit[1])}"'
            if absolute(url, target) in asset_rel:
                return f'{m.group(1)}"../{asset_rel[absolute(url, target)]}"'
            iu = img_url(url, target)
            if iu and img_by_url.get(iu):
                return f'{m.group(1)}"../{img_by_url[iu]}"'
            return f'{m.group(1)}"{html.escape(u)}" target="_blank" rel="noopener noreferrer"'
        doc = re.sub(r'(<a\b[^>]*?\shref\s*=\s*)["\']?([^"\'\s>]+)["\']?', href_rep, doc, flags=re.I)
        bar = (f'<div style="all:initial;display:block;font:13px/1.6 sans-serif;background:#1d1b17;color:#ece7dc;padding:6px 12px;'
               f'position:sticky;top:0;z-index:99999">保存された元のページ（{ts[:4]}.{ts[4:6]}.{ts[6:8]} 保存）'
               f'　<a href="../index.html" style="color:#f0b49f">公式アーカイブへ戻る</a>'
               f'<span style="opacity:.6">　画像とデザインは手元のコピー。取れなかった部分は当時と違って見えます</span></div>')
        head = '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">'
        if re.search(r"<head[^>]*>", doc, re.I):
            doc = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + head, doc, count=1, flags=re.I)
        else:
            doc = head + doc
        if re.search(r"<body[^>]*>", doc, re.I):
            doc = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + bar, doc, count=1, flags=re.I)
        else:
            doc = bar + doc
        write(oname(f), doc)
        n_raw += 1

    # ---- 置き場所・連載 ----
    sources = {r["id"]: dict(r) for r in con.execute("SELECT * FROM sources")}
    by_src = collections.defaultdict(list)
    for e in entries:
        by_src[e["source"]].append(e)
    series_file = {}
    series_list = collections.defaultdict(list)
    for sid, es in by_src.items():
        groups = collections.OrderedDict()
        for e in es:
            groups.setdefault((e["category"], e["series"]), []).append(e)
        for n, ((cat, ser), items) in enumerate(sorted(groups.items(), key=lambda kv: (
                CATEGORY_ORDER.index(kv[0][0]) if kv[0][0] in CATEGORY_ORDER else 99, kv[1][0]["date"])), 1):
            rel = f"r/{sid}-{n}.html"
            authors = {e["author"] for e in items if e["author"]}
            author = "メンバー全員" if len(authors) > 1 else (authors.pop() if authors else "")
            series_list[sid].append({"cat": cat, "ser": ser, "rel": rel, "items": items, "author": author})
            for e in items:
                series_file[e["id"]] = (rel, items)

    def src_label(sid):
        return (sources.get(sid) or {}).get("label", sid)

    # 1件
    for e in entries:
        rel, items = series_file[e["id"]]
        i = next(k for k, x in enumerate(items) if x["id"] == e["id"])
        prev, nxt = (items[i - 1] if i else None), (items[i + 1] if i + 1 < len(items) else None)
        y, mo, dd, wd = jp_date(e["date"])
        title = e["heading"] or e["title"] or e["series"]
        who = MEMBER.get(e["author"], (e["author"], ""))[0]
        saved = e["wayback_ts"] or ""
        nav_a = lambda x, label, cls: (f'<a class="{cls}" href="{x["id"]}.html">{label} {esc(x["date"].replace("-", "."))}'
                                       f'{"・" + esc(x["part"]) if x["part"] else ""}</a>') if x else "<span></span>"
        body = f"""<div class="crumbs"><a href="../index.html">公式アーカイブ</a><span><a href="../s/{e['source']}.html">{esc(src_label(e['source']))}</a></span>
<span>{esc(e['category'])}</span><span><a href="../{rel}">{esc(e['series'])}</a></span></div>
<article class="reader" style="--c:var({color(e['author'])});margin-top:.8rem">
<div class="r-date">{"保存された日 " if e["approx"] else ""}<b>{dd}</b>{y}年{mo}月（{wd}）{(" " + esc(e["time"])) if e["time"] else ""}</div>
<h1>{esc(title)}</h1>
<p class="meta">{esc(who) + "・" if who else ""}{esc(e['series'])}{"・" + esc(e['part']) if e['part'] else ""}{"・" + esc(e['title']) if e['title'] and e['heading'] else ""}</p>
<div class="r-body">{body_html(e['id'], e['body'], '../')}</div>
<div class="r-foot">{f"<span>Internet Archive {saved[:4]}.{saved[4:6]}.{saved[6:8]} 保存分</span>" if saved else ""}
{f'<a href="../{e["raw"]}">元のページを見る</a>' if e["raw"] else ""}<span>{esc(re.sub(r"^https?://", "", e["url"] or ""))}</span></div>
</article>
<div class="pn">{nav_a(prev, "←", "p")}<span class="m">{i + 1} / {len(items)}</span>{nav_a(nxt, "→", "n")}</div>"""
        write(f"d/{e['id']}.html", page(title, body))

    # 連載の目次
    for sid, sers in series_list.items():
        for s in sers:
            rows = []
            for e in s["items"]:
                n_img = sum(1 for x in eimgs.get(e["id"], {}).values() if x and x.get("rel") and x["kind"] != "ui")
                head = re.sub(r"\s+", " ", IMG_MARK.sub("", e["body"]))[:80]
                rows.append(f'<li><a href="../d/{e["id"]}.html"><span class="d">{esc(e["date"].replace("-", "."))}'
                            f'{"頃" if e["approx"] else ""}</span><span class="t"><span class="dot" style="--c:var({color(e["author"])})"></span>'
                            f'{esc(e["part"] + " " if e["part"] else "")}{esc(e["title"] or head[:30])}'
                            f'{f"<span class=ic>画像 {n_img}</span>" if n_img else ""}<small>{esc(head)}</small></span></a></li>')
            a, b = s["items"][0]["date"], s["items"][-1]["date"]
            body = f"""<div class="crumbs"><a href="../index.html">公式アーカイブ</a><span><a href="../s/{sid}.html">{esc(src_label(sid))}</a></span><span>{esc(s['cat'])}</span></div>
<h1>{esc(s['ser'])}</h1><p class="meta">{esc(MEMBER.get(s['author'], (s['author'], ''))[0] + "・" if s['author'] else "")}{len(s['items'])} 件・{a.replace('-', '.')} 〜 {b.replace('-', '.')}</p>
<ul class="list">{''.join(rows)}</ul>"""
            write(s["rel"], page(s["ser"], body))

    # 置き場所
    for sid, sers in series_list.items():
        cats = collections.OrderedDict()
        for s in sers:
            cats.setdefault(s["cat"], []).append(s)
        blocks = []
        for cat, ss in cats.items():
            cards = "".join(f'<a class="card" href="../{s["rel"]}"><b><span class="dot" style="--c:var({color(s["author"])})"></span>{esc(s["ser"])}</b>'
                            f'<small>{len(s["items"])} 件・{s["items"][0]["date"][:7].replace("-", ".")} 〜 {s["items"][-1]["date"][:7].replace("-", ".")}</small></a>'
                            for s in ss)
            blocks.append(f"<h2>{esc(cat)}</h2><div class=\"grid\">{cards}</div>")
        n = len(by_src[sid])
        body = f"""<div class="crumbs"><a href="../index.html">公式アーカイブ</a></div>
<h1>{esc(src_label(sid))}</h1><p class="meta">{n} 件・{esc((sources.get(sid) or {}).get('prefix', ''))}</p>{''.join(blocks)}"""
        write(f"s/{sid}.html", page(src_label(sid), body))

    # トップ: 置き場所と、日記・ブログの年代順
    order = sorted(by_src, key=lambda s: by_src[s][0]["date"])
    cards = "".join(f'<a class="card" href="s/{sid}.html"><b>{esc(src_label(sid))}</b>'
                    f'<small>{len(by_src[sid])} 件・{by_src[sid][0]["date"][:4]} 〜 {by_src[sid][-1]["date"][:4]}</small></a>' for sid in order)
    diaries = [s for sid in series_list for s in series_list[sid] if s["cat"] in ("日記", "ブログ", "スタッフ", "ラジオ") and len(s["items"]) >= 3]
    diaries.sort(key=lambda s: s["items"][0]["date"])
    y0 = min(int(s["items"][0]["date"][:4]) for s in diaries)
    y1 = max(int(s["items"][-1]["date"][:4]) for s in diaries) + 1
    span = (y1 - y0) * 12

    def pos(d):
        return ((int(d[:4]) - y0) * 12 + int(d[5:7]) - 1) / span * 100
    tl = "".join(f'<a href="{s["rel"]}" title="{esc(s["ser"])} {len(s["items"])} 件"><span class="lab"><span class="dot" style="--c:var({color(s["author"])})"></span>{esc(s["ser"])}</span>'
                 f'<span class="bar"><i style="--c:var({color(s["author"])});left:{pos(s["items"][0]["date"]):.2f}%;width:max(4px,{pos(s["items"][-1]["date"]) - pos(s["items"][0]["date"]):.2f}%)"></i></span></a>'
                 for s in diaries)
    n_img = sum(1 for m in imgs.values() if m.get("rel"))
    body = f"""<h1>Base Ball Bear 公式アーカイブ</h1>
<p class="meta">公式に出た日記・ブログ・お知らせ・特設サイトを、Internet Archive の保存から取り戻したもの。記事 {len(entries):,} 件・画像 {n_img:,} 枚・元のページ {n_raw:,}。本人だけが見る非公開の写しです。</p>
<h2>日記・ブログを年代順に</h2><div class="axis"><span></span><div><span>{y0}</span><span>{(y0 + y1) // 2}</span><span>{y1 - 1}</span></div></div><div class="tl">{tl}</div>
<h2>置き場所</h2><div class="grid">{cards}</div>"""
    write("index.html", page("公式アーカイブ", body, depth=0).replace('href="../', 'href="'))

    # ことばで探す
    idx = [[e["id"], e["date"], e["source"], e["series"], e["title"] or "", IMG_MARK.sub("", e["body"])] for e in entries]
    write("search.json", json.dumps(idx, ensure_ascii=False, separators=(",", ":")))
    labels = json.dumps({sid: src_label(sid) for sid in sources}, ensure_ascii=False)
    js = """<script>
const LABEL=%s;let DATA=null;const $=(s)=>document.querySelector(s);
const esc=(s)=>s.replace(/[&<>"]/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function run(){const q=$("#q").value.trim();history.replaceState(null,"","#"+encodeURIComponent(q));
 if(!q){$("#out").innerHTML="";$("#n").textContent="";return}
 if(!DATA){$("#n").textContent="読み込み中…";DATA=await (await fetch("search.json")).json()}
 const ts=q.split(/[\\s　]+/).filter(Boolean);const hit=DATA.filter((r)=>ts.every((t)=>r[4].includes(t)||r[5].includes(t)||r[3].includes(t)));
 $("#n").textContent=hit.length+" 件";
 const re=new RegExp(ts.map((t)=>t.replace(/[.*+?^${}()|[\\]\\\\]/g,"\\\\$&")).join("|"),"g");
 $("#out").innerHTML=hit.slice(0,300).map((r)=>{const i=Math.max(0,r[5].search(re));const s=r[5].slice(Math.max(0,i-40),i+90).replace(/\\s+/g," ");
  return `<li><a href="d/${r[0]}.html"><span class="d">${r[1].replace(/-/g,".")}</span><span class="t">${esc(r[4]||r[3])}<small>${esc(LABEL[r[2]]||r[2])}・${esc(r[3])}</small><small>${esc(s).replace(re,(m)=>"<mark>"+m+"</mark>")}</small></span></a></li>`}).join("")
  +(hit.length>300?`<li class="meta" style="padding:.6rem">ほか ${hit.length-300} 件。ことばを足して絞ってください</li>`:"")}
let t;$("#q").addEventListener("input",()=>{clearTimeout(t);t=setTimeout(run,250)});
if(location.hash.length>1){$("#q").value=decodeURIComponent(location.hash.slice(1));run()}
</script>""" % labels
    body = f"""<h1>ことばで探す</h1><p class="meta">題・本文・連載の名前から探します（空白で区切ると、全部を含む記事）。</p>
<div class="search"><input id="q" type="search" placeholder="例: つよがり少女" autofocus></div><p class="meta" id="n"></p><ul class="list" id="out"></ul>{js}"""
    write("search.html", page("ことばで探す", body, depth=0).replace('href="../', 'href="'))
    con.close()
    total = sum(len(fs) for _, _, fs in os.walk(SITE))
    print(f"書き出し: 記事 {len(entries)} / 元のページ {n_raw} / 画像 {n_img}（今回写した {copied}）/ ファイル {total} → {SITE}")


if __name__ == "__main__":
    main()
