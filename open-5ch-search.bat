@echo off
rem 5ch archive search (local only). Close this window to stop.
cd /d "%~dp0"
start "" http://127.0.0.1:8770/
python scripts\serve_5ch_search.py 8770
