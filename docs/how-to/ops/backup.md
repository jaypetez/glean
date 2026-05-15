---
title: "How to back up and restore state - glean"
description: "Back up SQLite online, snapshot the data volume, and restore safely."
---

# Back up and restore state

**Goal:** Create restorable backups of the SQLite state database and the `/data/` volume without corrupting a running `glean` deployment.

**You need:**

- Shell access to the Docker host.
- A mounted data directory, usually `./data:/data`.
- A backup destination with enough free space.
- `sqlite3` available on the host. The runtime container is intentionally minimal and may not include the SQLite CLI.

## Steps

1. Confirm the host paths for your data and backup directories.

   ```yaml
   services:
     glean:
       volumes:
         - ./data:/data
         - ./backup:/backup
   ```

2. Run an online SQLite backup from the host while `glean` is running.

   ```bash
   mkdir -p backup
   sqlite3 ./data/state.db ".backup ./backup/state.db.bak"
   ```

   If your host mounts are `/data` and `/backup`, the same operation is:

   ```bash
   sqlite3 /data/state.db ".backup /backup/state.db.bak"
   ```

   The SQLite `.backup` command is safe for an online database and works with WAL mode.

3. Create a full `/data/` snapshot when you can afford a short stop.

   ```bash
   docker compose down
   mkdir -p backup
   tar -czf backup/glean-data-$(date +%Y%m%d-%H%M).tgz data
   docker compose up -d
   ```

   Stopping first keeps `state.db`, WAL files, `api_key`, and any future data files consistent as a set.

4. Restore an online database backup.

   ```bash
   docker compose down
   rm -f data/state.db-wal data/state.db-shm
   cp backup/state.db.bak data/state.db
   chmod 600 data/state.db
   docker compose run --rm glean migrate --db /data/state.db
   docker compose up -d
   ```

   Removing stale WAL sidecar files prevents old pages from being replayed over the restored database.

5. Restore a full volume snapshot.

   ```bash
   docker compose down
   mv data data.before-restore
   tar -xzf backup/glean-data-20240101-0300.tgz
   chmod 700 data
   chmod 600 data/api_key data/state.db
   docker compose up -d
   ```

6. Add a cron job for daily online backups.

   ```cron
   15 3 * * * cd /opt/glean && mkdir -p backup && sqlite3 ./data/state.db ".backup ./backup/state-$(date +\%Y\%m\%d-\%H\%M).db.bak"
   ```

## Verify

Run:

```bash
sqlite3 backup/state.db.bak "PRAGMA integrity_check;"
docker compose exec glean glean list-feeds
curl -fsS http://127.0.0.1:9090/healthz
```

Expected output includes `ok` from `PRAGMA integrity_check`, normal feed output, and `"status":"ok"` from `/healthz`.

## Next steps

- Keep daily backups for at least 7 days and weekly backups for 4 to 8 weeks.
- Copy backups off-host so a disk failure does not remove the app and its restore point.
- Take a fresh backup before every [upgrade](upgrade.md) and API key rotation.
