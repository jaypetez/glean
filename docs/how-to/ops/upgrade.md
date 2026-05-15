---
title: "How to upgrade glean - glean"
description: "Pull a new image, run migrations, verify, and roll back if needed."
---

# Upgrade glean

**Goal:** Move a production deployment to a newer image, apply state migrations, and keep a rollback path.

**You need:**

- A recent [state backup](backup.md).
- Shell access to the Docker host.
- The target image tag or digest.
- A maintenance window if feeds must not run during the change.

## Steps

1. Record the current version and image tag.

   ```bash
   docker compose exec glean glean version
   docker compose images glean
   ```

2. Back up state before changing the image.

   ```bash
   mkdir -p backup
   sqlite3 ./data/state.db ".backup ./backup/state-before-upgrade.db.bak"
   ```

   The `sqlite3` command runs on the host against the bind-mounted database; the `glean` runtime image may not include the SQLite CLI.

3. Set the target image tag in your Compose file or `.env`, then pull it.

   ```bash
   docker compose pull glean
   ```

4. Stop the running container and apply migrations with the new image.

   ```bash
   docker compose stop glean
   docker compose run --rm glean migrate --db /data/state.db
   ```

   Schema migrations are also applied on startup, but running `glean migrate` first makes migration failures visible before the daemon resumes scheduled work. See the [CLI reference](../../reference/cli.md) for command options. Keep per-version notes under `docs/migration/` when a release needs extra operator steps. Add `--no-deps` if your Compose project would otherwise start unrelated dependencies for the one-shot migration.

5. Start the upgraded service.

   ```bash
   docker compose up -d glean
   ```

6. Roll back only with the matching pre-upgrade backup.

   ```bash
   docker compose down
   rm -f data/state.db-wal data/state.db-shm
   cp backup/state-before-upgrade.db.bak data/state.db
   chmod 600 data/state.db
   # Revert your Compose image tag to the previous version before pulling.
   docker compose pull glean
   docker compose up -d glean
   ```

   Do not point an older image at a database that was migrated by a newer release unless that release explicitly documents downgrade support.

## Verify

Run:

```bash
docker compose exec glean glean version
docker compose exec glean glean list-feeds
curl -fsS http://127.0.0.1:9090/healthz
```

Expected output includes the target version, normal feed output, and `"status":"ok"` from `/healthz`.

## Next steps

- Watch logs for one full scheduler interval after the upgrade.
- Keep the pre-upgrade backup until the new version has completed normal feed runs.
- Review release notes and per-version migration notes before the next upgrade.
