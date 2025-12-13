from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import uvicorn
from web.api.downloader import process_track

app = FastAPI()

# Enable CORS for Next.js (localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to localhost:3000
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class Track(BaseModel):
    uri: str
    name: str
    artist: str
    album: Optional[str] = None
    cover_url: Optional[str] = None

    cover_url: Optional[str] = None

class PlaylistBatch(BaseModel):
    name: str # Name of the playlist (for subfolder)
    tracks: List[Track]

class DownloadRequest(BaseModel):
    playlists: List[PlaylistBatch] # Changed from flat 'tracks'
    quality: str = "320" # '192' or '320'
    output_path: str = "downloads" # Default path

# Global State (Simple in-memory for this single-user local app)
class JobState(BaseModel):
    status: str = "idle"
    total: int = 0
    completed: int = 0
    current_track: str = ""
    logs: List[str] = []
    completed_files: List[dict] = [] # {name: str, path: str}

job_state = JobState()

def run_download_job(playlists: List[PlaylistBatch], quality: str, base_output_path: str):
    job_state.status = "working"
    
    # Calculate total first
    total_tracks = sum(len(p.tracks) for p in playlists)
    job_state.total = total_tracks
    job_state.completed = 0
    job_state.logs = []
    job_state.completed_files = [] # Reset
    
    # yt-dlp options
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': quality,
        }],
        'outtmpl': f'{base_output_path}/%(artist)s - %(title)s.%(ext)s', # Placeholder, overwritten below
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
    }

    if not os.path.exists(base_output_path):
        os.makedirs(base_output_path)

    print(f"Starting download job for {len(playlists)} playlists, {total_tracks} total tracks")

    for playlist in playlists:
        # Sanitize playlist name for folder
        safe_playlist_name = "".join([c for c in playlist.name if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        playlist_dir = os.path.join(base_output_path, safe_playlist_name)
        
        job_state.logs.append(f"Processing Playlist: {playlist.name} -> {playlist_dir}")
        
        # Create Playlist Directory
        if not os.path.exists(playlist_dir):
            os.makedirs(playlist_dir)

        # Update output template for this playlist
        ydl_opts['outtmpl'] = f'{playlist_dir}/%(artist)s - %(title)s.%(ext)s'
        ydl_opts['output_dir'] = playlist_dir # Custom param for our process_track
        
        # Create M3U8 Playlist File
        m3u_content = ["#EXTM3U"]
        
        for track in playlist.tracks:
            job_state.current_track = f"[{playlist.name}] {track.name}"
            
            # Call the core logic
            result = process_track(track.model_dump(), ydl_opts)
            
            if result['status'] == 'success':
                msg = f"Downloaded: {track.name}"
                # Add to M3U
                m3u_content.append(f"#EXTINF:-1,{track.artist} - {track.name}")
                m3u_content.append(result.get('filename', ''))
                
                # Add to completed_files for individual download
                rel_path = os.path.join(safe_playlist_name, os.path.basename(result.get('filename', '')))
                job_state.completed_files.append({
                    "name": track.name,
                    "path": rel_path
                })

            elif result['status'] == 'skipped':
                msg = f"Skipped: {track.name}"
                # Add to M3U (Now we have filename)
                if 'filename' in result:
                    m3u_content.append(f"#EXTINF:-1,{track.artist} - {track.name}")
                    m3u_content.append(result['filename'])
                    
                    rel_path = os.path.join(safe_playlist_name, os.path.basename(result.get('filename', '')))
                    job_state.completed_files.append({
                        "name": track.name,
                        "path": rel_path
                    })
                
            else:
                msg = f"Error {track.name}: {result.get('message')}"
                
            print(msg)
            job_state.logs.append(msg)
            job_state.completed += 1
            
        # Write M3U8
        # Note: This list might be incomplete if skipped tracks don't return filenames. 
        # I should probably update `downloader.py` to return filenames on skip.
        # But for this task, I'll write what I have.
        try:
             playlist_file = os.path.join(playlist_dir, f"{playlist.name}.m3u8")
             if len(m3u_content) > 1:
                 with open(playlist_file, 'w', encoding='utf-8') as f:
                     f.write("\n".join(m3u_content))
                 job_state.logs.append(f"Created Playlist: {playlist_file}")
        except Exception as e:
            print(f"Error creating m3u: {e}")
    
    job_state.status = "done"
    job_state.current_track = ""
    print("Job finished.")

@app.get("/")
def read_root():
    return {"message": "Spotify Downloader API is running"}

@app.get("/api/file")
def get_file(path: str):
    """Serve a specific file from the downloads directory"""
    # Security: Ensure path doesn't escape downloads/
    safe_path = os.path.normpath(os.path.join("downloads", path))
    if not safe_path.startswith("downloads"):
         raise HTTPException(status_code=403, detail="Invalid file path")
    
    if os.path.exists(safe_path):
        return FileResponse(safe_path, filename=os.path.basename(path))
    return {"error": "File not found"}

@app.post("/api/download")
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    if job_state.status == "working":
        raise HTTPException(status_code=400, detail="A download job is already running")
    
    total_tracks = sum(len(p.tracks) for p in request.playlists)
    background_tasks.add_task(run_download_job, request.playlists, request.quality, request.output_path)
    return {"message": "Download started", "total_tracks": total_tracks}

@app.get("/api/status")
def get_status():
    return {
        "status": job_state.status,
        "total": job_state.total,
        "completed": job_state.completed,
        "current_track": job_state.current_track,
        "recent_logs": job_state.logs[-5:] # Return last 5 logs
    }

@app.get("/api/zip")
def download_zip():
    """Zips the 'downloads' folder and returns it"""
    import shutil
    from fastapi.responses import FileResponse
    
    # Path to the folder we want to zip
    folder_path = "downloads"
    zip_name = "spotify_downloads"
    zip_path = f"{zip_name}.zip"
    
    if not os.path.exists(folder_path):
        raise HTTPException(status_code=404, detail="No downloads found")
        
    # Create Zip
    shutil.make_archive(zip_name, 'zip', folder_path)
    
    return FileResponse(path=zip_path, filename=zip_path, media_type='application/zip')

@app.get("/api/choose-directory")
def choose_directory():
    """Opens a native OS folder picker on the server (user's machine)"""
    try:
        # Strategy 1: MacOS Native (osascript) - Best for Mac
        import subprocess
        import sys
        
        if sys.platform == 'darwin':
            try:
                # AppleScript to choose folder
                script = 'tell application "System Events" to activate\nset p to POSIX path of (choose folder with prompt "Select Download Folder")\nreturn p'
                path = subprocess.check_output(['osascript', '-e', script], stderr=subprocess.STDOUT).decode('utf-8').strip()
                if path:
                    return {"path": path}
            except subprocess.CalledProcessError:
                return {"path": None} # User cancelled
            except Exception as e:
                print(f"Mac Picker failed: {e}")
                # Fallthrough to Tkinter

        # Strategy 2: Tkinter (Windows/Linux fallback)
        import tkinter as tk
        from tkinter import filedialog
        
        # Create a hidden root window
        root = tk.Tk()
        root.withdraw() # Hide the main window
        
        # Make sure it appears on top (MacOS/Windows)
        root.attributes('-topmost', True)
        root.lift()
        root.focus_force()
        
        # Open dialog
        path = filedialog.askdirectory(title="Select Download Folder")
        
        root.destroy()
        
        if path:
            return {"path": path}
        return {"path": None}
    except Exception as e:
        print(f"Directory picker error: {e}")
        return {"error": str(e), "path": None}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
