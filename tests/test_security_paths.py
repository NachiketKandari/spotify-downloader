"""Offline security checks for the file and ZIP endpoints.
Run: .venv/bin/python tests/test_security_paths.py

These assert the endpoints reject empty ids, path traversal, and cross-user
access BEFORE touching the filesystem, and that the custom output path is
off unless explicitly enabled.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from web.api.main import app, custom_output_allowed

client = TestClient(app)
checks = []


def check(name, condition):
    checks.append((name, bool(condition)))
    print(f"{'ok  ' if condition else 'FAIL'} {name}")


# 1. Empty user ids are rejected everywhere (they used to address downloads/).
check("file: empty user_id -> 400", client.get("/api/file?path=x/y.m4a&user_id=").status_code == 400)
check("zip: empty user_id -> 400", client.get("/api/zip?user_id=").status_code == 400)
check("playlist-zip: empty user_id -> 400", client.get("/api/playlist-zip?user_id=&playlist=x").status_code == 400)
check(
    "link-download: empty user_id -> 400",
    client.post("/api/link-download?user_id=", json={"url": "https://open.spotify.com/playlist/abc"}).status_code == 400,
)
check(
    "csv-download: id that filters to empty -> 400",
    client.post("/api/csv-download", data={"user_id": "!!!"}, files={"file": ("x.csv", b"Track Name\nsong", "text/csv")}).status_code == 400,
)

# 2. Traversal is rejected even with a valid-looking user id.
check("file: ../ escape -> 403", client.get("/api/file?path=../downloaded_songs.json&user_id=e2e").status_code == 403)
check("file: nested .. escape -> 403", client.get("/api/file?path=e2e/../../downloaded_songs.json&user_id=e2e").status_code == 403)

# 3. Prefix-matching ids cannot read another user's folder.
check("file: cross-user prefix -> 403", client.get("/api/file?path=e2e_test_user/x.m4a&user_id=e2e").status_code == 403)

# 4. Missing file for the right user is a clean 404.
check("file: missing file -> 404", client.get("/api/file?path=e2e_test_user/x.m4a&user_id=e2e_test_user").status_code == 404)

# 5. An empty x-user-id header must not start a job on the downloads root.
download_code = client.post(
    "/api/download", headers={"x-user-id": ""}, json={"playlists": []}
).status_code
check("download: empty x-user-id rejected", download_code in (400, 422))

# 6. Custom output paths are off unless explicitly enabled.
os.environ.pop("ALLOW_CUSTOM_OUTPUT_PATH", None)
check("custom output disabled by default", custom_output_allowed() is False)
os.environ["ALLOW_CUSTOM_OUTPUT_PATH"] = "1"
check("custom output enabled with env", custom_output_allowed() is True)
os.environ.pop("ALLOW_CUSTOM_OUTPUT_PATH")

# 7. The shared validator rejects empty and symbol-only ids directly.
from fastapi import HTTPException
from web.api.main import validated_user_id

for bad in ("", "!!!", "   "):
    try:
        validated_user_id(bad)
        ok = False
    except HTTPException:
        ok = True
    check(f"validator rejects {bad!r}", ok)

failed = [name for name, ok in checks if not ok]
print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
sys.exit(1 if failed else 0)
