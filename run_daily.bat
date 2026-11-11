@echo off
rem Run by Windows Task Scheduler every morning.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
call .venv\Scripts\activate.bat
python run.py >> logs\daily.log 2>&1
