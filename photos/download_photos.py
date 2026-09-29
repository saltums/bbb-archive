#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BBBアーカイブ イベント写真ダウンローダー

各イベントフォルダに _DONE ファイルがあればスキップ。
ダウンロード完了後に _DONE を自動生成。

使い方:
  python download_photos.py              # 全フォルダ処理
  python download_photos.py --dry-run    # 実行内容の確認のみ
"""
import os, sys, urllib.request, datetime

PHOTOS_DIR = os.path.dirname(os.path.abspath(__file__))
DONE_MARKER = "_DONE"

# イベントフォルダごとのダウンロード定義
# key: フォルダ名, value: [(url, 保存ファイル名), ...]
EVENTS = {
    "2026-09-04_SHIBUYA_NONFICTION_III": [
        # _DONE済み — ここを残しておいても自動スキップされる
        (
            "https://www.sma.co.jp/files/15/artist/169/28/_%E3%83%8E%E3%83%B3%E3%83%95%E3%82%A3%E3%82%AF%E3%82%B7%E3%83%A7%E3%83%B3%E3%83%A1%E3%82%A4%E3%83%B3%E3%83%93%E3%82%B8%E3%83%A5%E3%82%A2%E3%83%AB.jpg",
            "SMA_メインビジュアル.jpg"
        ),
        (
            "https://www.sma.co.jp/images/15/3fb/da503fa8142e8a12e5ba131da3b22-01.jpg",
            "SMA_追加ゲスト告知.jpg"
        ),
        (
            "https://eventernote.s3.amazonaws.com/images/events/464683.jpg",
            "Eventernote_イベント.jpg"
        ),
    ],
    # 今後のイベントはここに追加する
    # "2026-09-29_BIGMAMA_20th_Anniversary": [
    #     ("https://...", "ファイル名.jpg"),
    # ],
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DRY_RUN = "--dry-run" in sys.argv

def download(url, dest):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as res:
        data = res.read()
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)

def mark_done(folder_path, filenames):
    marker = os.path.join(folder_path, DONE_MARKER)
    with open(marker, "w", encoding="utf-8") as f:
        f.write(f"downloaded: {datetime.date.today()}\n")
        f.write("files: " + ", ".join(filenames) + "\n")

def main():
    for event_folder, photos in EVENTS.items():
        folder_path = os.path.join(PHOTOS_DIR, event_folder)
        done_path = os.path.join(folder_path, DONE_MARKER)

        if os.path.exists(done_path):
            print(f"[スキップ] {event_folder} (_DONE あり)")
            continue

        print(f"[処理] {event_folder}")
        if not os.path.exists(folder_path):
            if not DRY_RUN:
                os.makedirs(folder_path)
            print(f"  フォルダ作成: {folder_path}")

        saved = []
        for url, filename in photos:
            dest = os.path.join(folder_path, filename)
            if DRY_RUN:
                print(f"  [dry-run] {filename}")
                saved.append(filename)
                continue
            try:
                size = download(url, dest)
                print(f"  保存: {filename} ({size//1024}KB)")
                saved.append(filename)
            except Exception as e:
                print(f"  失敗: {filename} → {e}")

        if saved and not DRY_RUN:
            mark_done(folder_path, saved)
            print(f"  _DONE 作成")

    print("\n完了。")

if __name__ == "__main__":
    main()
