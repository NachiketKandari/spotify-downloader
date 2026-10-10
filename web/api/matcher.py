"""
Track matcher: finds the best YouTube Music / YouTube audio source for a Spotify
track and downloads it as a tagged MP3.

This module is the single place where "which video is the right one?" is decided.
Everything else (login downloads, CSV uploads, pasted playlist links) calls
`find_best_match` and `download_match` so the behavior stays consistent.

If matching quality needs tuning later, the knobs at the top of this file
(W_* weights, MAX_DURATION_DIFF, MIN_SCORE, BAD_TITLE_KEYWORDS) are the place to start.
"""

import io
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
import yt_dlp
from mutagen.id3 import APIC, TALB, TDRC, TIT2, TPE1, TRCK, TXXX, ID3, error
from mutagen.mp3 import MP3
from PIL import Image
from ytmusicapi import YTMusic

# ---------------------------------------------------------------------------
# Tuning knobs
# ---------------------------------------------------------------------------

# Duration tolerance: a candidate must be within max(15s, 15% of the Spotify
# duration) of it. The percentage side handles songs with long outros/intros.
# Rejecting on *relative* distance also means a 20s gap on a 3:32 song fails,
# while a long track tolerates a bigger absolute gap.
MIN_DURATION_TOLERANCE = 15
MAX_DURATION_TOLERANCE = 45
DURATION_TOLERANCE_RATIO = 0.15

# Minimum score a candidate needs to be accepted. Lower = more permissive.
MIN_SCORE = 40

# If the Spotify title has words, the candidate title must cover at least this
# fraction of them. Stops "same artist, different song" matches.
MIN_TITLE_COVERAGE = 0.5

# Scoring weights
W_DURATION = 60.0   # scaled by how close the durations are
W_ARTIST = 45.0     # artist name appears in the candidate
W_TITLE = 20.0      # candidate title roughly matches the track title
W_TOPIC = 15.0      # "Artist - Topic" style channel (usually official audio)
W_ALBUM = 5.0       # candidate came with album metadata

# Words that usually mean "not the plain studio track". Ignored when the
# Spotify title itself contains the word (e.g. a song actually called "Live").
BAD_TITLE_KEYWORDS = [
    "live", "remix", "cover", "karaoke", "instrumental", "sped up",
    "slowed", "nightcore", "8d", "bass boosted", "clip", "lyrics",
    "music video", "official video", "shorts", "reaction", "tutorial",
]

# How many YT Music results to request and score per track.
YT_MUSIC_SEARCH_LIMIT = 10
# How many yt-dlp ytsearch fallback results to request and score per track.
YTDLP_FALLBACK_LIMIT = 5

# Browser user agent for cover art downloads.
ART_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Offlineify cover art fetcher)"}


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class TrackQuery:
    """A Spotify track we want to find on YouTube Music."""

    name: str
    artist: str
    album: str = ""
    album_artist: str = ""
    duration_ms: Optional[int] = None
    cover_url: Optional[str] = None
    release_date: Optional[str] = None
    track_number: Optional[int] = None
    total_tracks: Optional[int] = None
    explicit: Optional[bool] = None

    @classmethod
    def from_dict(cls, track: Dict[str, Any]) -> "TrackQuery":
        return cls(
            name=track.get("name") or "",
            artist=track.get("artist") or "",
            album=track.get("album") or "",
            album_artist=track.get("album_artist") or "",
            duration_ms=track.get("duration_ms"),
            cover_url=track.get("cover_url"),
            release_date=track.get("release_date"),
            track_number=track.get("track_number"),
            total_tracks=track.get("total_tracks"),
            explicit=track.get("explicit"),
        )

    @property
    def duration_s(self) -> Optional[float]:
        if self.duration_ms:
            return self.duration_ms / 1000.0
        return None


@dataclass
class Match:
    """A candidate audio source found for a track."""

    video_id: str
    title: str
    duration: Optional[float]
    score: float
    source: str  # "ytmusic" or "ytsearch"
    artists: List[str] = field(default_factory=list)
    album: str = ""
    thumbnail: Optional[str] = None

    @property
    def url(self) -> str:
        return f"https://music.youtube.com/watch?v={self.video_id}"


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"[\(\[\{].*?[\)\]\}]")
_NON_WORD_RE = re.compile(r"[^a-z0-9\s]")
_FEAT_RE = re.compile(r"\b(feat|ft|featuring|with)\b.*")
_SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Lowercase, strip accents, parentheses/brackets and punctuation."""
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = _TAG_RE.sub(" ", value)  # drop "(Remastered 2011)" style suffixes
    value = value.lower()
    value = _NON_WORD_RE.sub(" ", value)
    return _SPACE_RE.sub(" ", value).strip()


def artist_tokens(artist_field: str) -> List[str]:
    """Split a possibly multi-artist string ('A;B', 'A feat. B') into names."""
    names: List[str] = []
    for chunk in re.split(r"[;,/&]| feat\.? | ft\.? | featuring ", artist_field or "", flags=re.IGNORECASE):
        token = normalize_text(chunk)
        if token:
            names.append(token)
    return names


def blocked_words(query: TrackQuery) -> List[str]:
    """Blocklist words that are acceptable because the Spotify title uses them."""
    title_words = set(normalize_text(query.name).split())
    return [kw for kw in BAD_TITLE_KEYWORDS if not set(kw.split()) & title_words]


def _duration_seconds(raw: Any) -> Optional[float]:
    """Accept seconds (int) or '3:45' strings from ytmusicapi results."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    parts = str(raw).strip().split(":")
    try:
        seconds = 0.0
        for part in parts:
            seconds = seconds * 60 + float(part)
        return seconds
    except ValueError:
        return None


def _artist_names(raw: Any) -> List[str]:
    """ytmusicapi returns artists as either a string or a list of dicts."""
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw]
    names = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name")
        else:
            name = str(item)
        if name:
            names.append(name)
    return names


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_candidate(query: TrackQuery, candidate: Match) -> Optional[float]:
    """
    Score one candidate against the Spotify track.

    Returns None when the candidate is rejected outright (too different in
    length, or contains a blocklisted word). Otherwise returns a number where
    higher is better; MIN_SCORE is the acceptance bar.
    """
    title_norm = normalize_text(candidate.title)
    title_raw = (candidate.title or "").lower()
    query_title = normalize_text(query.name)

    # 1. Reject blocklisted words unless the Spotify title has them too.
    # Check the raw title as well, so words inside "(Live...)" / "(Official Video)" count.
    for keyword in blocked_words(query):
        if keyword in title_raw:
            return None

    score = 0.0

    # 2. Duration closeness.
    query_duration = query.duration_s
    if query_duration is not None and candidate.duration is not None:
        tolerance = min(
            max(MIN_DURATION_TOLERANCE, query_duration * DURATION_TOLERANCE_RATIO),
            MAX_DURATION_TOLERANCE,
        )
        diff = abs(query_duration - candidate.duration)
        if diff > tolerance:
            return None
        # Linear falloff: perfect match gets W_DURATION, edge gets ~0.
        score += W_DURATION * max(0.0, 1.0 - diff / tolerance)
    # If we have no durations to compare, score on names alone.

    # 3. Artist match: any Spotify artist token appearing in the candidate.
    candidate_artists = " ".join(normalize_text(a) for a in candidate.artists) or title_norm
    if any(token and token in candidate_artists for token in artist_tokens(query.artist)):
        score += W_ARTIST

    # 4. Title match: token overlap between the two titles. When the Spotify
    # title has words, require decent coverage so we don't accept a different
    # song by the same artist.
    query_words = set(query_title.split())
    candidate_words = set(title_norm.split())
    if query_words:
        coverage = len(query_words & candidate_words) / len(query_words)
        if coverage < MIN_TITLE_COVERAGE:
            return None
        score += W_TITLE * coverage

    # 5. Bonus for "- Topic" style channels (auto-generated official uploads).
    if "topic" in title_norm and candidate.source == "ytmusic":
        score += W_TOPIC
    if candidate.album:
        score += W_ALBUM

    return score


def pick_best(query: TrackQuery, candidates: List[Match]) -> Optional[Match]:
    """Score every candidate, drop rejects, and return the highest scorer."""
    scored: List[Match] = []
    for candidate in candidates:
        value = score_candidate(query, candidate)
        if value is not None and value >= MIN_SCORE:
            candidate.score = value
            scored.append(candidate)

    if not scored:
        return None

    # Highest score first; ties go to the closest duration.
    query_duration = query.duration_s or 0.0
    scored.sort(key=lambda m: (m.score, -abs(query_duration - (m.duration or 0.0))), reverse=True)
    return scored[0]


# ---------------------------------------------------------------------------
# Candidate discovery
# ---------------------------------------------------------------------------

_ytmusic: Optional[YTMusic] = None


def _client() -> YTMusic:
    """Lazy singleton; anonymous access is enough for searching."""
    global _ytmusic
    if _ytmusic is None:
        _ytmusic = YTMusic()
    return _ytmusic


def _search_ytmusic(query: TrackQuery) -> List[Match]:
    search_term = f"{query.artist} {query.name}".strip()
    raw_results = _client().search(search_term, filter="songs", limit=YT_MUSIC_SEARCH_LIMIT)

    matches: List[Match] = []
    for item in raw_results:
        video_id = item.get("videoId")
        if not video_id:
            continue
        matches.append(
            Match(
                video_id=video_id,
                title=item.get("title") or "",
                duration=_duration_seconds(item.get("duration_seconds")),
                score=0.0,
                source="ytmusic",
                artists=_artist_names(item.get("artists")),
                album=(item.get("album") or {}).get("name", "") if isinstance(item.get("album"), dict) else "",
                thumbnail=(item.get("thumbnails") or [{}])[-1].get("url"),
            )
        )
    return matches


def _search_ytdlp(query: TrackQuery) -> List[Match]:
    """Fallback: plain YouTube search, same scoring applied later."""
    search_term = f"{query.artist} {query.name} audio".strip()
    options = {"quiet": True, "no_warnings": True, "noplaylist": True, "extract_flat": "in_playlist"}

    matches: List[Match] = []
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"ytsearch{YTDLP_FALLBACK_LIMIT}:{search_term}", download=False)

    for entry in (info or {}).get("entries", []) or []:
        if not entry or not entry.get("id"):
            continue
        matches.append(
            Match(
                video_id=entry["id"],
                title=entry.get("title") or "",
                duration=_duration_seconds(entry.get("duration")),
                score=0.0,
                source="ytsearch",
                artists=[entry.get("uploader") or ""],
                thumbnail=entry.get("thumbnail"),
            )
        )
    return matches


def find_best_match(query: TrackQuery, allow_ytdlp_fallback: bool = True) -> Optional[Match]:
    """
    Find the best audio source for a Spotify track.

    Tries YT Music first (its 'songs' catalog hides most videos and clips),
    then plain YouTube search as a fallback. Returns None when nothing scores
    above MIN_SCORE.
    """
    match = pick_best(query, _search_ytmusic(query))
    if match is not None or not allow_ytdlp_fallback:
        return match
    return pick_best(query, _search_ytdlp(query))


# ---------------------------------------------------------------------------
# Downloading and tagging
# ---------------------------------------------------------------------------

def ytdlp_download_options(output_dir: str, quality: str, base_name: str = "%(artist,uploader)s - %(title)s") -> Dict[str, Any]:
    """yt-dlp options used for every track download.

    `base_name` is the file name template; callers can pass a fixed name to
    control exactly how the file lands on disk.
    """
    return {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality,
        }],
        "outtmpl": os.path.join(output_dir, f"{base_name}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        # Do NOT read browser cookies: the backend must work on headless servers.
    }


def download_match(match: Match, query: TrackQuery, output_dir: str, quality: str = "320") -> Optional[str]:
    """
    Download a matched video and write Spotify tags onto the MP3.

    The file is named "<artist> - <title>.mp3" from the Spotify metadata, so
    names are predictable; messy YouTube channel names never leak in.
    Returns the final file path, or None if the download produced no file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Clean up the name for the filesystem: no slashes, no comma piles.
    safe_base = f"{query.artist} - {query.name}".replace("/", " ")
    safe_base = re.sub(r"\s*[,;]\s*", " ", safe_base)
    safe_base = _SPACE_RE.sub(" ", safe_base).strip() or "track"
    options = ytdlp_download_options(output_dir, quality, base_name=safe_base)

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(match.video_id, download=True)
        if info is None:
            return None
        file_path = ydl.prepare_filename(info)
        file_path = os.path.splitext(file_path)[0] + ".mp3"

    if not os.path.exists(file_path):
        return None

    write_tags(file_path, query, match)
    return file_path


def write_tags(file_path: str, query: TrackQuery, match: Match) -> None:
    """Write Spotify metadata and cover art onto an MP3 file (best effort)."""
    cover_url = query.cover_url or match.thumbnail

    try:
        audio = MP3(file_path, ID3=ID3)
        try:
            audio.add_tags()
        except error:
            pass

        audio.tags.add(TIT2(encoding=3, text=query.name))
        audio.tags.add(TPE1(encoding=3, text=query.artist))
        if query.album:
            audio.tags.add(TALB(encoding=3, text=query.album))
        if query.release_date:
            audio.tags.add(TDRC(encoding=3, text=query.release_date))
        if query.track_number:
            track_number = str(query.track_number)
            if query.total_tracks:
                track_number += f"/{query.total_tracks}"
            audio.tags.add(TRCK(encoding=3, text=track_number))
        if query.explicit is not None:
            audio.tags.add(TXXX(encoding=3, desc="ITUNESADVISORY", text="1" if query.explicit else "0"))

        if cover_url:
            # Cover art is best-effort: a dead image URL must not lose the tags.
            try:
                embed_cover(audio, cover_url, from_spotify=bool(query.cover_url))
            except Exception as e:
                print(f"Cover art error for {file_path}: {e}")

        audio.save()
    except Exception as e:
        print(f"Tagging error for {file_path}: {e}")


def embed_cover(audio: MP3, cover_url: str, from_spotify: bool) -> None:
    """Download and embed cover art, square-cropping non-Spotify images."""
    resp = requests.get(cover_url, headers=ART_HTTP_HEADERS, timeout=30)
    resp.raise_for_status()
    image = Image.open(io.BytesIO(resp.content))

    if not from_spotify:
        width, height = image.size
        side = min(width, height)
        left, top = (width - side) / 2, (height - side) / 2
        image = image.crop((left, top, left + side, top + side))

    image_io = io.BytesIO()
    image.convert("RGB").save(image_io, format="JPEG")
    audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=image_io.getvalue()))
