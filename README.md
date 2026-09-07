# ZKTeco Attendance Scrapper

A background service that pulls attendance punch records from **ZKTeco
fingerprint/face terminals** and stores them in a **PostgreSQL** database,
plus a **Flask dashboard** and a **versioned REST API** for browsing,
exporting, and integrating with that data.

Built and tested against a **ZKTeco F18**, but the collector talks to any
device supported by the `pyzk` protocol.

---

## Table of contents

- [What this project does](#what-this-project-does)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started (Docker — the fast path)](#getting-started-docker--the-fast-path)
  - [Prerequisites](#prerequisites)
  - [1. Clone the project](#1-clone-the-project)
  - [2. Run the setup script](#2-run-the-setup-script)
  - [What's actually running](#whats-actually-running)
- [Local development (without Docker)](#local-development-without-docker)
- [Adding a device](#adding-a-device)
- [Using the REST API](#using-the-rest-api)
  - [Authentication](#authentication)
  - [Endpoints](#endpoints)
  - [Common queries](#common-queries)
  - [Polling for new data](#polling-for-new-data)
- [Database schema](#database-schema)
- [How the collector stays reliable](#how-the-collector-stays-reliable)
- [Security notes](#security-notes)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)

---

## What this project does

Every ZKTeco terminal at every branch keeps its own local log of punches
(check-in, check-out, breaks, overtime). This project centralizes that
data:

1. **Collects** — a background daemon (`collector.py`) connects to each
   registered device, pulls its full attendance history once, then keeps
   a live connection open and saves every new punch as it happens.
2. **Stores** — every punch lands in a Postgres table with the employee,
   branch, device, and timestamp attached, deduplicated automatically so
   re-syncing never creates duplicate rows.
3. **Serves** — a Flask dashboard lets you browse/filter/export the data
   in a browser, and a documented REST API lets you (or another system)
   query it programmatically — from Postman, a script, or another app.

Multiple branches/devices are supported simultaneously, and devices can be
added or removed at any time from the dashboard without restarting
anything.

## Architecture

```
┌─────────────────────┐        ┌──────────────────────┐
│  ZKTeco Device(s)    │        │  ZKTeco Device(s)     │
│  (Branch A)          │        │  (Branch B)            │
└──────────┬────────────┘        └───────────┬────────────┘
           │  pyzk (TCP)                      │  pyzk (TCP)
           ▼                                  ▼
   ┌───────────────────────────────────────────────────┐
   │                    collector.py                    │
   │  one independent thread per device:                │
   │   full_sync()  →  live_monitor()  →  repeat forever │
   └───────────────────────┬─────────────────────────────┘
                            │ COPY + INSERT ... ON CONFLICT DO NOTHING
                            ▼
                 ┌─────────────────────┐
                 │   PostgreSQL (Neon)  │
                 │  zkt_attendance      │
                 │  zkt_devices         │
                 └──────────┬────────────┘
                            │ pooled, read-only
                            ▼
          ┌──────────────────────────────────────┐
          │        app.py + api.py (Flask)         │
          │  dashboard (browser)  +  /api/v1/*       │
          └─────────────────┬──────────────────────┘
                             │
             ┌───────────────┼────────────────┐
             ▼               ▼                ▼
        Web browser       Postman        Your integration app
```

The **write path** (device → database) and the **read path** (database →
dashboard/API) are fully decoupled — the API never talks to a physical
device, and the collector never serves an HTTP request. This means the
dashboard/API can be redesigned, scaled, or taken down for maintenance
without affecting data collection at all.

## Tech stack

| Layer | Technology |
|---|---|
| Device protocol | [`pyzk`](https://pypi.org/project/pyzk/) (ZKTeco TCP protocol) |
| Database | PostgreSQL ([Neon](https://neon.tech), serverless) |
| DB driver | `psycopg` 3, with `psycopg_pool` on the read side |
| Backend | Python 3.12, Flask |
| Production server | [`waitress`](https://pypi.org/project/waitress/) (multi-threaded WSGI) |
| Rate limiting | `Flask-Limiter` |
| Frontend | Vanilla HTML/CSS/JS — no build step, no framework |
| API docs | Hand-written OpenAPI 3.0 spec + Swagger UI |
| Deployment | Docker / Docker Compose |

## Project structure

```
.
├── collector.py            # Always-on device → DB sync daemon (the core)
├── database.py              # All Postgres writes: schema, device CRUD, bulk insert
├── config.py                 # Loads .env, exposes settings
├── device_manager.py        # One-off device connection test (used by "Add Device")
├── zkteco.py                  # Unused legacy device wrapper (kept for reference)
├── zkteco_to_csv.py          # Standalone debug script - not part of the pipeline
│
├── app.py                    # Flask app: dashboard pages + device management forms
├── api.py                     # REST API blueprint, mounted at /api/v1
├── openapi_spec.py           # OpenAPI 3.0 spec served at /api/v1/openapi.json
├── web_database.py           # All read-side Postgres queries (pooled, cached)
├── db_pool.py                 # Shared connection pool for the read side
├── rate_limiter.py           # Shared Flask-Limiter instance
│
├── templates/                 # Jinja2 HTML templates
├── static/                     # CSS + vanilla JS
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── docker-compose.network.yml  # Optional override: join an external DB's Docker network
├── deploy.sh                    # One-command setup script (see Getting started)
├── .env.example
└── CLAUDE.md                   # Deep internal architecture notes for contributors
```

> Looking for a much more detailed, line-by-line breakdown of every module,
> every known edge case, and every design decision? See **`CLAUDE.md`** —
> it's written for anyone (human or AI) doing deep work on this codebase.

## Getting started (Docker — the fast path)

This is the intended way to run this project on a server: clone it, run
one script, done. No Python, no virtual environment, no manual package
install, no manual database setup — the container installs everything it
needs, and the schema (tables, indexes, and the dedup constraint) is
created automatically on first start, safe to re-run against an existing
database too.

### Prerequisites

- **Docker** on the target machine. If it's not installed yet:
  ```bash
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker $USER   # log out and back in afterwards
  ```
- A reachable PostgreSQL database (built and tested against
  [Neon](https://neon.tech), but any Postgres 13+ works — including one
  already running in another Docker project on the same server, see
  below)
- Network access from wherever the collector runs to your ZKTeco device(s)
  — see [Troubleshooting](#troubleshooting) if a device seems unreachable

### 1. Clone the project

```bash
git clone <this-repo-url>
cd "zkt dev scrapper"
```

### 2. Run the setup script

First run, with your real database URL and a generated API key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # generate an API key

DATABASE_URL="postgresql://user:password@host:5432/dbname" \
API_KEY="<the key you just generated>" \
./deploy.sh
```

`deploy.sh` checks Docker is installed, creates `.env` from those values
(only if `.env` doesn't already exist — it never overwrites one), builds
the image, and starts both containers. Every run after the first, once
`.env` exists, is just:

```bash
./deploy.sh
```

Open **`http://<server-ip>:5050`** for the dashboard — Docker defaults to
host port **5050** specifically so it doesn't collide with anything else
already running on the more common 5000. Override it with `WEB_PORT` if
you'd rather use a different one (the container's own internal port
always stays 5000 — this only changes what you connect to from outside):

```bash
DATABASE_URL="..." API_KEY="..." WEB_PORT="8080" ./deploy.sh
```

**If your database is Postgres running in a separate project's Docker
Compose setup on this same server** (a shared VPS, e.g. an existing app's
database container reachable only by its container name), pass the
network name too, so this project's containers can actually resolve that
hostname:

```bash
DATABASE_URL="postgresql://user:pass@postgres:5432/dbname" \
API_KEY="<key>" \
DB_NETWORK="<the other project's docker network name>" \
./deploy.sh
```

Find that network name with `docker network ls` on the server. See
`.env.example` for more detail, including a note if your connection
string was copied from a Prisma-based project (drop any `?schema=...`
query parameter — `psycopg` doesn't understand it and will refuse to
connect).

**To also register your devices without touching the web UI**, pass
`DEVICES` — one or more `Branch Name,ip,port` entries separated by `;`:

```bash
DATABASE_URL="postgresql://user:password@host:5432/dbname" \
API_KEY="<key>" \
DEVICES="CTG Office,119.10.168.198,1111;Chapai Office,118.179.113.115,8121" \
./deploy.sh
```

This connects to each device the same way "Add Device" in the dashboard
does, reads its serial/firmware automatically, and saves it — skipping
any device already registered at that IP/port, so it's safe to include
`DEVICES` on every run, not just the first.

### What's actually running

```bash
docker compose ps                  # both containers up?
docker compose logs -f web         # dashboard/API logs
docker compose logs -f collector   # sync daemon logs
docker compose restart collector   # after any collector.py/database.py change
```

| Service | What it runs | Notes |
|---|---|---|
| `web` | `waitress-serve --threads=8 app:app` | Real multi-threaded WSGI server, host port 5050 by default (or `WEB_PORT` if set) |
| `collector` | `python collector.py` | The always-on sync daemon |

Both restart automatically (`restart: unless-stopped`).

## Local development (without Docker)

For actually working on the code, not deploying it:

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env           # then fill in DATABASE_URL and API_KEY

python collector.py            # terminal 1 — the sync daemon
python app.py                  # terminal 2 — dashboard on http://127.0.0.1:5000
```

The schema is created automatically the first time `collector.py` runs —
no manual SQL needed, on a fresh database or an existing one.

> `python app.py` uses Flask's development server, which is
> single-threaded and explicitly not meant for real use beyond solo local
> testing. Use Docker (above) for anything more than that.

## Adding a device

1. Open the dashboard → **Devices** → **Add Device**.
2. Enter a branch name, the device's IP address, and port.
3. The app connects to the device, reads its serial number, firmware, and
   model automatically, and saves it.
4. The collector picks up the new device within 10 seconds — no restart
   needed.

Device management (add / activate / deactivate) is **only** available
through this dashboard, by design — it is intentionally not exposed
through the API, even though attendance data is.

## Using the REST API

Full interactive documentation lives at **`/api/docs`** (Swagger UI), and
the raw spec is at **`/api/v1/openapi.json`** — import that URL directly
into Postman (**File → Import → Link**) to get every endpoint as a
ready-made collection.

### Authentication

Every `/api/v1/*` endpoint except `/health` and `/openapi.json` requires
an API key:

```
X-API-Key: <your key from .env>
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Health check, no key required |
| GET | `/api/v1/attendance` | Paginated, filterable, sortable list of punches |
| GET | `/api/v1/attendance/{id}` | A single attendance record |
| GET | `/api/v1/attendance/export.csv` | Same filters as the list, streams a CSV |
| GET | `/api/v1/attendance/filters` | Current valid values for every filter (branches, punch types, etc.) |
| GET | `/api/v1/stats` | Summary counts: total records, today's count, unique employees, device counts |
| GET | `/api/v1/devices` | Read-only device list |

### Common queries

```bash
# One employee, a date range
curl -H "X-API-Key: <key>" \
  "http://localhost:5000/api/v1/attendance?employee_id=23&from_date=2026-08-01&to_date=2026-08-31"

# Filter by punch type
curl -H "X-API-Key: <key>" \
  "http://localhost:5000/api/v1/attendance?punch_type=Check+In"

# Export to CSV
curl -H "X-API-Key: <key>" \
  "http://localhost:5000/api/v1/attendance/export.csv?branch=CTG+Office" -o attendance.csv
```

### Polling for new data

For an integration that needs to know "has anything new arrived since I
last checked," use `since_id` — a cursor based on the attendance table's
auto-incrementing id, which is safe against clock drift and backdated
punches in a way a timestamp filter isn't:

```bash
# 1. Get a starting point
curl -H "X-API-Key: <key>" http://localhost:5000/api/v1/stats
# → { "latest_id": 46132, ... }

# 2. Poll from there, in insertion order
curl -H "X-API-Key: <key>" \
  "http://localhost:5000/api/v1/attendance?since_id=46132&sort_by=id&sort_dir=asc"
# → only records inserted after id 46132

# 3. Advance your stored cursor to the highest id you received, repeat
```

Rate limits: **200 requests/minute** per API key on general endpoints,
**10/minute** on the CSV export (the heaviest query).

## Database schema

Two tables, both in `database.py::create_table()`:

**`zkt_attendance`** — one row per punch: device identity, branch,
employee id/name, timestamp, raw status/punch codes and their
human-readable label, plus a dedup hash. Indexed on device, employee,
time, and branch.

**`zkt_devices`** — one row per physical device: identity, connection
details, and an `active`/`inactive` flag that controls whether the
collector currently polls it.

See `CLAUDE.md` for the full column-by-column reference.

## How the collector stays reliable

- **Full sync + live monitor**: on connect, it pulls the device's entire
  attendance history once (`full_sync`), then opens a live connection and
  saves each new punch immediately as it happens (`live_monitor`).
- **Automatic dedup**: every insert uses `ON CONFLICT ... DO NOTHING` on a
  composite key, so re-syncing the same data twice never creates
  duplicates — this is what makes "pull everything, then just keep
  listening" safe to do on every reconnect.
- **Safety re-sync**: if a device goes an hour without producing a live
  event, the collector assumes something might have been missed silently
  and does a full re-sync from scratch, just in case.
- **Self-healing per device**: every device runs in its own independent
  thread with its own retry loop — one device being offline, slow, or
  freshly deactivated never affects any other device's sync.
- **Deactivation is respected quickly**: removing a device from the
  dashboard is noticed by its own thread within ~15 seconds and it stops
  cleanly, rather than needing an external process to be killed.

## Security notes

- The API uses a single shared key (`X-API-Key`), suitable for an internal
  tool — it is not per-user authentication. Anyone with the key can read
  all attendance data across all employees/branches (by design, per this
  project's requirements).
- Device management is intentionally excluded from the API entirely, so a
  leaked/shared read key can never be used to add, remove, or reconfigure
  physical devices — only through the dashboard itself.
- `.env` (containing `DATABASE_URL` and `API_KEY`) is gitignored. Never
  commit it. Rotate the API key if it's ever exposed.

## Troubleshooting

**"Could not connect to device: can't reach device (ping x.x.x.x)"** —
`pyzk` checks ICMP ping reachability before connecting over TCP. Many
routers/firewalls block ICMP while still forwarding the actual TCP port
fine. Confirm with `nc -vz <ip> <port>` — if that succeeds, the device is
actually reachable and this error is a false negative (already worked
around in this codebase via `ommit_ping=True`, so if you see this it's
worth double-checking the running code is current).

**A device I removed still shows activity** — deactivation takes effect
within about 15 seconds, not instantly. If it's been longer than that,
check the collector logs for that device's thread.

**`/api/v1/*` returns a 500 telling you to set `API_KEY`** — `.env` is
missing or incomplete on the machine running `app.py`.

**`docker compose up` fails to connect to the database, or the collector
logs show a DNS/connection error to a hostname like `postgres`** — that
hostname only resolves between containers on the same Docker network. See
[step 2](#2-run-the-setup-script) — you likely need `DB_NETWORK` set to
the other project's network name.

**Connecting fails with `invalid URI query parameter: "schema"`** — your
`DATABASE_URL` was copied from a Prisma-based project and has a trailing
`?schema=public`. Remove it — `psycopg` doesn't understand that parameter,
and `public` is the default schema anyway so nothing is lost by dropping
it.

## Known limitations

- The API key is a single shared secret, not per-user auth — acceptable
  for an internal tool, not for public exposure without more work.
- If a device's serial number can't be read and it's later reconnected
  under a different IP, it will be treated as a new device (no automatic
  identity merging).
- In-process caching and rate limiting are per-process — running multiple
  web worker processes means each enforces its own separate view, not a
  shared one.

For the full, unfiltered list of edge cases and design tradeoffs, see
`CLAUDE.md`.
