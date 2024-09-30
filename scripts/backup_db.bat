cd "C:/Program Files/PostgreSQL/16/bin"
pg_dump -U postgres runeclock > %~dp0/../data/backup.sql