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
without a restart.

**Deactivation is self-checked, not externally killed** (fixed 2026-09,
was previously a real bug — see below): each `run_device()` thread checks
`is_device_active(device_id)` (in `database.py`) itself, at two points —
once at the top of its reconnect loop (before bothering to connect), and
again roughly every `STATUS_CHECK_SECONDS` (15s) inside `live_monitor()`'s
polling loop. If the device has been deactivated, `live_monitor()` returns
`"deactivated"` and the thread exits its `while` loop for good — it is not
forcibly killed from outside, it notices and stops itself, typically within
~15s of the "Remove" action. `device_manager()` only removes a device from
its `running_devices` tracking dict once `thread.is_alive()` is `False`
(not the moment the DB row flips to inactive) — this is what prevents a
second thread being spawned for the same physical device if it's quickly
reactivated while the first thread is still winding down.

**Why this matters**: `update_device_online()` (called every time a thread
(re)connects — every resync, every retry) intentionally does **not** touch
`status` — it only used to touch it. Before this fix it unconditionally set
`status = 'active'` on every reconnect, which silently undid a manual
"Remove device" the next time that device's thread happened to reconnect
(sometimes within seconds). `status` is now exclusively an admin-controlled
flag — only `add_device()` / `activate_device()` / `deactivate_device()`
touch it. If you're asked to add more device metadata refresh logic, do NOT
have it write `status` — read it via `is_device_active()` instead.

Graceful shutdown: `SIGINT`/`SIGTERM` sets a global `STOP_REQUESTED` flag
that all loops check.

## Files

| File | Role |
|---|---|
| `collector.py` | The daemon described above. Entry point: `python collector.py`. |
| `database.py` | All Postgres access: schema creation (`create_table`), device CRUD, bulk attendance insert (`insert_records`, COPY-based), name backfill. Single source of truth for the schema. |
| `config.py` | Loads `.env` via `python-dotenv`, exposes `DATABASE_URL`. Also holds a legacy/unused static `DEVICES` list and tunables (`DEVICE_RETRY_SECONDS`, `FULL_SYNC_AFTER_MINUTES`, etc.) that **`collector.py` does not actually read** — it hardcodes its own copies at the top of the file. Devices now come from the `zkt_devices` DB table, not this list. Treat `config.py`'s constants as stale/decorative until reconciled. |
| `zkteco.py` | `ZKTecoDevice` — a thin OOP wrapper around `pyzk`'s `ZK` (connect/disconnect/get_users/get_attendance/live_capture). **Not used by `collector.py`**, which talks to `pyzk`'s `ZK` directly. Appears to be an earlier abstraction; check before extending it. |
| `device_manager.py` | `test_device()` — connects to a device once, reads its identity, disconnects. Used **only** by the HTML "Add Device" form in `app.py` — device management is not exposed via the API at all (see below). |
| `db_pool.py` | Shared `psycopg_pool.ConnectionPool` used by **only** `web_database.py`. Exists purely to remove the ~1.5-2s per-connection handshake cost that made every dashboard/API request slow. `collector.py` and `database.py` do not import this and keep opening plain `psycopg.connect()` connections exactly as before. |
| `web_database.py` | All read-side Postgres queries: attendance listing/count (one pool checkout, two queries), single record lookup, CSV export, filter-dropdown values and summary stats (both cached in-process with a short TTL — `config.FILTER_CACHE_SECONDS` / `STATS_CACHE_SECONDS`), and read-only device listing (`list_devices()`). Talks to the same tables as `database.py` but is a separate query layer — keep filter/column changes in sync between the two if the schema changes. |
| `api.py` | Flask blueprint mounted at `/api/v1`. Every route except `/health` and `/openapi.json` requires the `X-API-Key` header (checked in a `before_request`, compared against `config.API_KEY`). Attendance/stats/filters routes call `web_database.py`. `GET /devices` is the only device route — **read-only, on purpose**: add/activate/deactivate are deliberately not reachable via the API, only through the web app's own forms. |
| `openapi_spec.py` | Hand-written OpenAPI 3.0 dict describing every `/api/v1` endpoint. Served as JSON at `GET /api/v1/openapi.json` — import that URL directly into Postman (File → Import → Link) to get a ready-made collection. Also powers the Swagger UI page at `/api/docs` (`templates/api_docs.html`, Swagger UI loaded from a CDN). |
| `rate_limiter.py` | Shared `flask_limiter.Limiter` instance (in-memory storage, keyed on the caller's API key, 200 req/min default, tighter 10/min on CSV export). Imported by both `app.py` (`.init_app(app)`) and `api.py` (per-route `@limiter.limit(...)` / `@limiter.exempt`). |
| `app.py` | Flask app entry point. Registers the `api.py` blueprint, initializes `rate_limiter.py`'s limiter, renders HTML pages (`/`, `/devices`, `/devices/add`, `/record/<id>`, `/api/docs`), and handles the HTML device-management form posts (delegates to `database.py`, logic unchanged from before the redesign — only the templates changed). Injects `api_key` into every template via `context_processor` so the dashboard's own JS can call `/api/v1/*` like any other client. |
| `zkteco_to_csv.py` | Standalone one-off script: connects to the hardcoded device IP and dumps its full attendance log straight to `attendance_records.csv`. Not part of the collector pipeline; a manual/debug tool. Leaves a file on disk if run — nothing else in the project writes files to disk (CSV export in the app/API is generated in memory and streamed, never touches the filesystem). |
| `attendance_records.csv` | Output of `zkteco_to_csv.py` above. Generated data, now gitignored — don't treat it as a source of truth. |
| `collector.py.bak`, `database.py.bak` | Stale pre-multi-device versions (single hardcoded device, no `zkt_devices` table). Kept in the working tree but gitignored; safe to ignore or delete. |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore` | Production deployment (added 2026-09). One image, two services: `web` (dashboard/API under `waitress-serve`, real concurrency instead of Flask's single-threaded dev server) and `collector` (same image, `command: python collector.py`). Both read config via `env_file: .env`. See "Running in production" below. |
| `deploy.sh` | One-command setup for a fresh server (added 2026-09): checks Docker is installed, creates `.env` from `DATABASE_URL`/`API_KEY`/`DB_NETWORK` env vars passed into the script invocation (only if `.env` doesn't already exist), runs `docker compose up -d --build` (layering in `docker-compose.network.yml` when `DB_NETWORK` is set), then — if `DEVICES` is set — runs `seed_devices.py` as a one-off container to register devices too. |
| `docker-compose.network.yml` | Optional Compose override, only applied when `DB_NETWORK` is set. Attaches `web`/`collector` to an external Docker network by name — needed when Postgres runs in a *different* Docker Compose project on the same server (a shared VPS) and `DATABASE_URL` uses that project's container name as the host. |
| `seed_devices.py` | Standalone script (added 2026-09): registers one or more devices non-interactively, given a `"Branch,ip,port;Branch,ip,port"` string — reuses `device_manager.test_device()` + `database.add_device()`, the exact same connect-then-save flow as the "Add Device" form. Skips (does not duplicate) a device already registered at a given ip/port, so safe to pass on every `deploy.sh` run. Runs standalone too: `python3 seed_devices.py "..."`. |
| `.env.example` | Template for `.env` — copy it and fill in real values. Not read by any code, just documentation. |

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
  — used by `insert_records()`'s `ON CONFLICT ... DO NOTHING`. **As of
  2026-09, `create_table()` creates this itself** (wrapped in a
  `DO $$ ... EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
  END $$;` block, since Postgres has no `ADD CONSTRAINT IF NOT EXISTS`).
  Both the "already exists" path (existing databases, e.g. the live one)
  and the "doesn't exist yet" path (a genuinely fresh database) are
  covered — verified directly against the live database and a disposable
  scratch table respectively. `duplicate_table`, not `duplicate_object`,
  is the exception Postgres actually raises for a UNIQUE constraint name
  collision (its backing index shares the name) — this tripped up the
  first version of this fix; if you're ever adding a similar "create if
  missing" DO block for a UNIQUE/PRIMARY KEY constraint elsewhere, catch
  both exception classes, not just `duplicate_object`.

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
| GET | `/api/v1/attendance` | Filters: `since_id`, `employee_id`, `branch`, `device_ip`, `device_serial`, `punch_type`, `status`, `search` (name/ID), `from_date`, `to_date`; plus `sort_by`/`sort_dir`, `page`/`per_page`. |
| GET | `/api/v1/attendance/<id>` | Single record. |
| GET | `/api/v1/attendance/export.csv` | Same filters as list (including `since_id`), streams CSV. |
| GET | `/api/v1/attendance/filters` | Cached dropdown values (branches, device IPs/serials, punch types, status codes actually present in the data). |
| GET | `/api/v1/stats` | Cached summary counts, including `latest_id` (highest attendance row id right now — the bootstrap value for `since_id` polling). |
| GET | `/api/v1/devices` | Read-only, pooled (`web_database.list_devices()`). **No POST/activate/deactivate on the API** — device management is intentionally web-app-only (see below). |

**Incremental polling (`since_id`)**: added after the initial redesign
because a downstream integration and employee self-service via Postman both
need "did anything new arrive since I last checked." `id` (the attendance
table's `BIGSERIAL` primary key) is used as the cursor rather than a
timestamp — it's assigned at insert time and strictly increasing, so it
can't miss or double-count rows the way filtering on `attendance_time` or
`created_at` could around clock drift/backdated punches. Pattern: call
`GET /stats` once for `latest_id`, then poll
`GET /attendance?since_id=<last_seen_id>&sort_by=id&sort_dir=asc`, advancing
`last_seen_id` to the max `id` seen each time. Documented with a full
worked example in the `since_id` parameter description in
`openapi_spec.py` and as a cheat-sheet card on `/api/docs`
(`templates/api_docs.html`).

**On the `status` field**: it is a raw device verification-method code
(observed values in this data: 1, 3, 4 — likely fingerprint/password/card
or similar), **not** check-in/out state — that's `punch`/`punch_type`.
There's no authoritative ZKTeco mapping encoded anywhere in this codebase;
don't invent one. `punch_type` also has a real `'Unknown'` bucket in
production data (raw `punch` code 255, not in `collector.py`'s
`PUNCH_TYPES` dict) — worth knowing if you're asked to reconcile counts.

**Auth**: every route above except `/health` and `/openapi.json` requires
header `X-API-Key: <value>`. The key lives in `.env` as `API_KEY` (not
committed — see `.gitignore`). The dashboard's own pages inject it into a
`<meta name="api-key">` tag server-side so its own JS can call the same API
any other client would; this is a shared-secret scheme (one key for
everyone with the URL), not per-user auth — adequate for an internal tool,
not for anything exposed publicly without additional hardening.

**Device management is deliberately excluded from the API** (decided
2026-09): the API is meant to be handed out broadly (employees in Postman,
an integration app), and letting that same key add/remove physical devices
from the collector was judged too much privilege for a read-oriented key.
`POST /api/v1/devices` and the activate/deactivate routes that existed
briefly during the 2026-09 redesign were removed — if you're asked to add
device write endpoints back to the API, confirm that's really wanted first,
it was a deliberate choice, not an oversight.

**Rate limiting** (`rate_limiter.py`, added 2026-09): default 200
requests/minute per API key (falls back to remote IP for unauthenticated
requests), 10/minute specifically on `/attendance/export.csv` since it's
the heaviest query. `/health` and `/openapi.json` are exempt. In-memory
storage — per-process, resets on restart, and if this is ever run with
multiple worker processes each enforces its own separate budget rather
than a shared one (same caveat as the TTL cache below).

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
   -> device add/activate/deactivate: web app forms ONLY, not exposed via API
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

## pyzk connects over TCP, but pings first unless told not to

`pyzk`'s `ZK.connect()` (used by `collector.py`, `device_manager.py`,
`zkteco.py`, `zkteco_to_csv.py`) does an OS-level ICMP `ping` shell-out
*before* attempting the actual TCP connection, and raises
`ZKNetworkError("can't reach device (ping <ip>)")` if that ping fails —
even if the TCP port the device actually talks on is completely reachable.
Many routers/NATs/firewalls (especially for port-forwarded devices at a
remote branch) block ICMP echo while still forwarding the TCP port fine, so
this false-negative is common, not an edge case. All four files construct
`ZK(..., ommit_ping=True)` for this reason — skips the ping shell-out,
relies on the real TCP connect (which `pyzk` still performs, so genuinely
unreachable devices still fail correctly). If a device add ever fails with
that exact "can't reach device (ping ...)" message, confirm with
`nc -vz <ip> <port>` before assuming the device is actually down — if `nc`
succeeds, this is almost certainly the same ICMP-blocked situation.

## Known rough edges / things to confirm before relying on them

- `SAFETY_SYNC_MINUTES` in `collector.py` is `60` (bumped from `45` in
  commit `7e85565`, "properly listen after 1hr with full fresh data"). The
  comment above it ("Keep 1 minutes for testing... Change to 45 after
  testing") is now stale/pre-dates that change — not a live TODO.
- `config.py`'s `DEVICES` list and several tunables are vestigial — devices
  are actually sourced from the `zkt_devices` DB table at runtime.
- `zkteco.py` (`ZKTecoDevice` class) is unused by the live collector path.
- `database.py`'s `make_record_hash()` is unused; `record_hash` is just the
  raw object `repr()`. Real dedup relies on the composite unique constraint.
- `/api/docs` loads Swagger UI from `cdnjs.cloudflare.com` — the docs page
  needs internet access to render; the API itself (`/api/v1/*`) does not.
- The `web_database.py` TTL cache is a plain in-process dict guarded by a
  lock — correct for a single Flask process, but if this is ever run with
  multiple workers/dynos each will have its own cache and its own view of
  "fresh," which is fine for filter dropdowns/stats but worth knowing.
- **Device identity can silently change.** `prepare_record()` in
  `collector.py` falls back to `"{ip}:{port}"` as `device_id` if a device's
  serial can't be read. If that device is on a dynamic IP and it changes,
  the collector treats it as a brand-new device from then on — new
  `device_id`, and prior history looks orphaned. No mitigation exists for
  this today; if asked to fix it, it needs a human-in-the-loop "merge
  devices" flow, not an automated guess.
- **`record_hash` isn't device-scoped.** It's `str(attendance)` (the raw
  pyzk repr) with a global `UNIQUE` constraint, but doesn't include
  `device_id`. Two different devices producing a punch with identical
  `user_id`/timestamp-to-the-second/`status`/`punch` would collide on this
  constraint — that one live insert would raise and get retried on the
  device's normal error/reconnect cycle, not silently dropped. Realistically
  very unlikely, not worth "fixing" unless it's actually observed.
- **CORS is not configured.** Doesn't matter for Postman or the dashboard's
  own same-origin JS. Would matter if a browser-based integration app on a
  *different* domain tries to call `/api/v1/*` directly with `fetch()` — add
  `flask-cors` (or manual headers) if/when that's actually needed; skip it
  for a backend/server-side integration, which isn't subject to CORS at all.

## Running in production (Docker)

Intended path for a real server, added 2026-09 alongside the automatic
schema init above: `git clone` + one script, nothing else.

```bash
DATABASE_URL="postgresql://user:pass@host:5432/dbname" \
API_KEY="<generate with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'>" \
./deploy.sh
```

`deploy.sh` checks Docker is installed, creates `.env` from those vars
(only if `.env` doesn't already exist — never overwrites one), then runs
`docker compose up -d --build`. Every run after the first is just
`./deploy.sh` with no vars needed, since `.env` is already there.

Two containers from one image: `web` (dashboard/API on port 5000, served by
`waitress-serve --threads=8` — real concurrent request handling, unlike
Flask's dev server) and `collector` (same image, `command: python
collector.py`). Both restart automatically (`restart: unless-stopped`) and
read config from the same `.env` via `env_file:`. `docker compose logs -f
collector` / `docker compose logs -f web` to watch either one.
`docker compose restart collector` after any `collector.py`/`database.py`
change — like any Python process, it only picks up new code on restart.

**Database on the same server, not remote** (`docker-compose.network.yml`,
`DB_NETWORK` in `.env`): if Postgres runs in a *different* Docker Compose
project on the same machine (e.g. a shared VPS also running another app's
database), the hostname in `DATABASE_URL` (like `postgres` in
`postgresql://user:pass@postgres:5432/dbname`) only resolves between
containers sharing a Docker network — it is not resolvable system-wide.
Set `DB_NETWORK=<that project's docker network name>` and `deploy.sh`
layers `docker-compose.network.yml` on top, which attaches `web` and
`collector` to that external network (`docker network ls` on the server
to find the name). Without this, `docker compose up` succeeds but the
containers can't reach the database at all.

**Prisma-originated connection strings**: a `DATABASE_URL` copied from a
Prisma-based project often has a trailing `?schema=public`. `psycopg`
does not recognize that query parameter and raises
`invalid URI query parameter: "schema"` on connect — confirmed directly
against `psycopg.conninfo.conninfo_to_dict()`. Strip it; `public` is the
default schema regardless, so nothing changes functionally by removing
it. Not something to silently work around in code (e.g. by stripping
unknown query params) — the fix belongs in the `.env` value itself.

## Running locally (dev, no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# create .env with DATABASE_URL=postgresql://... and API_KEY=<random string>
python collector.py     # start the always-on device -> DB sync daemon
python app.py            # dashboard on http://127.0.0.1:5000 (dev server -
                          # single-threaded; use Docker/waitress for anything
                          # more than solo local testing)
```

Dashboard: `http://127.0.0.1:5000`. API docs (Swagger UI): `/api/docs`.
Raw OpenAPI spec (importable into Postman): `/api/v1/openapi.json`. Every
`/api/v1/*` call needs header `X-API-Key: <value from .env>`.
