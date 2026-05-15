---
title: "How to reset one feed - glean"
description: "Clear one feed state, reset bootstrap, or run one off-schedule send."
---

# Reset one feed

**Goal:** Make one feed reprocess items or run immediately without deleting all `glean` state.

**You need:**

- The feed name from `feeds.yaml`.
- Shell access to the Docker host.
- A recent backup if you plan to edit SQLite state.
- `sqlite3` available on the host for direct state edits.

## Steps

1. Choose the least disruptive reset.

   - Delete state rows when the feed is stuck on old `seen_items` data.
   - Remove and re-add the feed when you want to treat it as new configuration.
   - Run `send-now` when you only need one off-schedule delivery.

2. Approach A: delete `seen_items` rows for that feed.

   ```bash
   sqlite3 ./data/state.db \
     "DELETE FROM seen_items WHERE feed='<feed-name>';"
   ```

   This keeps the feed's run history but lets already-seen items be considered new again. To force first-run bootstrap behavior too, also clear the feed row:

   ```bash
   sqlite3 ./data/state.db \
     "DELETE FROM feed_runs WHERE feed='<feed-name>';"
   ```

   Replace `./data/state.db` if your host bind mount uses a different path.

3. Approach B: delete the feed from `feeds.yaml`, then re-add it.

   ```bash
   # Edit feeds.yaml and remove the feed block, then restart.
   docker compose restart glean
   # Add the feed block back and restart again.
   docker compose restart glean
   ```

   Feed bootstrap state is keyed by feed name. Re-add with a new feed name to start clean. If you must keep the same name, clear the `feed_runs` row in Approach A before re-adding it.

4. Approach C: run one off-schedule send.

   ```bash
   docker compose exec glean glean send-now <feed-name>
   ```

   Use this when the schedule is correct but you do not want to wait for the next tick.

## Verify

Run:

```bash
docker compose exec glean glean list-feeds
docker compose logs --tail=100 glean
```

Expected output shows the feed in `list-feeds`. After Approach A, expect a bootstrap or delivery; after Approach C alone, expect a normal off-schedule run.

## Next steps

- If the reset fixed a source bug, keep the SQL command in your incident notes.
- If the feed still reports no items, run `glean test-feed <feed-name>` to inspect fetch counts without sending.
- Use [backups](backup.md) before making broad state changes.
