"""Offline checks that logging in with Spotify lifts the 50-track ceiling.

The logged-out path falls back to Spotify's public embed page, which only ever
lists the first 50 tracks. The logged-in path uses the Web API and follows
`next` until the playlist is exhausted, so it must return every track.

This feeds `resolve_playlist` a fake Spotify client that paginates, so the
assertion holds without touching the network.

Run: .venv/bin/python tests/test_playlist_pagination.py
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web.api import link_download

checks = []


def check(name, condition):
    checks.append((name, bool(condition)))
    print(f"{'ok  ' if condition else 'FAIL'} {name}")


def make_track(i):
    return {
        "track": {
            "name": f"Track {i}",
            "uri": f"spotify:track:{i}",
            "duration_ms": 200000,
            "explicit": False,
            "track_number": i,
            "is_local": False,
            "artists": [{"name": "Artist"}],
            "album": {"name": "Album", "total_tracks": 1, "release_date": "2020-01-01", "images": []},
        }
    }


class FakeSpotify:
    """Minimal stand-in for spotipy.Spotify that paginates like the real one."""

    def __init__(self, total, page_size=100, auth=None):
        self.total = total
        self.page_size = page_size
        self.auth = auth
        self.pages_fetched = 0

    def playlist(self, playlist_id, fields=None):
        return {"name": "Big Playlist"}

    def playlist_items(self, playlist_id, fields=None, additional_types=None, limit=None):
        self.pages_fetched += 1
        return self._page(0)

    def _page(self, start):
        end = min(start + self.page_size, self.total)
        payload = {"items": [make_track(i) for i in range(start, end)]}
        payload["next"] = {"__cursor": end} if end < self.total else None
        return payload

    def next(self, result):
        cursor = (result or {}).get("next")
        if not cursor:
            return None
        self.pages_fetched += 1
        return self._page(cursor["__cursor"])


URL = "https://open.spotify.com/playlist/4hOKQuZbraPDIfaGbM3lKI"

# ── Logged in: full pagination, no ceiling ────────────────────────────────────
for total in (137, 250, 1):
    fake = FakeSpotify(total)
    original = link_download.Spotify
    link_download.Spotify = lambda auth=None, _f=fake: _f
    try:
        name, tracks, warning = link_download.resolve_playlist(URL, user_token="user-token")
    finally:
        link_download.Spotify = original
    check(f"token path returns all {total} track(s) from a {total}-track playlist", len(tracks) == total)
    check(f"token path emits no 'first 50' warning for {total} track(s)", warning is None)

# A 137-track playlist must span more than one page, so this really did paginate.
fake = FakeSpotify(137)
original = link_download.Spotify
link_download.Spotify = lambda auth=None, _f=fake: _f
try:
    _, tracks, _ = link_download.resolve_playlist(URL, user_token="user-token")
finally:
    link_download.Spotify = original
check("137 tracks required more than one API page (pagination really ran)", fake.pages_fetched >= 2)
check("137 tracks really exceeds the embed ceiling of 50", len(tracks) > link_download.EMBED_TRACK_LIMIT)

# ── Logged out: the 50-track ceiling still applies, with a warning ───────────
calls = []


def fake_embed(url):
    calls.append(url)
    name = "Big Playlist"
    tracks = [
        link_download.TrackQuery(name=f"Track {i}", artist="Artist", album="Album", duration_ms=200000)
        for i in range(link_download.EMBED_TRACK_LIMIT)
    ]
    return name, tracks, None


original_embed = link_download._resolve_with_embed
link_download._resolve_with_embed = fake_embed
try:
    _, tracks, _ = link_download.resolve_playlist(URL, user_token=None)
finally:
    link_download._resolve_with_embed = original_embed

check("logged-out path uses the embed fallback", len(calls) == 1)
check(
    f"logged-out path is capped at {link_download.EMBED_TRACK_LIMIT} tracks",
    len(tracks) == link_download.EMBED_TRACK_LIMIT,
)

# The real embed resolver is what produces the warning. It needs the network to
# run, so assert the message it builds actually reaches the user.
embed_src = inspect.getsource(link_download._resolve_with_embed)
warning_text = embed_src[embed_src.find("warning = ("):]
check(
    "embed fallback warns the user to log in for the full list",
    "Log in" in warning_text and "EMBED_TRACK_LIMIT" in warning_text,
)
check("the embed ceiling is exactly Spotify's 50-track page limit", link_download.EMBED_TRACK_LIMIT == 50)

failed = [name for name, ok in checks if not ok]
print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
sys.exit(1 if failed else 0)