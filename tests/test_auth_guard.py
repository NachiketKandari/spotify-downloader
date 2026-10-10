"""Offline checks for the optional shared-password guard (OFFLINEIFY_PASSWORD).
Run: .venv/bin/python tests/test_auth_guard.py
"""

import base64
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from web.api.main import app

client = TestClient(app)
checks = []


def check(name, condition):
    checks.append((name, bool(condition)))
    print(f"{'ok  ' if condition else 'FAIL'} {name}")


def basic(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


token = base64.b64encode(b"offlineify:sekret").decode()

# Unset -> the API is open (laptop default).
os.environ.pop("OFFLINEIFY_PASSWORD", None)
check("open when no password is configured", client.get("/api/status").status_code == 200)

os.environ["OFFLINEIFY_PASSWORD"] = "sekret"
try:
    check("401 without credentials", client.get("/api/status").status_code == 401)
    check(
        "401 advertises WWW-Authenticate",
        client.get("/api/status").headers.get("www-authenticate", "").startswith("Basic"),
    )
    check("correct Basic header accepted", client.get("/api/status", headers=basic("offlineify", "sekret")).status_code == 200)
    check("username is ignored", client.get("/api/status", headers=basic("anything", "sekret")).status_code == 200)
    check("wrong password rejected", client.get("/api/status", headers=basic("offlineify", "nope")).status_code == 401)
    check("malformed Basic header rejected", client.get("/api/status", headers={"Authorization": "Basic not*base64"}).status_code == 401)
    check("?key= accepted (download links)", client.get(f"/api/status?key={token}").status_code == 200)
    check("wrong key rejected", client.get("/api/status?key=nope").status_code == 401)
    check("X-API-Key accepted (scripts)", client.get("/api/status", headers={"X-API-Key": token}).status_code == 200)
    check(
        "CORS preflight bypasses the guard",
        client.options(
            "/api/status",
            headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
        ).status_code
        in (200, 204),
    )
    check(
        "401 keeps CORS headers so browsers see it",
        client.get("/api/status", headers={"Origin": "https://example.com"}).headers.get("access-control-allow-origin")
        == "https://example.com",
    )
finally:
    os.environ.pop("OFFLINEIFY_PASSWORD", None)

check("open again after password removed", client.get("/api/status").status_code == 200)

failed = [name for name, ok in checks if not ok]
print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
sys.exit(1 if failed else 0)
