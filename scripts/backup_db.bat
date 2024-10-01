@echo off

for /f "usebackq delims=" %%i in (`
  PowerShell -Command "get-date" -format "yyyy-MM-dd_HHmmss"
`) do set _timestamp=%%i

cd "C:/Program Files/PostgreSQL/16/bin"
pg_dump -U postgres runeclock > Z:/RuneClock/Backups/backup_%_timestamp%.sql