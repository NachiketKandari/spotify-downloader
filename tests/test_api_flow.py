"""End-to-end test of the API file/zip flow using FastAPI's TestClient.
Run: .venv/bin/python tests/test_api_flow.py

It downloads two real tracks through the normal /api/download pipeline
(no Spotify login needed), checks the dedupe cache, then checks that
/api/file and /api/zip deliver and delete files from the server.
"""

import io
import os
import shutil
import sys
import zipfile

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

payload = {"playlists": [{"name": "E2E Playlist", "tracks": TRACKS}], "format": "m4a"}

response = client.post("/api/download", headers={"x-user-id": USER}, json=payload)
print("POST /api/download ->", response.status_code, response.json())

status = client.get(f"/api/status?user_id={USER}").json()
print("job status:", status["status"], f"{status['completed']}/{status['total']}")
for log in status["logs"]:
    print("  log:", log)

assert status["status"] == "done", "job did not finish"
assert status["completed"] == 2, "not all tracks processed"
assert len(status["completed_files"]) == 2, "expected 2 playable files"

# Re-running the same tracks should hit the cache and finish instantly.
response = client.post("/api/download", headers={"x-user-id": USER}, json=payload)
status = client.get(f"/api/status?user_id={USER}").json()
skipped = sum(1 for log in status["logs"] if log.startswith("Skipped"))
print(f"second run: {skipped}/2 skipped via cache, status={status['status']}")
assert status["status"] == "done" and skipped == 2

# Per-file download (this is what the browser "Save" link hits) must deliver
# the file and then remove it from the server.
file_path = status["completed_files"][0]["path"]
file_response = client.get(f"/api/file?path={file_path}&user_id={USER}")
print("GET /api/file ->", file_response.status_code, len(file_response.content), "bytes")
assert file_response.status_code == 200 and len(file_response.content) > 100_000
assert not os.path.exists(os.path.join("downloads", file_path)), "saved file was not deleted"

# ZIP streams whatever is left and clears the user folder afterwards.
zip_response = client.get(f"/api/zip?user_id={USER}")
print("GET /api/zip ->", zip_response.status_code, len(zip_response.content), "bytes")
assert zip_response.status_code == 200 and zip_response.content[:2] == b"PK"
names = zipfile.ZipFile(io.BytesIO(zip_response.content)).namelist()
print("zip entries:", names)
assert len(names) >= 2, "zip should contain the remaining file and the m3u8"

user_dir = os.path.join("downloads", USER)
assert not any(files for _, _, files in os.walk(user_dir)), "user folder was not cleared after ZIP"
print("user folder cleared after ZIP delivery")

# A second ZIP attempt finds nothing to send.
again = client.get(f"/api/zip?user_id={USER}")
print("second GET /api/zip ->", again.status_code)
assert again.status_code == 404

print("\nAPI flow OK")
