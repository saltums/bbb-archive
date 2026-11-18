@echo off
chcp 65001 >nul
rem Fetch new posts of the current thread (and a next thread if one was started), then rebuild the search database.
cd /d "%~dp0"
python scripts\fetch_5ch_archive.py --refresh-latest
python scripts\build_5ch_db.py

rem Back up the raw data to the private repository (saltums/bbb-5ch-archive), if it is set up here.
if exist data\5ch-archive\.git (
  git -C data\5ch-archive add -A
  git -C data\5ch-archive commit -q -m "update %date%"
  git -C data\5ch-archive push -q
)
pause
