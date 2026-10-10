from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, Form, HTTPException, Header, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
from urllib.parse import quote
import mimetypes
import io
import os
import random
import time
import zipfile
import pandas as pd
from . import housekeeping
from .auth import PasswordGuard
from .downloader import process_track
from .link_download import csv_export, is_playlist_url, preview_playlist, run_link_job, safe_name


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Hourly sweep that deletes downloads nobody picked up (see housekeeping).
    housekeeping.start_cleanup_thread()
    yield


app = FastAPI(lifespan=lifespan)

# Optional shared-password guard (active only when OFFLINEIFY_PASSWORD is set).
# Registered before CORS so CORS stays outermost and wraps the guard's 401s
# with CORS headers (otherwise browsers would see an opaque network error).
app.add_middleware(PasswordGuard)

# Allow CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class Track(BaseModel):
    uri: str
    name: str
    artist: str
    album: str
    cover_url: Optional[str] = None
    release_date: Optional[str] = None
    track_number: Optional[int] = None
    total_tracks: Optional[int] = None
    explicit: Optional[bool] = False
    duration_ms: Optional[int] = None

class PlaylistBatch(BaseModel):
    name: str
    tracks: List[Track]

class DownloadRequest(BaseModel):
    playlists: List[PlaylistBatch]
    quality: str = "320"
    format: str = "m4a"  # "m4a" (passthrough, default) or "mp3" (re-encode)
    output_path: str = "downloads" # Only honored with ALLOW_CUSTOM_OUTPUT_PATH=1 (local folder picker)

class JobState(BaseModel):
    status: str = "idle"
    total: int = 0
    completed: int = 0
    current_track: str = ""
    logs: List[str] = []
    completed_files: List[dict] = [] # {name: str, path: str}
    cancel_requested: bool = False
    playlist_dir: str = ""

# Global State: Map user_id (email) -> JobState
job_states: Dict[str, JobState] = {}

def get_job_state(user_id: str) -> JobState:
    if user_id not in job_states:
        job_states[user_id] = JobState()
    return job_states[user_id]

def validated_user_id(user_id: str) -> str:
    """Filter a user id to safe filename characters; reject empty results.

    Every file endpoint goes through this so an empty or crafted id cannot
    address the downloads root or another user's folder.
    """
    cleaned = "".join(c for c in (user_id or "") if c.isalnum() or c in ['@', '.', '-', '_'])
    if not cleaned:
        raise HTTPException(status_code=400, detail="A valid user_id is required")
    return cleaned

def custom_output_allowed() -> bool:
    """Custom output_path is a local-only convenience; off by default on servers."""
    return os.environ.get("ALLOW_CUSTOM_OUTPUT_PATH", "").lower() in ("1", "true", "yes")

class _ZipSink(io.RawIOBase):
    """Unseekable byte sink; the zip generator drains it after every file."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, data: bytes) -> int:
        self.buffer += data
        return len(data)

    def take(self) -> bytes:
        chunk = bytes(self.buffer)
        self.buffer.clear()
        return chunk


def iter_zip(folder: str):
    """
    Stream `folder` as a ZIP.

    Entries are stored, not deflated: audio is already compressed, so this
    costs no compression CPU and the archive is identical in size. Nothing is
    written to disk. When the browser cancels mid-way the generator closes
    early and the files stay; once every byte has been yielded they are
    removed from the server (see housekeeping).
    """
    housekeeping.mark_active(folder)
    sink = _ZipSink()
    delivered = False
    try:
        with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED, allowZip64=True) as archive:
            for root, _, files in os.walk(folder):
                for name in files:
                    full = os.path.join(root, name)
                    # zipfile wants forward slashes; utf-8 names are kept intact.
                    archive.write(full, os.path.relpath(full, folder).replace(os.sep, "/"))
                    chunk = sink.take()
                    if chunk:
                        yield chunk
        chunk = sink.take()
        if chunk:
            yield chunk
        delivered = True
    finally:
        housekeeping.unmark_active(folder)
        if delivered:
            housekeeping.remove_after_delivery(folder)


def iter_file(path: str):
    """Stream one file; it is removed from the server once fully delivered."""
    housekeeping.mark_active(path)
    delivered = False
    try:
        with open(path, "rb") as handle:
            while chunk := handle.read(256 * 1024):
                yield chunk
        delivered = True
    finally:
        housekeeping.unmark_active(path)
        if delivered:
            housekeeping.remove_after_delivery(path)


def attachment_headers(download_name: str) -> Dict[str, str]:
    """Content-Disposition that survives non-ASCII names (Hindi playlists etc.)."""
    fallback = download_name.encode("ascii", "ignore").decode().strip() or "download"
    return {"Content-Disposition": f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(download_name)}'}


def zip_response(folder: str, download_name: str) -> StreamingResponse:
    """One streamed, stored ZIP; the folder is cleared after delivery."""
    return StreamingResponse(
        iter_zip(folder),
        media_type="application/zip",
        headers=attachment_headers(download_name),
    )


def folder_is_empty(folder: str) -> bool:
    return not any(files for _, _, files in os.walk(folder))

def run_download_job(user_id: str, playlists: List[PlaylistBatch], quality: str, output_path: str = "downloads", fmt: str = "m4a"):
    """Public entry point: waits for the global download slot, then runs the job."""
    with housekeeping.download_slot(get_job_state(user_id)):
        _run_download_job(user_id, playlists, quality, output_path, fmt)


def _run_download_job(user_id: str, playlists: List[PlaylistBatch], quality: str, output_path: str, fmt: str):
    state = get_job_state(user_id)
    state.status = "working"
    
    # Calculate total first
    total_tracks = sum(len(p.tracks) for p in playlists)
    state.total = total_tracks
    state.completed = 0
    state.logs = []
    state.completed_files = [] # Reset
    state.cancel_requested = False # Reset, otherwise a past cancel kills this job
    
    # Base Output Path: downloads/{user_id}
    # Determine base output path
    safe_user_id = "".join([c for c in user_id if c.isalnum() or c in ['@', '.', '-', '_']])
    
    # Logic: 
    # 1. A custom output_path is only honored with ALLOW_CUSTOM_OUTPUT_PATH=1
    #    (local folder picker). On a server everything stays under downloads/.
    # 2. If user_id is "unknown" (local dev default), use "downloads" root.
    # 3. Otherwise, use downloads/{user_id} for multi-user isolation.
    if output_path and output_path != "downloads" and custom_output_allowed():
        base_output_path = output_path
    elif safe_user_id.lower() == "unknown":
        base_output_path = "downloads"
    else:
        base_output_path = os.path.join("downloads", safe_user_id)

    # yt-dlp is driven by matcher.py; here we only choose destination + format.
    ydl_opts = {
        'output_dir': base_output_path,
        'quality': quality,
        'format': fmt,
    }

    if not os.path.exists(base_output_path):
        os.makedirs(base_output_path)

    print(f"Starting download job for user {user_id}: {len(playlists)} playlists")

    for playlist in playlists:
        # Create Playlist Subfolder
        safe_playlist_name = "".join([c for c in playlist.name if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        playlist_dir = os.path.join(base_output_path, safe_playlist_name)
        
        state.logs.append(f"Processing Playlist: {playlist.name}")
        
        if not os.path.exists(playlist_dir):
            os.makedirs(playlist_dir)
        
        # Update output template for this playlist
        ydl_opts['output_dir'] = playlist_dir

        m3u_content = ["#EXTM3U"]
        
        for track in playlist.tracks:
            # Check for cancellation
            if state.cancel_requested:
                state.status = "cancelled"
                state.logs.append("Download cancelled by user")
                print(f"Job cancelled by user {user_id}")
                return

            state.current_track = f"[{playlist.name}] {track.name}"

            result = process_track(track.model_dump(), ydl_opts)

            # Rate limiting: only pause between real downloads. Cached tracks
            # (skipped) return instantly, so long playlists re-run in seconds.
            if result['status'] != 'skipped':
                time.sleep(random.uniform(3, 8))
            
            if result['status'] == 'success':
                msg = f"Downloaded: {track.name}"
                m3u_content.append(f"#EXTINF:-1,{track.artist} - {track.name}")
                m3u_content.append(result.get('filename', ''))
                
                # Rel path relative to USER'S base folder (downloads/user_id) is usually what we want?
                # Actually for UI download, we need track path relative to something handled by get_file.
                # get_file will take path relative to downloads/.
                # So we store path relative to downloads/
                
                full_rel_path = os.path.join(safe_user_id, safe_playlist_name, os.path.basename(result.get('filename', '')))
                state.completed_files.append({
                    "name": track.name,
                    "path": full_rel_path
                })

            elif result['status'] == 'skipped':
                msg = f"Skipped: {track.name}"
                if 'filename' in result:
                     m3u_content.append(f"#EXTINF:-1,{track.artist} - {track.name}")
                     m3u_content.append(result['filename'])
                     
                     full_rel_path = os.path.join(safe_user_id, safe_playlist_name, os.path.basename(result.get('filename', '')))
                     state.completed_files.append({
                        "name": track.name,
                        "path": full_rel_path
                    })
                
            else:
                msg = f"Error {track.name}: {result.get('message')}"
                
            print(msg)
            state.logs.append(msg)
            state.completed += 1
            
        # Write M3U8
        try:
             playlist_file = os.path.join(playlist_dir, f"{playlist.name}.m3u8")
             if len(m3u_content) > 1:
                 with open(playlist_file, 'w', encoding='utf-8') as f:
                     f.write("\n".join(m3u_content))
                 state.logs.append(f"Created Playlist: {playlist_file}")
        except Exception as e:
            print(f"Error creating m3u: {e}")
    
    state.status = "done"
    state.current_track = ""
    print(f"Job finished for user {user_id}")

@app.get("/")
def read_root():
    return {"message": "Offlineify API is running"}

@app.get("/api/file")
def get_file(path: str, user_id: str):
    """Serve one file; it is removed from the server once the browser got it."""
    safe_user_id = validated_user_id(user_id)

    # The path must resolve inside downloads/ AND inside this user's folder.
    downloads_root = os.path.abspath("downloads")
    requested = os.path.abspath(os.path.join(downloads_root, path))
    try:
        inside_root = os.path.commonpath([downloads_root, requested]) == downloads_root
    except ValueError:
        inside_root = False
    if not inside_root:
        raise HTTPException(status_code=403, detail="Invalid file path")

    if not path.startswith(safe_user_id + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.isfile(requested):
        raise HTTPException(status_code=404, detail="File not found")

    headers = attachment_headers(os.path.basename(path))
    headers["Content-Length"] = str(os.path.getsize(requested))
    media_type = mimetypes.guess_type(requested)[0] or "application/octet-stream"
    return StreamingResponse(iter_file(requested), media_type=media_type, headers=headers)

@app.post("/api/download")
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks, x_user_id: str = Header(...)):
    x_user_id = validated_user_id(x_user_id)

    state = get_job_state(x_user_id)
    
    if state.status == "working":
        return {"message": "Job already in progress", "status": "working"}
    
    # Start background task with USER CONTEXT
    background_tasks.add_task(run_download_job, x_user_id, request.playlists, request.quality, request.output_path, request.format)
    return {"message": "Download started", "status": "starting"}

@app.get("/api/status")
def get_status(user_id: Optional[str] = Query(None)):
    if not user_id:
        return JobState() # Return empty state
    return get_job_state(user_id)

@app.get("/api/zip")
def download_zip(user_id: str):
    """Stream the user's whole download folder as one ZIP (then clear it)."""
    safe_user_id = validated_user_id(user_id)
    user_dir = os.path.join("downloads", safe_user_id)
    
    if not os.path.isdir(user_dir) or folder_is_empty(user_dir):
        raise HTTPException(status_code=404, detail="Nothing to download")

    return zip_response(user_dir, "your_music.zip")

@app.get("/api/choose-directory")
def choose_directory():
    """Opens a native OS folder picker. Returns {"path": ...} or error."""
    try:
        # Strategy 1: MacOS Native (AppleScript) - Better UX on Mac
        import subprocess
        import sys
        if sys.platform == 'darwin':
            try:
                script = 'tell application "System Events" to activate\nset p to POSIX path of (choose folder with prompt "Select Download Folder")\nreturn p'
                path = subprocess.check_output(['osascript', '-e', script], stderr=subprocess.STDOUT).decode('utf-8').strip()
                if path:
                    return {"path": path}
            except subprocess.CalledProcessError:
                return {"path": "downloads"} # Cancelled -> Default
            except Exception as e:
                print(f"Mac Picker failed: {e}")

        # Strategy 2: Tkinter (Universal Fallback)
        import tkinter as tk
        from tkinter import filedialog
        
        # Check if we have a display (prevent crash on headless servers)
        if not os.environ.get('DISPLAY') and sys.platform != 'darwin' and os.name != 'nt':
             return {"path": "downloads"} # Headless env -> Default

        root = tk.Tk()
        root.withdraw() 
        root.attributes('-topmost', True) 
        
        # Force focus
        root.lift()
        root.focus_force()
        
        path = filedialog.askdirectory(title="Select Download Folder")
        root.destroy()
        
        if path:
             return {"path": path}
        return {"path": "downloads"} # Cancelled -> Default
            
    except Exception as e:
        print(f"Directory picker error: {e}")
        return {"path": "downloads"} # Fallback safe mode

@app.post("/api/cancel")
def cancel_download(user_id: str):
    """Cancel an in-progress download job"""
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
    
    state = get_job_state(user_id)
    if state.status != "working":
        return {"message": "No active download to cancel", "status": state.status}
    
    state.cancel_requested = True
    return {"message": "Cancellation requested", "status": "cancelling"}

def _clean_text(value) -> str:
    """CSV cells come back as NaN when empty; turn those into ''."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()

def _clean_int(value) -> Optional[int]:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def _clean_bool(value) -> bool:
    return _clean_text(value).lower() == 'true'

def parse_csv_tracks(contents: bytes) -> List[Track]:
    """
    Build Track objects from a Spotify playlist CSV export.

    Works with this app's own export and with Exportify's, which uses
    'Track Duration (ms)' instead of 'Duration (ms)'.
    """
    df = pd.read_csv(io.BytesIO(contents))
    tracks = []
    for _, row in df.iterrows():
        duration = row.get('Duration (ms)')
        if duration is None or pd.isna(duration):
            duration = row.get('Track Duration (ms)')
        tracks.append(Track(
            uri=_clean_text(row.get('Track URI')),
            name=_clean_text(row.get('Track Name')),
            artist=_clean_text(row.get('Artist Name(s)')),
            album=_clean_text(row.get('Album Name')),
            cover_url=_clean_text(row.get('Album Image URL')) or None,
            release_date=_clean_text(row.get('Album Release Date')) or None,
            track_number=_clean_int(row.get('Track Number')),
            total_tracks=_clean_int(row.get('Total Tracks')),
            explicit=_clean_bool(row.get('Explicit')),
            duration_ms=_clean_int(duration),
        ))
    return tracks

@app.post("/api/csv-download")
async def csv_download(file: UploadFile, background_tasks: BackgroundTasks, format: str = Form("m4a"), user_id: str = Form("csv_user")):
    """Upload a Spotify CSV export and download the tracks"""
    user_id = validated_user_id(user_id)
    try:
        contents = await file.read()
        tracks = parse_csv_tracks(contents)
        
        # Create a single playlist batch
        playlist_batch = PlaylistBatch(name="CSV Upload", tracks=tracks)
        
        # Start download job
        state = get_job_state(user_id)
        if state.status == "working":
            return {"message": "Job already in progress", "status": "working"}
        
        background_tasks.add_task(run_download_job, user_id, [playlist_batch], "320", "downloads", format)
        return {"message": "CSV upload successful, download started", "status": "starting", "track_count": len(tracks)}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parsing error: {str(e)}")

class LinkDownloadRequest(BaseModel):
    url: Optional[str] = None
    quality: str = "320"
    format: str = "m4a"  # "m4a" (passthrough, default) or "mp3" (re-encode)
    spotify_user_token: Optional[str] = None  # sent by the UI when logged in
    preview_token: Optional[str] = None       # from /api/link-preview
    selected_indexes: Optional[List[int]] = None  # subset of preview tracks

class PlaylistPreviewRequest(BaseModel):
    url: str
    spotify_user_token: Optional[str] = None

@app.post("/api/link-preview")
def link_preview(request: PlaylistPreviewRequest):
    """Resolve a playlist link and return its tracks for selection (no downloads)."""
    if not is_playlist_url(request.url):
        raise HTTPException(status_code=400, detail="Please paste a valid Spotify playlist link")
    try:
        return preview_playlist(request.url, user_token=request.spotify_user_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read playlist: {e}")

@app.get("/api/link-csv")
def link_csv(preview_token: Optional[str] = None, url: Optional[str] = None, selected: Optional[str] = None):
    """Export a resolved playlist as an Exportify-compatible CSV (re-uploadable)."""
    try:
        playlist_name, csv_text = csv_export(preview_token, url, selected)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not export CSV: {e}")
    return Response(
        csv_text,
        media_type="text/csv; charset=utf-8",
        headers=attachment_headers(f"{playlist_name}.csv"),
    )

@app.post("/api/link-download")
def start_link_download(request: LinkDownloadRequest, background_tasks: BackgroundTasks, user_id: str = Query(...)):
    """Start a download from a pasted Spotify playlist link (no login required)"""
    user_id = validated_user_id(user_id)
    if request.url is None and request.preview_token is None:
        raise HTTPException(status_code=400, detail="Provide a playlist link or preview token")
    if request.url is not None and not is_playlist_url(request.url):
        raise HTTPException(status_code=400, detail="Please paste a valid Spotify playlist link")
    if request.selected_indexes is not None and not request.selected_indexes:
        raise HTTPException(status_code=400, detail="Select at least one track to download")

    state = get_job_state(user_id)
    if state.status == "working":
        return {"message": "Job already in progress", "status": "working"}

    background_tasks.add_task(
        run_link_job,
        state,
        user_id,
        request.url or "",
        request.quality,
        request.spotify_user_token,
        request.preview_token,
        request.selected_indexes,
        request.format,
    )
    return {"message": "Playlist download started", "status": "starting"}

@app.get("/api/playlist-zip")
def download_playlist_zip(user_id: str, playlist: str):
    """Stream one playlist folder as a ZIP (then clear it from the server)."""
    safe_user_id = validated_user_id(user_id)
    playlist_dir = os.path.join("downloads", safe_user_id, safe_name(playlist))

    if not os.path.isdir(playlist_dir) or folder_is_empty(playlist_dir):
        raise HTTPException(status_code=404, detail="Playlist not found")

    return zip_response(playlist_dir, f"{safe_name(playlist)}.zip")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
