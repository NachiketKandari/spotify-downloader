"""
Optional shared-password guard for the whole API.

When OFFLINEIFY_PASSWORD is set (env), every HTTP request must prove it knows
the password, using standard HTTP Basic:

- `Authorization: Basic base64(user:password)` — what the web UI and
  `curl -u anything:password` send. The username is ignored: there is one
  shared password and one shared token.
- `?key=base64(user:password)` — for download links opened via `<a href>` or
  `window.open()`, which cannot set headers.
- `X-API-Key: base64(user:password)` — convenient for scripts.

CORS preflights (OPTIONS) bypass the check so browsers can talk to the API.
When the variable is unset the API stays open — the right default for a laptop.
"""

import base64
import os
import secrets
from urllib.parse import parse_qs

from starlette.responses import PlainTextResponse


def _password() -> str:
    return os.environ.get("OFFLINEIFY_PASSWORD", "")


def _password_from(raw: str) -> str | None:
    """Decode a base64 "user:password" token; returns the password or None."""
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
    except Exception:
        return None
    if ":" not in decoded:
        return None
    return decoded.split(":", 1)[1]


def _provided_password(scope) -> str | None:
    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}

    auth = headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        return _password_from(auth.split(" ", 1)[1].strip())

    api_key = headers.get("x-api-key")
    if api_key:
        return _password_from(api_key)

    query = parse_qs(scope.get("query_string", b"").decode())
    key = (query.get("key") or [""])[0]
    if key:
        return _password_from(key)

    return None


class PasswordGuard:
    """Pure ASGI middleware, so streaming responses are untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        password = _password()
        if not password or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)

        provided = _provided_password(scope)
        if provided is not None and secrets.compare_digest(provided.encode(), password.encode()):
            return await self.app(scope, receive, send)

        response = PlainTextResponse(
            "Unauthorized — this server needs its access password.",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Offlineify"'},
        )
        return await response(scope, receive, send)
