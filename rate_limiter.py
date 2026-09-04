"""
Shared Flask-Limiter instance for the read side (app.py / api.py).

Keyed on the caller's API key when present, so each key gets its
own budget instead of every client sharing one global limit;
falls back to remote IP for requests with no key (the HTML pages,
or an unauthenticated API call that's about to get a 401 anyway).

In-memory storage - per-process, resets on restart. Fine for a
single-process deployment; if this is ever run with multiple
worker processes, each enforces its own separate limit rather than
a shared one (same caveat as the TTL cache in web_database.py).
"""

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _rate_limit_key():

    api_key = (
        request.headers.get("X-API-Key")
        or request.args.get("api_key")
    )

    return api_key or get_remote_address()


limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=["200 per minute"],
)
