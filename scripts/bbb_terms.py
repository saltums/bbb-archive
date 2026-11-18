#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""投稿の本文から「ことば」を取り出す部品（関連ワード用）。

形態素解析は使わない。曲名・作品名・メンバー名は辞書で拾い、それ以外は
カタカナ・漢字・英字のかたまりを1語として数える。
"""
import json, os, re, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

URL = re.compile(r"h?ttps?://\S+")
ANCHOR = re.compile(r">>\d+(?:-\d+)?")
TOKEN = re.compile(r"[ァ-ヴ][ァ-ヴー]+|[一-龥々〆]{2,8}|[A-Za-z][A-Za-z0-9]{2,}")

MEMBERS = ["小出祐介", "小出", "こいちゃん", "関根史織", "関根", "関根嬢", "堀之内大介", "堀之内", "ホリ",
           "湯浅将平", "湯浅"]

# どの話題にも出てくるので、関連ワードとしては役に立たない語
STOP = set("""
今日 昨日 明日 今年 去年 来年 今回 前回 次回 最近 最初 最後 自分 本当 普通 感じ 意味 以外 場合 全部 一番 結局
何か 誰か 時間 時代 今更 今後 以上 以下 以前 以降 正直 実際 絶対 多分 一応 一緒 全然 結構 相当 大分 微妙
名無 無名 意見 理由 問題 必要 気持 個人的 個人 的 思 言 見 聞 行 出 来 方 人 事 物 中 前 後 上 下 時
http https www com jpg png html the and for you that this with are was not but have from they all can
base ball bear baseballbear ベボベ スレ レス
""".split())


def norm(text):
    """全角英数・半角カナをそろえ、英字は小文字にする。"""
    return unicodedata.normalize("NFKC", text).lower()


def _clean_title(title):
    t = re.sub(r"\s*feat\..*$", "", title, flags=re.I)
    t = re.sub(r"\s*[（(](?:live|album|last)[^）)]*[）)]\s*$", "", t, flags=re.I)
    t = re.sub(r"\s*part\.?\s*\d+\s*$", "", t, flags=re.I)
    return t.strip()


def load_dictionary():
    """{正規化した語: (表示用の語, 種類)}。種類は song / album / member。"""
    words = {}
    path = os.path.join(ROOT, "data", "songs.json")
    releases = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    for r in releases:
        for part in r.get("album_title", "").split(" / "):
            t = _clean_title(part)
            if len(norm(t)) >= 2:
                words.setdefault(norm(t), (t, "album" if r.get("type") in ("album", "mini", "indie", "ep") else "song"))
    for r in releases:
        for tr in r.get("tracks", []):
            t = _clean_title(tr["title"] if isinstance(tr, dict) else tr)
            if len(norm(t)) >= 2 and words.get(norm(t), ("", "song"))[1] != "album":
                words[norm(t)] = (t, "song")
    for m in MEMBERS:
        words[norm(m)] = (m, "member")
    return words


class Extractor:
    def __init__(self):
        self.dictionary = load_dictionary()
        keys = sorted(self.dictionary, key=len, reverse=True)
        ascii_keys = [k for k in keys if k.isascii()]
        other_keys = [k for k in keys if not k.isascii()]
        # 英字だけの題名（c2、park など）は、ほかの単語の一部に反応しないよう前後を区切る
        self._ascii = re.compile(r"(?<![a-z0-9])(?:" + "|".join(map(re.escape, ascii_keys)) + r")(?![a-z0-9])") if ascii_keys else None
        self._other = re.compile("|".join(map(re.escape, other_keys))) if other_keys else None

    def terms(self, body):
        """本文に出てくる語の集合 {正規化した語: 表示用の語}。同じ語は1投稿で1回だけ数える。"""
        text = ANCHOR.sub(" ", URL.sub(" ", unicodedata.normalize("NFKC", body)))
        low = text.lower()
        found = {}
        spans = []
        for rx in (self._other, self._ascii):
            if rx:
                for m in rx.finditer(low):
                    found[m.group(0)] = self.dictionary[m.group(0)][0]
                    spans.append(m.span())
        same_length = len(low) == len(text)
        for m in TOKEN.finditer(text):
            surface = m.group(0)
            key = surface.lower()
            if key in found or key in STOP or re.fullmatch(r"w+", key):  # 「www」は笑いの表現なので数えない
                continue
            # 曲名の一部（「GIRL FRIEND」の GIRL など）は別の語として数えない
            if same_length and any(a < m.end() and m.start() < b for a, b in spans):
                continue
            found[key] = surface
        return found
