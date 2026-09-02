# ZKTeco Attendance Scrapper — Project Guide

This file orients AI agents (and humans) working in this repo. Read it before
making changes.

## What this project does

Pulls attendance punch records from **ZKTeco fingerprint/face terminals**
(the target device is a ZKTeco F18, but the code is generic ZKTeco over the
`pyzk` protocol) and stores them in a **Neon-hosted PostgreSQL** database.
A small Flask app provides a read-only web UI over the collected data.

There are two independent pieces:

1. **`collector.py`** — the always-running background worker. This is the
   core of the project.
2. **`app.py`** — an optional Flask dashboard for browsing/exporting what
   the collector has stored. The user has said this UI will likely be
   rewritten/replaced later; don't over-invest in it without asking.

## Collector lifecycle (the important part)

`collector.py` is a multi-device daemon (`python collector.py`). Per device it:

1. **Connects** over TCP to the device (`ip:port`, via `pyzk`'s `ZK` class).
2. **Reads device metadata**: firmware, serial number, device name, platform,
   and the full user list (`user_id -> name` map) — `get_device_information()`.
3. **Full sync** (`full_sync()`): pulls *all* attendance logs currently on the
   device (`conn.get_attendance()`), converts each into a DB row
   (`prepare_record()`), and bulk-inserts them. Deduplication happens in
   Postgres via `ON CONFLICT ... DO NOTHING` on a composite unique
   constraint — so "check if already in DB" is not a separate pre-check step,
   it's implicit in the insert (see Database section below).
4. **Live monitor** (`live_monitor()`): after the full sync, it calls
   `conn.live_capture()` (a blocking generator from `pyzk`) on a background
   thread and pushes events into a `queue.Queue`. The main loop drains that
   queue and saves each new punch immediately via `save_live_record()`.
5. **Safety re-sync**: if no live event arrives for `SAFETY_SYNC_MINUTES`
   (currently 45 min, see the `# TODO`-ish comment in the file — it was set
   to 1 min for testing at some point, confirm before relying on it), the
   live monitor bails out with `"resync"`, the connection is dropped and
   `full_sync()` runs again. This guards against silently missed events if
   `live_capture()` dies quietly.
6. **Reconnect loop**: `run_device()` wraps all of the above in a
   `while not STOP_REQUESTED` loop with a fixed `RETRY_SECONDS` (5s) backoff
   on any exception (device offline, network drop, etc).

**Multi-device orchestration**: `device_manager()` polls the `zkt_devices`
table (via `get_active_devices()`) every `DEVICE_REFRESH_SECONDS` (10s) and
spawns one daemon thread (`run_device`) per active device it doesn't already
have a thread for. Devices are added/removed at runtime through the Flask UI
(`/devices/add`, `/devices/<id>/remove`) — the collector picks up changes
without a restart. Threads for removed devices are only *untracked*, not
forcibly killed; the running thread notices on its own retry cycle.

Graceful shutdown: `SIGINT`/`SIGTERM` sets a global `STOP_REQUESTED` flag
that all loops check.

## Files

| File | Role |
|---|---|
| `collector.py` | The daemon described above. Entry point: `python collector.py`. |
| `database.py` | All Postgres access: schema creation (`create_table`), device CRUD, bulk attendance insert (`insert_records`, COPY-based), name backfill. Single source of truth for the schema. |
| `config.py` | Loads `.env` via `python-dotenv`, exposes `DATABASE_URL`. Also holds a legacy/unused static `DEVICES` list and tunables (`DEVICE_RETRY_SECONDS`, `FULL_SYNC_AFTER_MINUTES`, etc.) that **`collector.py` does not actually read** — it hardcodes its own copies at the top of the file. Devices now come from the `zkt_devices` DB table, not this list. Treat `config.py`'s constants as stale/decorative until reconciled. |
| `zkteco.py` | `ZKTecoDevice` — a thin OOP wrapper around `pyzk`'s `ZK` (connect/disconnect/get_users/get_attendance/live_capture). **Not used by `collector.py`**, which talks to `pyzk`'s `ZK` directly. Appears to be an earlier abstraction; check before extending it. |
| `device_manager.py` | `test_device()` — connects to a device once, reads its identity, disconnects. Used by the Flask "Add Device" flow to validate a device before saving it. |
| `app.py` | Flask app: attendance browser (`/`, JSON API at `/api/attendance`, per-record view, CSV export) and device management (`/devices`, add/activate/deactivate). Renders `templates/*.html`, styled by `static/style.css`. |
| `web_database.py` | Read-side Postgres queries for the Flask app (filtering, pagination, CSV export). Talks to the same `zkt_attendance` table as `database.py` but is a separate query layer — keep filter/column changes in sync between the two if the schema changes. |
| `zkteco_to_csv.py` | Standalone one-off script: connects to the hardcoded device IP and dumps its full attendance log straight to `attendance_records.csv`. Not part of the collector pipeline; a manual/debug tool. |
| `attendance_records.csv` | Output of `zkteco_to_csv.py` above. Generated data, now gitignored — don't treat it as a source of truth. |
| `collector.py.bak`, `database.py.bak` | Stale pre-multi-device versions (single hardcoded device, no `zkt_devices` table). Kept in the working tree but gitignored; safe to ignore or delete. |

## Database schema (Neon Postgres)

Defined in `database.py::create_table()`, called from `collector.py::main()`
on every collector start (idempotent — `CREATE TABLE IF NOT EXISTS`).

### `zkt_attendance`
One row per punch event.
- `device_id` — stable device identity. **Serial number if available,
  otherwise `"{ip}:{port}"`** (see `prepare_record()` in `collector.py`).
  This means device identity can silently change if a device's serial can't
  be read on first sync — watch for this when debugging duplicate devices.
- `branch_name`, `device_ip`, `device_port`, `device_name`, `serial_number`,
  `firmware`, `platform` — denormalized device info, copied onto every row
  at insert time (not joined from `zkt_devices`).
- `user_id`, `user_name` — `user_name` is often `NULL` on first sync (see
  below) and backfilled later.
- `attendance_time`, `status`, `punch`, `punch_type` (human label derived
  from `punch` via the `PUNCH_TYPES` dict in `collector.py`).
- `record_hash` — `UNIQUE`, but **currently just `str(attendance)`** (the
  raw pyzk object repr), not a computed hash. `database.py` also defines
  `make_record_hash()` (a real SHA-256 of device/user/time/status/punch) but
  it is **not called anywhere** — dead code / inconsistency to be aware of.
- **Real deduplication constraint**: a composite `UNIQUE (device_id, user_id,
  attendance_time, status, punch)` — named `zkt_attendance_device_record_unique`
  in the live Neon database — used by `insert_records()`'s
  `ON CONFLICT ... DO NOTHING`. Confirmed present via `pg_constraint`, but it
  is **not created by `create_table()`** (it was added manually/out-of-band
  at some point). **A fresh database bootstrapped only from
  `create_table()` will NOT have this constraint**, which would make
  `insert_records()`'s `ON CONFLICT` clause fail outright. Add it manually
  when setting up a new environment:
  ```sql
  ALTER TABLE zkt_attendance
    ADD CONSTRAINT zkt_attendance_device_record_unique
    UNIQUE (device_id, user_id, attendance_time, status, punch);
  ```

### `zkt_devices`
One row per physical device, managed via the Flask "Devices" page.
- `device_id` (unique) — same serial-or-`ip:port` identity as above.
- `branch_name`, `ip_address`, `port`, `device_name`, `serial_number`,
  `firmware`, `platform`.
- `status` — `'active'` / `'inactive'`. Only `active` devices are polled by
  `device_manager()` in the collector.
- `first_seen`, `last_seen`, `created_at`, `updated_at`.

### Insert path (`insert_records`)
Bulk-loads records into a `COPY`-based temp table
(`zkteco_attendance_stage`), then `INSERT ... SELECT ... ON CONFLICT DO
NOTHING` into `zkt_attendance`. Returns `(inserted_count, duplicate_count)`.
This is how "check if already in DB, if not push" is implemented — it's a
single upsert-style statement per sync batch, not a row-by-row existence
check.

### Employee names
Device attendance logs only carry a numeric `user_id`, not a name. Names
come from `conn.get_users()` (a separate device call) and are written via
`update_attendance_names()`, which only fills rows where `user_name IS NULL
OR user_name = ''`. This runs after every full sync and is why a name may
be missing on a punch until the *next* sync completes.

## Data flow summary

```
ZKTeco device (pyzk)
   -> collector.py: full_sync()      -- one-time backfill of all device records
   -> collector.py: live_monitor()   -- ongoing, pushes new punches as they happen
   -> database.py: insert_records()  -- COPY + INSERT ... ON CONFLICT DO NOTHING
   -> Neon Postgres: zkt_attendance / zkt_devices

Flask app (app.py, web_database.py)
   -> reads zkt_attendance / zkt_devices (read-only, no writes back to devices)
   -> browser UI + JSON API + CSV export
```

## Environment / secrets

- `DATABASE_URL` lives in `.env` (Neon connection string, `sslmode=require`).
  **`.env` was committed to git in the initial commit** and has now been
  removed from tracking going forward (see `.gitignore`), but the credential
  already exists in git history. **Rotate the Neon database password** if
  this repo's history is or will be pushed anywhere shared/public.
- `config.py` raises at import time if `DATABASE_URL` is missing — every
  entry point (`collector.py`, `app.py`) will fail fast without a valid `.env`.

## Known rough edges / things to confirm before relying on them

- `SAFETY_SYNC_MINUTES` in `collector.py` has a comment suggesting it was
  temporarily set low for testing ("Keep 1 minutes for testing... Change to
  45 after testing") but the value is `45`. Confirm this is the intended
  production value.
- `config.py`'s `DEVICES` list and several tunables are vestigial — devices
  are actually sourced from the `zkt_devices` DB table at runtime.
- `zkteco.py` (`ZKTecoDevice` class) is unused by the live collector path.
- `database.py`'s `make_record_hash()` is unused; `record_hash` is just the
  raw object `repr()`. Real dedup relies on the composite unique constraint.
- The composite unique constraint on `zkt_attendance` isn't in
  `create_table()`'s DDL (see Database section above) — it must be added by
  hand on any new/restored database, or full syncs will crash.
- The Flask dashboard (`app.py`, templates, `static/style.css`) is expected
  to change significantly later; treat it as replaceable, not load-bearing.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# create .env with DATABASE_URL=postgresql://...
python collector.py     # start the always-on device -> DB sync daemon
python app.py            # optional: dashboard on http://127.0.0.1:5000
```
