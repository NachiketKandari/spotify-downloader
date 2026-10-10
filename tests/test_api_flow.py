"""End-to-end test of the API file/zip flow using FastAPI's TestClient.
Run: .venv/bin/python tests/test_api_flow.py

It downloads two real tracks through the normal /api/download pipeline
(no Spotify login needed), then checks /api/file and /api/zip.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from web.api.main import app

USER = "e2e_test_user"
TRACKS = [
    {
        "uri": "spotify:track:e2e-tum-hi-ho",
        "name": "Tum Hi Ho",
        "artist": "Arijit Singh",
        "album": "Aashiqui 2",
        "duration_ms": 262_000,
        "release_date": "2013-04-08",
        "track_number": 1,
        "total_tracks": 10,
        "explicit": False,
    },
    {
        "uri": "spotify:track:e2e-blinding-lights",
        "name": "Blinding Lights",
        "artist": "The Weeknd",
        "album": "After Hours",
        "duration_ms": 200_000,
        "release_date": "2020-03-20",
        "track_number": 9,
        "total_tracks": 14,
        "explicit": False,
    },
]

# fresh state
shutil.rmtree(os.path.join("downloads", USER), ignore_errors=True)

client = TestClient(app)

response = client.post(
    "/api/download",
    headers={"x-user-id": USER},
    json={"playlists": [{"name": "E2E Playlist", "tracks": TRACKS}], "quality": "320"},
)
print("POST /api/download ->", response.status_code, response.json())

status = client.get(f"/api/status?user_id={USER}").json()
print("job status:", status["status"], f"{status['completed']}/{status['total']}")
for log in status["logs"]:
    print("  log:", log)

assert status["status"] == "done", "job did not finish"
assert status["completed"] == 2, "not all tracks processed"
assert len(status["completed_files"]) == 2, "expected 2 playable files"

# Per-file download (this is what the browser "Save" link hits).
file_path = status["completed_files"][0]["path"]
file_response = client.get(f"/api/file?path={file_path}&user_id={USER}")
print("GET /api/file ->", file_response.status_code, len(file_response.content), "bytes")
assert file_response.status_code == 200 and len(file_response.content) > 100_000

# ZIP of the whole user folder (login/CSV flows use this).
zip_response = client.get(f"/api/zip?user_id={USER}")
print("GET /api/zip ->", zip_response.status_code, len(zip_response.content), "bytes")
assert zip_response.status_code == 200 and zip_response.content[:2] == b"PK"

# Re-running the same tracks should hit the cache and finish instantly.
response = client.post(
    "/api/download",
    headers={"x-user-id": USER},
    json={"playlists": [{"name": "E2E Playlist", "tracks": TRACKS}], "quality": "320"},
)
status = client.get(f"/api/status?user_id={USER}").json()
skipped = sum(1 for log in status["logs"] if log.startswith("Skipped"))
print(f"second run: {skipped}/2 skipped via cache, status={status['status']}")
assert status["status"] == "done" and skipped == 2

print("\nAPI flow OK")
