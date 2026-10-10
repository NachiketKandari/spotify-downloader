from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import io
import os
import uuid
import random
import time
import zipfile
import pandas as pd
from starlette.background import BackgroundTask
from .downloader import process_track
from .link_download import is_playlist_url, run_link_job, safe_name

app = FastAPI()

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
    output_path: str = "downloads" # Legacy param, effectively ignored/overridden by multi-user logic

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

def zip_folder(folder: str, zip_path: str) -> str:
    """Zip a folder with UTF-8 entry names (make_archive mangles accents)."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for root, _, files in os.walk(folder):
            for name in files:
                full = os.path.join(root, name)
                # zipfile wants forward slashes and utf-8 encoded names.
                archive.write(full, os.path.relpath(full, folder))
    return zip_path

def remove_file(path: str) -> None:
    """BackgroundTask: delete a temp file once it has been sent."""
    try:
        os.remove(path)
    except OSError:
        pass

def run_download_job(user_id: str, playlists: List[PlaylistBatch], quality: str, output_path: str = "downloads"):
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
    # 1. If explicit output_path provided (and not default "downloads"), use it.
    # 2. If user_id is "unknown" (local dev default), use "downloads" root.
    # 3. Otherwise, use downloads/{user_id} for multi-user isolation.
    if output_path and output_path != "downloads":
        base_output_path = output_path
    elif safe_user_id.lower() == "unknown":
        base_output_path = "downloads"
    else:
        base_output_path = os.path.join("downloads", safe_user_id)

    # yt-dlp is driven by matcher.py; here we only choose the destination.
    ydl_opts = {
        'output_dir': base_output_path,
        'quality': quality,
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
    """Serve a specific file. Path is relative to 'downloads/'."""
    # Security: Ensure path doesn't escape downloads/
    safe_path = os.path.normpath(os.path.join("downloads", path))
    if not safe_path.startswith("downloads"):
         raise HTTPException(status_code=403, detail="Invalid file path")
    
    # Path must start with user_id
    safe_user_id = "".join([c for c in user_id if c.isalnum() or c in ['@', '.', '-', '_']])
    # Check if the requested path actually inside the user's folder
    # path is like "user_id/playlist/song.mp3"
    if not path.startswith(safe_user_id):
            raise HTTPException(status_code=403, detail="Access denied")

    if os.path.exists(safe_path):
        return FileResponse(safe_path, filename=os.path.basename(path))
    return {"error": "File not found"}

@app.post("/api/download")
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks, x_user_id: str = Header(...)):
    if not x_user_id:
        raise HTTPException(status_code=400, detail="User ID required")
        
    state = get_job_state(x_user_id)
    
    if state.status == "working":
        return {"message": "Job already in progress", "status": "working"}
    
    # Start background task with USER CONTEXT
    background_tasks.add_task(run_download_job, x_user_id, request.playlists, request.quality, request.output_path)
    return {"message": "Download started", "status": "starting"}

@app.get("/api/status")
def get_status(user_id: Optional[str] = Query(None)):
    if not user_id:
        return JobState() # Return empty state
    return get_job_state(user_id)

@app.get("/api/zip")
def download_zip(user_id: str):
    """Zips the USER'S download folder"""
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
        
    safe_user_id = "".join([c for c in user_id if c.isalnum() or c in ['@', '.', '-', '_']])
    user_dir = os.path.join("downloads", safe_user_id)
    
    if not os.path.exists(user_dir):
        raise HTTPException(status_code=404, detail="Nothing to download")

    zip_filename = f"offlineify_{safe_user_id}_{uuid.uuid4().hex[:8]}"
    zip_path = os.path.join("downloads", f"{zip_filename}.zip")
    
    zip_folder(user_dir, zip_path)
    return FileResponse(zip_path, filename="your_music.zip", background=BackgroundTask(remove_file, zip_path))

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
async def csv_download(file: UploadFile, background_tasks: BackgroundTasks, quality: str = "320", user_id: str = "csv_user"):
    """Upload a Spotify CSV export and download the tracks"""
    try:
        contents = await file.read()
        tracks = parse_csv_tracks(contents)
        
        # Create a single playlist batch
        playlist_batch = PlaylistBatch(name="CSV Upload", tracks=tracks)
        
        # Start download job
        state = get_job_state(user_id)
        if state.status == "working":
            return {"message": "Job already in progress", "status": "working"}
        
        background_tasks.add_task(run_download_job, user_id, [playlist_batch], quality, "downloads")
        return {"message": "CSV upload successful, download started", "status": "starting", "track_count": len(tracks)}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parsing error: {str(e)}")

class LinkDownloadRequest(BaseModel):
    url: str
    quality: str = "320"
    spotify_user_token: Optional[str] = None  # sent by the UI when logged in

@app.post("/api/link-download")
def start_link_download(request: LinkDownloadRequest, background_tasks: BackgroundTasks, user_id: str = Query(...)):
    """Start a download from a pasted Spotify playlist link (no login required)"""
    if not is_playlist_url(request.url):
        raise HTTPException(status_code=400, detail="Please paste a valid Spotify playlist link")

    state = get_job_state(user_id)
    if state.status == "working":
        return {"message": "Job already in progress", "status": "working"}

    background_tasks.add_task(
        run_link_job, state, user_id, request.url, request.quality, request.spotify_user_token
    )
    return {"message": "Playlist download started", "status": "starting"}

@app.get("/api/playlist-zip")
def download_playlist_zip(user_id: str, playlist: str):
    """Zips a single playlist folder from the user's downloads"""
    safe_user_id = "".join([c for c in user_id if c.isalnum() or c in ['@', '.', '-', '_']])
    playlist_dir = os.path.join("downloads", safe_user_id, safe_name(playlist))

    if not os.path.isdir(playlist_dir):
        raise HTTPException(status_code=404, detail="Playlist not found")

    zip_path = os.path.join("downloads", f"offlineify_{safe_user_id}_{uuid.uuid4().hex[:8]}.zip")
    zip_folder(playlist_dir, zip_path)
    return FileResponse(zip_path, filename=f"{safe_name(playlist)}.zip", background=BackgroundTask(remove_file, zip_path))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
