"""Offline checks for the paste-link CSV export (/api/link-csv).
Run: .venv/bin/python tests/test_link_csv.py

Covers: column format, quoting, round-trip through the CSV upload parser,
selection filtering, and error cases.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from web.api import link_download
from web.api.main import app, parse_csv_tracks
from web.api.matcher import TrackQuery

client = TestClient(app)
checks = []


def check(name, condition):
    checks.append((name, bool(condition)))
    print(f"{'ok  ' if condition else 'FAIL'} {name}")


def track(i):
    return TrackQuery(
        name=f"Song {i}",
        artist='Artist A;Artist "B"' if i == 0 else f"Artist {i}",
        album=f"Album {i}",
        duration_ms=200_000 + i,
        cover_url=f"https://example.com/{i}.jpg",
        release_date="2020-01-01",
        track_number=i + 1,
        total_tracks=3,
        explicit=(i == 0),
        uri=f"spotify:track:abc{i}",
    )


tracks = [track(0), track(1), track(2)]

# 1. CSV shape: header + one row per track, RFC-style quoting.
csv_text = link_download.tracks_to_csv(tracks)
lines = csv_text.strip().split("\n")
check("header row matches the Dashboard/Exportify columns",
      lines[0] == "Track URI,Track Name,Artist Name(s),Album Name,Album Artist Name(s),"
                  "Album Image URL,Album Release Date,Duration (ms),Track Number,"
                  "Total Tracks,Explicit")
check("one row per track plus header", len(lines) == 4)
check("quotes are escaped and fields quoted", '"Artist A;Artist ""B"""' in csv_text)
check("explicit true/false written", ",true" in csv_text and ",false" in csv_text)

# 2. Round-trip: the file must re-upload through the CSV parser.
parsed = parse_csv_tracks(csv_text.encode("utf-8"))
check("round-trip keeps all tracks", len(parsed) == 3)
check("round-trip keeps uri", parsed[0].uri == "spotify:track:abc0")
check("round-trip keeps name", parsed[1].name == "Song 1")
check("round-trip keeps multi-artist", parsed[0].artist == 'Artist A;Artist "B"')
check("round-trip keeps duration", parsed[0].duration_ms == 200_000)
check("round-trip keeps explicit", parsed[0].explicit is True and parsed[1].explicit is False)
check("round-trip keeps track number", parsed[2].track_number == 3)

# 3. Endpoint with a cached preview + selection filter.
link_download.PREVIEW_CACHE["csvtest"] = {"name": "My Test Playlist", "tracks": tracks, "warning": None}
try:
    res = client.get("/api/link-csv?preview_token=csvtest")
    check("endpoint returns 200", res.status_code == 200)
    check("content type is csv", res.headers["content-type"].startswith("text/csv"))
    check("disposition names the playlist",
          "My Test Playlist.csv" in res.headers.get("content-disposition", "").replace("_", " ")
          or "My%20Test%20Playlist.csv" in res.headers.get("content-disposition", ""))
    check("all three tracks exported", len(res.text.strip().split("\n")) == 4)

    res = client.get("/api/link-csv?preview_token=csvtest&selected=0,2")
    body = res.text.strip().split("\n")
    check("selection exports only chosen rows", len(body) == 3)
    check("selection keeps the right rows", "Song 0" in body[1] and "Song 2" in body[2])

    res = client.get("/api/link-csv?preview_token=csvtest&selected=99")
    check("out-of-range selection -> 400", res.status_code == 400)

    # 4. Error cases.
    check("no token and no url -> 400", client.get("/api/link-csv").status_code == 400)
    check("bad url -> 400", client.get("/api/link-csv?url=https://example.com/x").status_code == 400)
finally:
    link_download.PREVIEW_CACHE.pop("csvtest", None)

failed = [name for name, ok in checks if not ok]
print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
sys.exit(1 if failed else 0)
