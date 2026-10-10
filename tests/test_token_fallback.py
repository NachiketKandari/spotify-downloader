"""Offline checks that a rejected login token is reported instead of being
silently downgraded to the anonymous embed page.
Run: .venv/bin/python tests/test_token_fallback.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web.api import link_download

checks = []


def check(name, condition):
    checks.append((name, bool(condition)))
    print(f"{'ok  ' if condition else 'FAIL'} {name}")


URL = "https://open.spotify.com/playlist/37i9dQZF1EIW3RER8uUu7l"


def fake_track(i):
    return link_download.TrackQuery(name=f"Track {i}", artist="Artist", duration_ms=1000)


def token_fails(url, token):
    raise RuntimeError("401 Unauthorized")


def embed_ok(url):
    return (
        "Public Playlist",
        [fake_track(1), fake_track(2)],
        "Spotify's embed page only lists the first 50 tracks. Log in and paste the link to get the full list.",
    )


def both_break(url, token):
    raise RuntimeError("403 Forbidden")


def embed_fails(url):
    raise RuntimeError("embed down")


saved_token_resolver = link_download._resolve_with_user_token
saved_embed_resolver = link_download._resolve_with_embed

try:
    # 1. A token was sent but rejected -> the warning must explain it.
    link_download._resolve_with_user_token = token_fails
    link_download._resolve_with_embed = embed_ok
    name, tracks, warning = link_download.resolve_playlist(URL, user_token="stale")
    check("token rejection surfaces in the warning", "login could not be used" in (warning or ""))
    check("warning carries the actual error", "401" in (warning or ""))
    check("warning suggests logging in again", "log out and log in again" in (warning or "").lower())
    check("tracks still returned (graceful fallback)", len(tracks) == 2)

    # 1b. Editorial playlists: a 404 gets its own explanation (not "log in").
    def token_404(url, token):
        raise RuntimeError("404 Resource not found")

    link_download._resolve_with_user_token = token_404
    name, tracks, warning = link_download.resolve_playlist(URL, user_token="fine")
    check("404 gets the editorial-playlist explanation", "editorial" in (warning or ""))
    check("404 warning does not send the user to re-login", "log out and log in" not in (warning or "").lower())
    check("404 warning points at the CSV route", "Exportify" in (warning or ""))

    # 2. No token -> the plain anonymous warning is unchanged.
    name, tracks, warning = link_download.resolve_playlist(URL)
    check("anonymous path keeps the plain warning", "first 50 tracks" in (warning or ""))
    check("anonymous warning does not blame a login", "login could not be used" not in (warning or ""))

    # 3. A working token -> all tracks, no warning.
    link_download._resolve_with_user_token = lambda url, token: (
        "Full Playlist",
        [fake_track(i) for i in range(137)],
        None,
    )
    name, tracks, warning = link_download.resolve_playlist(URL, user_token="fresh")
    check("working token returns all tracks", len(tracks) == 137)
    check("working token emits no warning", warning is None)

    # 4. Both paths fail -> the raised error names both causes.
    link_download._resolve_with_user_token = both_break
    link_download._resolve_with_embed = embed_fails
    try:
        link_download.resolve_playlist(URL, user_token="stale")
        raised = False
    except RuntimeError as e:
        raised = "login token failed" in str(e) and "embed page failed" in str(e)
    check("total failure reports both causes", raised)
finally:
    link_download._resolve_with_user_token = saved_token_resolver
    link_download._resolve_with_embed = saved_embed_resolver

failed = [name for name, ok in checks if not ok]
print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
sys.exit(1 if failed else 0)
