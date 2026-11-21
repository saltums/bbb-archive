# -*- coding: utf-8 -*-
"""公式アーカイブの画像の共通部分（どの画像を取るか・置き場所の決め方）。
build_blog_db.py / fetch_wayback_images.py / sync_images_pcloud.py から使う。"""
import os, re, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "blog-archive")
IMG_DIR = os.path.join(OUT, "images")
IMG_MANIFEST = os.path.join(OUT, "images.json")
PCLOUD_ROOT = "/BaseBallBear-Archive/images"

# 取らない画像
# - seesaa の画像サーバー（*.up.seesaa.net）は robots.txt で Claude を禁止している
# - 事務所 sma.co.jp は robots.txt で Claude を全面禁止
# - 広告・計測・通販・動画サイトのサムネイル・ブログサービスの飾り
SKIP = re.compile(
    r"up(\.[a-z])?\.seesaa\.net|blog\.seesaa\.jp|sma\.co\.jp|"
    r"amazon|images-amazon|valuecommerce|ytimg\.com|px\.srvcs\.tumblr|assets\.tumblr|static\.tumblr|"
    r"parts\.blog\.livedoor|livedoor\.com/(img|parts)|counter|access|analytics|doubleclick|googlesyndication|"
    r"facebook|twitter|twimg|addthis|hatena|mixi|line\.me|"
    r"spacer|space\.gif|blank\.gif|clear\.gif|dot\.gif|1x1|pixel", re.I)


def img_url(page_url, src):
    """記事のページのURLと img の src から、元の画像のURL（web.archive.org を外したもの）。取らない画像は None。"""
    src = src.strip()
    if not src or src.startswith(("data:", "javascript:", "about:")):
        return None
    src = re.sub(r"^(https?:)?//web\.archive\.org/web/\d+[a-z_]*/", "", src)
    src = re.sub(r"^/web/\d+[a-z_]*/", "", src)
    base = page_url if re.match(r"https?://", page_url) else "http://" + page_url
    u = urllib.parse.urljoin(base, src)
    u = re.sub(r"^https?://", "http://", u)
    u = re.sub(r":80(?=/)", "", u).split("#")[0]
    if not re.match(r"http://[^/]+\.[^/]+/", u) or SKIP.search(u):
        return None
    if not re.search(r"\.(jpe?g|gif|png|webp|bmp)(\?|$)|/image/|/img/|photo|images", u, re.I):
        return None
    return u


def local_name(source, url):
    """手元の保存先（images/<置き場所>/<ホストとパスを1つの名前にしたもの>）。"""
    path = re.sub(r"^http://", "", url)
    stem, ext = os.path.splitext(path.split("?")[0])
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)[-150:] + (re.sub(r"[^a-z0-9.]", "", ext.lower())[:6] or ".img")
    if "?" in path:
        import hashlib
        name = hashlib.sha1(path.encode()).hexdigest()[:8] + "_" + name
    return f"{source}/{name}"
