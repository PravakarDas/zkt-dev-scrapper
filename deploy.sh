#!/usr/bin/env bash
#
# One-command setup for a fresh server.
#
# First run (no .env yet), values passed inline:
#   DATABASE_URL="postgresql://user:pass@host:5432/dbname" \
#   API_KEY="your-key" \
#   ./deploy.sh
#
# If your Postgres runs in another project's Docker Compose setup on
# this same server (shared VPS), also pass the network name so the
# hostname in DATABASE_URL actually resolves:
#   DATABASE_URL="postgresql://user:pass@postgres:5432/dbname" \
#   API_KEY="your-key" \
#   DB_NETWORK="hrm_default" \
#   ./deploy.sh
#
# Every run after that, once .env exists:
#   ./deploy.sh
#
# This script only ever creates .env if it's missing. It never
# overwrites an existing one - delete it yourself first if you want
# to regenerate it from new values.
#
# To also register devices without touching the web UI, pass DEVICES
# (safe to include on every run - a device already registered at a
# given ip/port is skipped, never duplicated):
#   DATABASE_URL="..." API_KEY="..." \
#   DEVICES="CTG Office,119.10.168.198,1111;Chapai Office,118.179.113.115,8121" \
#   ./deploy.sh
#
# Defaults to host port 5050 (the container's own internal port always
# stays 5000). Override with WEB_PORT if you want a different one:
#   DATABASE_URL="..." API_KEY="..." WEB_PORT="8080" ./deploy.sh

set -euo pipefail

cd "$(dirname "$0")"

echo "============================================================"
echo "ZKTeco Attendance - deploy"
echo "============================================================"
echo

# ------------------------------------------------------------
# Docker check
# ------------------------------------------------------------

if ! command -v docker &> /dev/null; then

    echo "Docker is not installed on this machine."
    echo
    echo "Install it with:"
    echo "  curl -fsSL https://get.docker.com | sudo sh"
    echo "  sudo usermod -aG docker \$USER"
    echo "  (then log out and back in for the group change to apply)"
    exit 1

fi

if ! docker compose version &> /dev/null; then

    echo "The 'docker compose' plugin was not found."
    echo "It's normally bundled with a current Docker install - see"
    echo "https://docs.docker.com/compose/install/ if it's missing."
    exit 1

fi

echo "Docker OK: $(docker --version)"

# ------------------------------------------------------------
# .env
# ------------------------------------------------------------

if [ -f .env ]; then

    echo ".env already exists - using it as-is."

else

    if [ -z "${DATABASE_URL:-}" ] || [ -z "${API_KEY:-}" ]; then

        echo
        echo "No .env file found, and DATABASE_URL / API_KEY were not"
        echo "provided as environment variables."
        echo
        echo "Run it like this instead:"
        echo '  DATABASE_URL="postgresql://user:pass@host:5432/dbname" \'
        echo '  API_KEY="your-key" \'
        echo '  ./deploy.sh'
        echo
        echo "(Or copy .env.example to .env and fill it in by hand first.)"
        exit 1

    fi

    echo "Creating .env from the values you passed in..."

    {
        echo "DATABASE_URL=\"${DATABASE_URL}\""
        echo "API_KEY=\"${API_KEY}\""

        if [ -n "${DB_NETWORK:-}" ]; then
            echo "DB_NETWORK=\"${DB_NETWORK}\""
        fi

        if [ -n "${WEB_PORT:-}" ]; then
            echo "WEB_PORT=\"${WEB_PORT}\""
        fi

    } > .env

    echo ".env created."

fi

# ------------------------------------------------------------
# Optional external DB network
# ------------------------------------------------------------

COMPOSE_FILES=(-f docker-compose.yml)

# .env is also read automatically by `docker compose` itself for
# ${VAR} substitution, so DB_NETWORK works whether it came from this
# shell invocation or was already sitting in an existing .env.
if [ -z "${DB_NETWORK:-}" ] && [ -f .env ]; then
    DB_NETWORK="$(grep -E '^DB_NETWORK=' .env | cut -d= -f2- | tr -d '"' || true)"
fi

if [ -n "${DB_NETWORK:-}" ]; then

    echo "Attaching to external Docker network: ${DB_NETWORK}"

    if ! docker network inspect "${DB_NETWORK}" &> /dev/null; then

        echo
        echo "WARNING: Docker network '${DB_NETWORK}' does not exist"
        echo "on this machine yet. Find the correct name with:"
        echo "  docker network ls"
        echo "Continuing anyway - 'docker compose up' will fail below"
        echo "if this name is wrong."
        echo

    fi

    export DB_NETWORK
    COMPOSE_FILES+=(-f docker-compose.network.yml)

fi

# ------------------------------------------------------------
# Build and run
# ------------------------------------------------------------

echo
echo "Building and starting..."
echo

docker compose "${COMPOSE_FILES[@]}" up -d --build

# ------------------------------------------------------------
# Optional device seeding
#
# Runs as a one-off container using the same image/env/network as
# the real services, so it reaches the devices exactly like the
# collector does - no separate network config needed for this step.
# ------------------------------------------------------------

if [ -n "${DEVICES:-}" ]; then

    echo
    echo "Registering devices from DEVICES..."
    echo

    docker compose "${COMPOSE_FILES[@]}" run --rm web \
        python3 seed_devices.py "${DEVICES}"

fi

if [ -z "${WEB_PORT:-}" ] && [ -f .env ]; then
    WEB_PORT="$(grep -E '^WEB_PORT=' .env | cut -d= -f2- | tr -d '"' || true)"
fi

WEB_PORT="${WEB_PORT:-5050}"

echo
echo "============================================================"
echo "Done."
echo "============================================================"
echo
echo "Dashboard : http://<this-server>:${WEB_PORT}"
echo "API docs  : http://<this-server>:${WEB_PORT}/api/docs"
echo
echo "Status : docker compose ps"
echo "Logs   : docker compose logs -f web"
echo "         docker compose logs -f collector"
