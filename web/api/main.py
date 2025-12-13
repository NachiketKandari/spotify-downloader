from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
import shutil
import uuid
import yt_dlp
from .downloader import process_track

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

# Global State: Map user_id (email) -> JobState
job_states: Dict[str, JobState] = {}

def get_job_state(user_id: str) -> JobState:
    if user_id not in job_states:
        job_states[user_id] = JobState()
    return job_states[user_id]

def run_download_job(user_id: str, playlists: List[PlaylistBatch], quality: str):
    state = get_job_state(user_id)
    state.status = "working"
    
    # Calculate total first
    total_tracks = sum(len(p.tracks) for p in playlists)
    state.total = total_tracks
    state.completed = 0
    state.logs = []
    state.completed_files = [] # Reset
    
    # Base Output Path: downloads/{user_id}
    # Sanitize user_id to be safe for filesystem
    safe_user_id = "".join([c for c in user_id if c.isalnum() or c in ['@', '.', '-', '_']])
    base_output_path = os.path.join("downloads", safe_user_id)

    # yt-dlp options
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': quality,
        }],
        'outtmpl': f'{base_output_path}/%(artist)s - %(title)s.%(ext)s', 
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
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
        ydl_opts['outtmpl'] = f'{playlist_dir}/%(artist)s - %(title)s.%(ext)s'
        ydl_opts['output_dir'] = playlist_dir 

        m3u_content = ["#EXTM3U"]
        
        for track in playlist.tracks:
            state.current_track = f"[{playlist.name}] {track.name}"
            
            # Call the core logic
            # Note: process_track might need updates if it relies on global singletons, 
            # but currently it takes ydl_opts and manages its own index. 
            # Ideally each user should have their own index? 
            # For now, we share the index or let process_track handle it.
            # Ideally pass output_dir to process_track to ensure index is relevant?
            # existing process_track uses DOWNLOAD_INDEX_FILE which is global. 
            # This might cause "Skipped" if User A downloaded it and User B tries.
            # For now, acceptable optimization (global cache), but might be weird if users want separate files.
            # Let's keep global deduplication for efficiency.
            
            result = process_track(track.model_dump(), ydl_opts)
            
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
    background_tasks.add_task(run_download_job, x_user_id, request.playlists, request.quality)
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
    zip_path = os.path.join("downloads", zip_filename) 
    
    shutil.make_archive(zip_path, 'zip', user_dir)
    return FileResponse(f"{zip_path}.zip", filename="your_music.zip")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
