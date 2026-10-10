"""
Single-track download flow: dedupe -> match -> download -> tag -> index.

The "which video is right?" decision lives in `matcher.py`; this file only adds
the download index (so repeat requests are skipped instantly) around it.
"""

import json
import os
import time
from typing import Any, Dict, Optional

from .matcher import DEFAULT_AUDIO_FORMAT, TrackQuery, download_match, find_best_match

DOWNLOAD_INDEX_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "downloaded_songs.json")
DOWNLOAD_DIR = "downloads"


def load_download_index() -> Dict[str, Any]:
    if os.path.exists(DOWNLOAD_INDEX_FILE):
        try:
            with open(DOWNLOAD_INDEX_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading index file: {e}")
    return {}


def save_download_index(index: Dict[str, Any]) -> None:
    try:
        with open(DOWNLOAD_INDEX_FILE, "w") as f:
            json.dump(index, f, indent=4)
    except Exception as e:
        print(f"Error saving index file: {e}")


def _output_dir(ydl_opts: Optional[Dict[str, Any]]) -> str:
    """Where the audio lands. main.py passes it via ydl_opts['output_dir']."""
    if ydl_opts and ydl_opts.get("output_dir"):
        return ydl_opts["output_dir"]
    return DOWNLOAD_DIR


def _quality(ydl_opts: Optional[Dict[str, Any]]) -> str:
    return (ydl_opts or {}).get("quality", "320")


def _fmt(ydl_opts: Optional[Dict[str, Any]]) -> str:
    return (ydl_opts or {}).get("format") or DEFAULT_AUDIO_FORMAT


def process_track(track: Dict[str, Any], ydl_opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Download one track. Returns one of:
      {"status": "success", "filename": ...}
      {"status": "skipped", "filename": ..., "message": ...}
      {"status": "error",   "message": ...}
    """
    output_dir = _output_dir(ydl_opts)
    quality = _quality(ydl_opts)
    fmt = _fmt(ydl_opts)
    os.makedirs(output_dir, exist_ok=True)

    track_uri = track.get("uri")
    download_index = load_download_index()

    # 1. Dedupe: already indexed AND the file is really there.
    recorded = download_index.get(track_uri) if track_uri else None
    if recorded and recorded.get("filename"):
        existing = os.path.join(output_dir, recorded["filename"])
        if os.path.exists(existing):
            return {"status": "skipped", "message": "Already downloaded", "filename": recorded["filename"]}

    # 2. Match and download.
    query = TrackQuery.from_dict(track)
    if not query.name:
        return {"status": "error", "message": "Track has no name"}

    match = find_best_match(query)
    if match is None:
        return {"status": "error", "message": "No good audio match found on YouTube Music"}

    try:
        file_path = download_match(match, query, output_dir, quality=quality, fmt=fmt)
    except Exception as e:
        return {"status": "error", "message": f"Download failed: {e}"}

    if not file_path:
        return {"status": "error", "message": "Download produced no file"}

    filename = os.path.basename(file_path)

    # 3. Index for future dedupe.
    if track_uri:
        download_index[track_uri] = {
            "name": query.name,
            "artist": query.artist,
            "filename": filename,
            "video_id": match.video_id,
            "match_score": round(match.score, 1),
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        save_download_index(download_index)

    return {"status": "success", "filename": filename, "match_score": round(match.score, 1)}
