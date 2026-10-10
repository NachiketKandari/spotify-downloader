"""
Resolve a pasted Spotify playlist link into track metadata.

Two sources, in order:
1. The logged-in user's token (sent by the UI when signed in). Reads anything
   the user can see, including private playlists, without track-count limits.
2. The public embed page. No auth needed, but lists only the first 50 tracks.

App-only (client credentials) access is deliberately not used: Spotify blocks
playlist endpoints for that grant type on most apps.

Once the tracks are known, `run_link_job` hands each one to `matcher.py`.
"""

import html as html_module
import json
import os
import random
import re
import time
from typing import List, Optional, Tuple

import requests
from spotipy import Spotify

from .matcher import TrackQuery, download_match, find_best_match

DOWNLOAD_ROOT = "downloads"

# Accepts open.spotify.com/playlist/..., /intl-xx/playlist/... and spotify:playlist:...
PLAYLIST_URL_RE = re.compile(
    r"^(https?://open\.spotify\.com/(intl-[a-z\-]+/)?playlist/[A-Za-z0-9]+(\?.*)?|spotify:playlist:[A-Za-z0-9]+)$"
)

SPOTIFY_PAGE_LIMIT = 100
EMBED_TRACK_LIMIT = 50  # Spotify's embed page shows at most this many tracks

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def is_playlist_url(url: str) -> bool:
    return bool(PLAYLIST_URL_RE.match(url.strip()))


def safe_name(value: str) -> str:
    cleaned = "".join(c for c in value if c.isalnum() or c in " -_").strip()
    return cleaned or "playlist"


def _playlist_id(url: str) -> str:
    if url.startswith("spotify:playlist:"):
        return url.rsplit(":", 1)[1]
    return url.split("/playlist/")[1].split("?")[0].split("/")[0]


def _images_first(images) -> Optional[str]:
    if isinstance(images, list) and images:
        return images[0].get("url")
    return None


# ---------------------------------------------------------------------------
# Spotify Web API walker (used by the user-token and app-credentials paths)
# ---------------------------------------------------------------------------

def _walk_playlist(client: Spotify, url: str) -> Tuple[str, List[TrackQuery], Optional[str]]:
    playlist_id = _playlist_id(url)

    meta = client.playlist(playlist_id, fields="name")
    playlist_name = safe_name((meta or {}).get("name") or "Spotify Playlist")

    tracks: List[TrackQuery] = []
    results = client.playlist_items(
        playlist_id,
        fields=(
            "next,items(track(name,duration_ms,uri,explicit,track_number,is_local,"
            "artists(name),album(name,total_tracks,release_date,images)))"
        ),
        additional_types=("track",),
        limit=SPOTIFY_PAGE_LIMIT,
    )
    while results:
        for item in results.get("items", []):
            track = item.get("track") or {}
            if not track.get("name") or track.get("is_local"):
                continue
            album = track.get("album") or {}
            tracks.append(TrackQuery(
                name=track["name"],
                artist=";".join(a["name"] for a in track.get("artists") or []),
                album=album.get("name", ""),
                duration_ms=track.get("duration_ms"),
                cover_url=_images_first(album.get("images")),
                release_date=album.get("release_date"),
                track_number=track.get("track_number"),
                total_tracks=album.get("total_tracks"),
                explicit=track.get("explicit"),
            ))
        results = client.next(results) if results.get("next") else None

    return playlist_name, tracks, None


def _resolve_with_user_token(url: str, token: str) -> Tuple[str, List[TrackQuery], Optional[str]]:
    return _walk_playlist(Spotify(auth=token), url)


# ---------------------------------------------------------------------------
# Source 2: the public embed page (no auth, first 50 tracks)
# ---------------------------------------------------------------------------

def _resolve_with_embed(url: str) -> Tuple[str, List[TrackQuery], Optional[str]]:
    playlist_id = _playlist_id(url)
    resp = requests.get(
        f"https://open.spotify.com/embed/playlist/{playlist_id}",
        headers=BROWSER_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()

    match = NEXT_DATA_RE.search(resp.text)
    if not match:
        raise RuntimeError("Spotify did not return playlist data")

    entity = (
        json.loads(html_module.unescape(match.group(1)))
        .get("props", {}).get("pageProps", {}).get("state", {})
        .get("data", {}).get("entity", {})
    )
    if entity.get("type") != "playlist":
        raise RuntimeError("That link does not point to a playlist")

    playlist_name = safe_name(entity.get("name") or entity.get("title") or "Spotify Playlist")
    cover_url = _images_first((entity.get("coverArt") or {}).get("sources"))

    tracks: List[TrackQuery] = []
    for entry in entity.get("trackList") or []:
        uri = entry.get("uri") or ""
        if not uri.startswith("spotify:track:"):
            continue
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        # "subtitle" looks like "Artist A, Artist B"; drop "(feat. X)" suffixes.
        artist = re.sub(r"\s*\(feat\..*?\)", "", entry.get("subtitle") or "", flags=re.IGNORECASE).strip()
        tracks.append(TrackQuery(
            name=title,
            artist=artist or "Unknown Artist",
            album="",
            duration_ms=entry.get("duration"),
            cover_url=cover_url,
            explicit=entry.get("isExplicit"),
        ))

    warning = None
    if len(tracks) >= EMBED_TRACK_LIMIT:
        warning = (
            f"Spotify's embed page only lists the first {EMBED_TRACK_LIMIT} tracks. "
            "Log in and paste the link (or upload a CSV) to get the full list."
        )
    return playlist_name, tracks, warning


def resolve_playlist(url: str, user_token: Optional[str] = None) -> Tuple[str, List[TrackQuery], Optional[str]]:
    """Return (playlist_name, tracks, warning). Tries the user token, then the embed page."""
    errors = []

    if user_token:
        try:
            return _resolve_with_user_token(url, user_token)
        except Exception as e:
            errors.append(f"login token failed: {e}")

    try:
        return _resolve_with_embed(url)
    except Exception as e:
        errors.append(f"embed page failed: {e}")

    raise RuntimeError("Could not read this playlist. " + " | ".join(errors))


# ---------------------------------------------------------------------------
# Background job
# ---------------------------------------------------------------------------

def run_link_job(state, user_id: str, url: str, quality: str, user_token: Optional[str] = None):
    """Background job: resolve the playlist, then match + download each track."""
    state.status = "working"
    state.logs = []
    state.completed_files = []
    state.completed = 0
    state.total = 0
    state.current_track = "Fetching playlist..."
    state.cancel_requested = False
    state.playlist_dir = ""

    safe_user_id = "".join([c for c in user_id if c.isalnum() or c in ["@", ".", "-", "_"]])

    try:
        playlist_name, tracks, warning = resolve_playlist(url, user_token=user_token)
    except Exception as e:
        state.logs.append(f"Could not read playlist: {e}")
        state.status = "error"
        state.current_track = ""
        return

    if warning:
        state.logs.append(f"Note: {warning}")

    if not tracks:
        state.logs.append("No downloadable tracks found in this playlist")
        state.status = "error"
        state.current_track = ""
        return

    playlist_dir = os.path.join(DOWNLOAD_ROOT, safe_user_id, playlist_name)
    os.makedirs(playlist_dir, exist_ok=True)
    state.playlist_dir = playlist_name
    state.total = len(tracks)
    state.logs.append(f"Playlist: {playlist_name} ({len(tracks)} tracks)")

    for query in tracks:
        if state.cancel_requested:
            state.status = "cancelled"
            state.logs.append("Download cancelled by user")
            state.current_track = ""
            return

        label = f"{query.artist} - {query.name}"
        state.current_track = label

        match = find_best_match(query)
        if match is None:
            state.logs.append(f"No good match found: {label}")
            state.completed += 1
            continue

        # Light delay between real downloads to avoid YouTube rate limits.
        time.sleep(random.uniform(1, 3))

        try:
            file_path = download_match(match, query, playlist_dir, quality)
        except Exception as e:
            state.logs.append(f"Error {label}: {e}")
            state.completed += 1
            continue

        if file_path is None:
            state.logs.append(f"No match found: {label}")
        else:
            state.logs.append(f"Downloaded: {label}")
            state.completed_files.append({
                "name": label,
                "path": os.path.join(safe_user_id, playlist_name, os.path.basename(file_path)),
            })
        state.completed += 1

    state.status = "done"
    state.current_track = ""
