@echo off
REM ATLAS daily data job — ingest the latest available B3 trading day.
REM Schedule once (run as the user, ~20:00 on weekdays):
REM   schtasks /Create /TN "ATLAS daily" /TR "%~f0" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 20:00
REM Remove with:  schtasks /Delete /TN "ATLAS daily" /F

cd /d "%~dp0\.."
set "PYTHONPATH=apps\api"
"apps\api\.venv\Scripts\python.exe" -m atlas_api.cli update --db "data_cache\atlas.db"
