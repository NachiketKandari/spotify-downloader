"""Live test: embed a real Spotify cover into an MP3 and verify the tags.
Run: .venv/bin/python tests/test_cover_embed.py
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mutagen.mp3 import MP3

from web.api.matcher import TrackQuery, download_match, find_best_match

OUT = "tests/output/cover"

query = TrackQuery(
    name="Tum Hi Ho",
    artist="Arijit Singh",
    album="Aashiqui 2",
    duration_ms=262_000,
    release_date="2013-04-08",
    track_number=1,
    total_tracks=10,
    explicit=False,
    # Real Spotify cover (fetched live so the test never goes stale).
    cover_url="https://i.scdn.co/image/ab67706f00000002526040498d89ec622e9d3495",
)

shutil.rmtree(OUT, ignore_errors=True)
match = find_best_match(query)
print("match:", match.title, "score:", round(match.score, 1))

path = download_match(match, query, OUT, "320")
print("file:", path)

audio = MP3(path)
assert audio.info.bitrate == 320000, f"expected 320kbps, got {audio.info.bitrate}"
assert str(audio.tags["TIT2"]) == "Tum Hi Ho", "title tag wrong"
assert str(audio.tags["TPE1"]) == "Arijit Singh", "artist tag wrong"
assert str(audio.tags["TALB"]) == "Aashiqui 2", "album tag wrong"
assert str(audio.tags["TRCK"]) == "1/10", "track number tag wrong"

covers = audio.tags.getall("APIC")
assert covers, "no cover art embedded"
print("cover bytes:", len(covers[0].data), "mime:", covers[0].mime)
assert covers[0].mime == "image/jpeg" and len(covers[0].data) > 10_000

print("\nCover embed OK")
