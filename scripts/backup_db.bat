cd "C:/Program Files/PostgreSQL/15/bin"
pg_dump -U postgres gino > %~dp0/../data/backup.sql