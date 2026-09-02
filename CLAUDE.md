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
   core of the project. **Write path — do not modify without explicit
   instruction.** The user has repeatedly asked that the save/sync logic
   stay untouched while the read side gets rebuilt around it.
2. **`app.py` + `api.py` + `web_database.py`** — the read side: a Flask
   dashboard and a versioned, API-key-protected JSON REST API
   (`/api/v1/...`) for browsing/exporting what the collector has stored.
   This was redesigned from scratch (2026-09) for speed and Postman
   usability — see "Web dashboard & API" below. Safe to keep evolving.

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
| `device_manager.py` | `test_device()` — connects to a device once, reads its identity, disconnects. Used by both the HTML "Add Device" form (`app.py`) and the `POST /api/v1/devices` endpoint (`api.py`) to validate a device before saving it. Unchanged by the redesign. |
| `db_pool.py` | Shared `psycopg_pool.ConnectionPool` used by **only** `web_database.py`. Exists purely to remove the ~1.5-2s per-connection handshake cost that made every dashboard/API request slow. `collector.py` and `database.py` do not import this and keep opening plain `psycopg.connect()` connections exactly as before. |
| `web_database.py` | All read-side Postgres queries: attendance listing/count (one pool checkout, two queries), single record lookup, CSV export, filter-dropdown values and summary stats (both cached in-process with a short TTL — `config.FILTER_CACHE_SECONDS` / `STATS_CACHE_SECONDS`), and read-only device listing (`list_devices()`). Talks to the same tables as `database.py` but is a separate query layer — keep filter/column changes in sync between the two if the schema changes. |
| `api.py` | Flask blueprint mounted at `/api/v1`. Every route except `/health` and `/openapi.json` requires the `X-API-Key` header (checked in a `before_request`, compared against `config.API_KEY`). Attendance/stats/filters/device-list routes call `web_database.py`; device write routes (`POST /devices`, `.../activate`, `.../deactivate`) call `database.py`'s existing functions unchanged. |
| `openapi_spec.py` | Hand-written OpenAPI 3.0 dict describing every `/api/v1` endpoint. Served as JSON at `GET /api/v1/openapi.json` — import that URL directly into Postman (File → Import → Link) to get a ready-made collection. Also powers the Swagger UI page at `/api/docs` (`templates/api_docs.html`, Swagger UI loaded from a CDN). |
| `app.py` | Flask app entry point. Registers the `api.py` blueprint, renders HTML pages (`/`, `/devices`, `/devices/add`, `/record/<id>`, `/api/docs`), and handles the HTML device-management form posts (delegates to `database.py`, logic unchanged from before the redesign — only the templates changed). Injects `api_key` into every template via `context_processor` so the dashboard's own JS can call `/api/v1/*` like any other client. |
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

## Web dashboard & API (redesigned 2026-09)

The original dashboard opened a **new** Postgres connection for every query
(list, count, and each of 5 separate `DISTINCT` filter-option queries), and
each new connection to this Neon endpoint costs roughly 1.5-2s. A single
page-1 load could open 5+ connections and take 8-10+ seconds even though the
table is small (tens of thousands of rows, fully indexed) and every query
individually is fast. That is the entire root cause — it was not a database
or indexing problem.

Fix, entirely on the read side (`db_pool.py`, `web_database.py`, `api.py`,
`app.py`, templates, `static/`):

- **Connection pooling** (`db_pool.py`, `psycopg_pool.ConnectionPool`) — the
  dashboard/API keep a small pool of already-authenticated connections
  instead of opening a fresh one per query.
- **Fewer round trips per request** — `get_attendance_page()` does the page
  of rows and the total count in one pool checkout; `get_filter_options()`
  fetches all 5 dropdown lists in a single `UNION ALL` query instead of 5
  separate ones.
- **Caching** — filter-dropdown values and summary stats rarely change
  between requests, so both are cached in-process with a short TTL
  (`config.FILTER_CACHE_SECONDS` = 120s, `STATS_CACHE_SECONDS` = 20s) via
  the `_TTLCache` helper in `web_database.py`. This cache is per-process and
  not shared across workers/restarts — fine for this app's traffic, but
  don't assume it's a distributed cache if the app is ever scaled out.
- **Home page (`/`) does zero DB work on render** — it ships an empty shell;
  the browser fills it in via `fetch()` calls to `/api/v1/*` (see
  `static/attendance.js`). This mirrors the original design's intent
  ("browser will call the API") but now the API itself is fast.

**Frontend** is plain HTML/CSS/vanilla JS (no build step, no framework) —
`static/style.css` (design tokens + components), `static/app.js` (shared
`ZKT` helper: API-key-aware `fetch` wrapper, HTML escaping, debounce, badge
coloring), `static/attendance.js` (the attendance page: filters, sorting,
pagination, stat cards, CSV export via blob download). Device management
pages (`devices.html`, `add_device.html`) stayed server-rendered Jinja
forms — they're low-frequency admin actions, not the thing that was slow.

**API** (`api.py`, mounted at `/api/v1`, doc'd in full at `/api/docs` and
`/api/v1/openapi.json`):

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/health` | No API key required. |
| GET | `/api/v1/attendance` | Filters: `employee_id`, `branch`, `device_ip`, `device_serial`, `punch_type`, `status`, `search` (name/ID), `from_date`, `to_date`; plus `sort_by`/`sort_dir`, `page`/`per_page`. |
| GET | `/api/v1/attendance/<id>` | Single record. |
| GET | `/api/v1/attendance/export.csv` | Same filters as list, streams CSV. |
| GET | `/api/v1/attendance/filters` | Cached dropdown values. |
| GET | `/api/v1/stats` | Cached summary counts (total records, today, unique employees, device counts). |
| GET | `/api/v1/devices` | Read-only, pooled (`web_database.list_devices()`). |
| POST | `/api/v1/devices` | Same test-then-save flow as the HTML form, calls `database.add_device()` unchanged. Body: `{branch_name, ip_address, port}`. |
| POST | `/api/v1/devices/<device_id>/activate` `/deactivate` | Calls `database.py` unchanged. |

**Auth**: every route above except `/health` and `/openapi.json` requires
header `X-API-Key: <value>`. The key lives in `.env` as `API_KEY` (not
committed — see `.gitignore`). The dashboard's own pages inject it into a
`<meta name="api-key">` tag server-side so its own JS can call the same API
any other client would; this is a shared-secret scheme (one key for
everyone with the URL), not per-user auth — adequate for an internal tool,
not for anything exposed publicly without additional hardening.

## Data flow summary

```
ZKTeco device (pyzk)
   -> collector.py: full_sync()      -- one-time backfill of all device records
   -> collector.py: live_monitor()   -- ongoing, pushes new punches as they happen
   -> database.py: insert_records()  -- COPY + INSERT ... ON CONFLICT DO NOTHING
   -> Neon Postgres: zkt_attendance / zkt_devices

Flask app + API (app.py, api.py, web_database.py, db_pool.py)
   -> reads zkt_attendance / zkt_devices through a pooled connection
      (read-only, no writes back to the physical devices)
   -> browser UI (fetches /api/v1/*) + versioned JSON API + CSV export
   -> device add/activate/deactivate writes still go through database.py
```

## Environment / secrets

- `DATABASE_URL` lives in `.env` (Neon connection string, `sslmode=require`).
  **`.env` was committed to git in the initial commit** and has now been
  removed from tracking going forward (see `.gitignore`), but the credential
  already exists in git history. **Rotate the Neon database password** if
  this repo's history is or will be pushed anywhere shared/public.
- `config.py` raises at import time if `DATABASE_URL` is missing — every
  entry point (`collector.py`, `app.py`) will fail fast without a valid `.env`.
- `API_KEY` also lives in `.env` (read side only — `collector.py` never
  reads it). If unset, every `/api/v1/*` request (including the dashboard's
  own) fails with a 500 telling you to set it; `app.py` also prints a
  startup warning. `web_database.py`'s pool size and cache TTLs are
  likewise configurable via `.env` (`WEB_POOL_MIN_SIZE`, `WEB_POOL_MAX_SIZE`,
  `FILTER_CACHE_SECONDS`, `STATS_CACHE_SECONDS`) but have sane defaults.

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
- `/api/docs` loads Swagger UI from `cdnjs.cloudflare.com` — the docs page
  needs internet access to render; the API itself (`/api/v1/*`) does not.
- The `web_database.py` TTL cache is a plain in-process dict guarded by a
  lock — correct for a single Flask process, but if this is ever run with
  multiple workers/dynos each will have its own cache and its own view of
  "fresh," which is fine for filter dropdowns/stats but worth knowing.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# create .env with DATABASE_URL=postgresql://... and API_KEY=<random string>
python collector.py     # start the always-on device -> DB sync daemon
python app.py            # optional: dashboard on http://127.0.0.1:5000
```

Dashboard: `http://127.0.0.1:5000`. API docs (Swagger UI): `/api/docs`.
Raw OpenAPI spec (importable into Postman): `/api/v1/openapi.json`. Every
`/api/v1/*` call needs header `X-API-Key: <value from .env>`.
