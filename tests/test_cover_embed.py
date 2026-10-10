"""Live test: embed a real Spotify cover into an MP3 download and into an M4A
file, then verify the tags on both.
Run: .venv/bin/python tests/test_cover_embed.py
"""

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

from web.api.matcher import Match, TrackQuery, download_match, find_best_match, write_tags

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
os.makedirs(OUT, exist_ok=True)

# ---- M4A tagging (synthetic file, no download needed) ---------------------

m4a_path = os.path.join(OUT, "tag-target.m4a")
subprocess.run(
    ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc", "-t", "1", "-c:a", "aac", m4a_path],
    check=True,
    capture_output=True,
)
synthetic_match = Match(video_id="x", title="Tum Hi Ho", duration=262, score=100.0,
                        source="ytmusic", artists=["Arijit Singh"], album="Aashiqui 2")
write_tags(m4a_path, query, synthetic_match)

audio = MP4(m4a_path)
assert str(audio.tags["\xa9nam"][0]) == "Tum Hi Ho", "m4a title tag wrong"
assert str(audio.tags["\xa9ART"][0]) == "Arijit Singh", "m4a artist tag wrong"
assert str(audio.tags["\xa9alb"][0]) == "Aashiqui 2", "m4a album tag wrong"
assert audio.tags["trkn"][0] == (1, 10), "m4a track number tag wrong"
covers = audio.tags.get("covr")
assert covers and len(covers[0]) > 10_000, "no m4a cover art embedded"
print("M4A tags OK — cover:", len(covers[0]), "bytes")

# ---- MP3 download + tagging (full live path) ------------------------------

mp3_dir = os.path.join(OUT, "mp3")
match = find_best_match(query)
print("match:", match.title, "score:", round(match.score, 1))

path = download_match(match, query, mp3_dir, quality="320", fmt="mp3")
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
