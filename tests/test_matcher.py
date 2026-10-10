"""Offline tests for matcher scoring. Run: .venv/bin/python tests/test_matcher.py"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web.api.matcher import Match, TrackQuery, blocked_words, pick_best, score_candidate, ytdlp_download_options

PASS = []

def check(name, condition):
    PASS.append((name, bool(condition)))
    print(f"{'ok  ' if condition else 'FAIL'} {name}")

def song(title, duration, artists, album="Some Album", source="ytmusic"):
    return Match(video_id="x", title=title, duration=duration, score=0.0,
                 source=source, artists=artists, album=album)

query = TrackQuery(
    name="Do I Wanna Know?",
    artist="Arctic Monkeys",
    album="AM",
    duration_ms=272_000,  # 4:32
)

# 1. Exact official upload should be accepted with a high score.
good = song("Do I Wanna Know?", 273, ["Arctic Monkeys"])
score = score_candidate(query, good)
check("exact match accepted", score is not None and score > 70)

# 2. Music video with a blocklisted word should be rejected.
video = song("Arctic Monkeys - Do I Wanna Know? (Official Video)", 312, ["Arctic Monkeys"])
check("official video rejected", score_candidate(query, video) is None)

# 3. Live version rejected.
live = song("Do I Wanna Know? (Live at Reading)", 240, ["Arctic Monkeys"])
check("live version rejected", score_candidate(query, live) is None)

# 3b. A different song by the same artist is rejected (duration far off).
other_song = song("Stop The World I Wanna Get Off With You", 192, ["Arctic Monkeys"])
check("different song by same artist rejected", score_candidate(query, other_song) is None)

# 4. Version length far beyond tolerance rejected.
cover = song("Do I Wanna Know?", 500, ["Some Cover Band"])
check("wrong length rejected", score_candidate(query, cover) is None)

# 5. Wrong artist scores lower than right artist.
right = score_candidate(query, song("Do I Wanna Know?", 273, ["Arctic Monkeys"]))
wrong_artist = score_candidate(query, song("Do I Wanna Know?", 273, ["Karaoke Hits Band"]))
check("artist match scores higher", right is not None and wrong_artist is not None and right > wrong_artist)

# 6. A song whose real title contains a blocklist word is not blocked.
spotify_live = TrackQuery(name="Live and Let Die", artist="Paul McCartney", duration_ms=190_000)
keep = score_candidate(spotify_live, song("Live and Let Die", 190, ["Paul McCartney"]))
check("title word allowed when Spotify title uses it", keep is not None)
check("blocklist removed that word", "live" not in blocked_words(spotify_live))

# 7. pick_best chooses the closest duration among acceptable candidates.
closest = song("Do I Wanna Know?", 271, ["Arctic Monkeys"])
off = song("Do I Wanna Know? (Remastered 2013)", 285, ["Arctic Monkeys"])
best = pick_best(query, [off, closest])
check("closest duration wins", best is closest)

# 8. Everyone rejected -> None.
check("no acceptable candidates -> None", pick_best(query, [video, live]) is None)

# 9. Normalization: punctuation and features.
feat = TrackQuery(name="Lovely", artist="Billie Eilish;Khalid", duration_ms=200_000)
feat_candidate = song("Lovely (with Khalid)", 200, ["Billie Eilish", "Khalid"], source="ytmusic")
check("featured artist match accepted", score_candidate(feat, feat_candidate) is not None)

# 10. Output format options.
m4a_opts = ytdlp_download_options("out", "m4a", "320")
check("m4a prefers the AAC stream", m4a_opts["format"].startswith("bestaudio[ext=m4a]"))
check("m4a postprocessor targets m4a", m4a_opts["postprocessors"][0]["preferredcodec"] == "m4a")
mp3_opts = ytdlp_download_options("out", "mp3", "320")
check("mp3 postprocessor targets mp3", mp3_opts["postprocessors"][0]["preferredcodec"] == "mp3")
check("mp3 keeps the requested quality", mp3_opts["postprocessors"][0]["preferredquality"] == "320")
check("unknown format falls back to m4a",
      ytdlp_download_options("out", "flac", "320")["postprocessors"][0]["preferredcodec"] == "m4a")

failed = [name for name, ok in PASS if not ok]
print(f"\n{len(PASS) - len(failed)}/{len(PASS)} passed")
sys.exit(1 if failed else 0)
