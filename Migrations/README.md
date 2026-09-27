# Database migrations

This directory is the authoritative, forward-only schema history for the
application. Do not use `db.create_all()` for a persistent deployment.

For a new or existing local database:

```powershell
$env:APP_ENV = "development"
flask --app app.py db upgrade
```

The initial revision is deliberately non-destructive. It snapshots the current
tables, columns, foreign keys, indexes, and unique constraints, then adds only
the legacy columns and indexes that earlier releases introduced outside
Alembic. It does not drop tables or delete data. A legacy database with
duplicate migration-file object rows cannot receive the corresponding unique
index automatically; resolve those duplicates deliberately before retrying the
upgrade.

SQLite is suitable for local development and single-process demos. Use a
server database and a shared worker/session design before multi-worker
production deployment.
