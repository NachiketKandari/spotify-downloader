"""Live test: match real tracks against YouTube Music and inspect the winner.
Run: .venv/bin/python tests/test_live_match.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web.api.matcher import TrackQuery, find_best_match

TRACKS = [
    TrackQuery(name="Do I Wanna Know?", artist="Arctic Monkeys", album="AM", duration_ms=272_000),
    TrackQuery(name="Kesariya", artist="Arijit Singh", album="Brahmastra", duration_ms=268_000),
    TrackQuery(name="Blinding Lights", artist="The Weeknd", album="After Hours", duration_ms=200_000),
    TrackQuery(name="Tum Hi Ho", artist="Arijit Singh", album="Aashiqui 2", duration_ms=262_000),
]

for query in TRACKS:
    match = find_best_match(query)
    if match is None:
        print(f"NO MATCH  {query.artist} - {query.name}")
        continue
    diff = abs((query.duration_s or 0) - (match.duration or 0))
    print(f"MATCHED   {query.artist} - {query.name}")
    print(f"          -> [{match.source}] {match.title}")
    print(f"          duration diff: {diff:.0f}s, score: {match.score:.1f}, video: {match.video_id}")
