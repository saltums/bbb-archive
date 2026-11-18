@echo off
rem Fetch new posts of the current thread (and a next thread if one was started), then rebuild the search database.
cd /d "%~dp0"
python scripts\fetch_5ch_archive.py --refresh-latest
python scripts\build_5ch_db.py
pause
