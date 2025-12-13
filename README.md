# Offlineify

A minimal, powerful web application to download high-quality Spotify playlists to your local machine.

## Features
- 🎵 **High Quality**: Downloads 320kbps MP3s with full metadata.
- 🖼️ **Album Art**: Embeds high-res Spotify cover art (square 640x640).
- 📂 **Playlist Support**: Organizes downloads into subfolders by playlist name.
- 📜 **M3U8 Generation**: Automatically creates playlist files for VLC/iTunes.
- ⚡ **Deduplication**: Skips already downloaded songs to save time.
- 📱 **Mobile Friendly**: Control the downloader from your phone (if on the same Wi-Fi).

## Architecture
This app supports two modes:

1.  **Local Mode (Recommended)**:
    - Runs entirely on your computer.
    - Files saved directly to `downloads/`.
    - No setup required.

2.  **Cloud Mode (Render/Netlify)**:
    - **Frontend**: Hosted on Vercel/Netlify.
    - **Backend**: Hosted on Render/Railway.
    - **Filesystem**: Files are saved to the cloud server's specific storage.
    - **Retrieval**: Use the **"Download as ZIP"** button to get your music after the job finishes.

## Prerequisites
1.  **Python 3.8+**
2.  **Node.js 18+**
3.  **FFmpeg** installed (Required for MP3 conversion).

## Setup (Local)

### 1. Backend (Python)
```bash
# Install dependencies
pip install fastapi "uvicorn[standard]" yt_dlp pandas requests Pillow mutagen
# OR
pip install -r requirements.txt
```

### 2. Frontend (Next.js)
```bash
cd web/ui
npm install
```

### 3. Environment Variables
Create `web/ui/.env.local` with your Spotify Credentials:
```env
NEXTAUTH_URL=http://127.0.0.1:3000
NEXTAUTH_SECRET=your_secret_key_here
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

## Usage

1.  **Start the Backend**:
    ```bash
    python3 -m web.api.main
    ```

2.  **Start the Frontend**:
    ```bash
    cd web/ui
    npm run dev
    ```

3.  Open `http://localhost:3000` -> Login -> Download -> Enjoy! 🎵

## Hosting Guide

### Deploying the Frontend (Vercel/Netlify)
1.  Push this repo to GitHub.
2.  Import into Vercel/Netlify.
3.  Set Environment Variables (`SPOTIFY_CLIENT_ID`, etc).
4.  **Important**: If deploying Frontend to Cloud, you must also deploy Backend to Cloud (due to CORS/Network visibility), OR use a tunnel like **ngrok** for your local backend.

### Deploying the Backend (Render)
1.  Create a Web Service on Render.
2.  Command: `uvicorn web.api.main:app --host 0.0.0.0 --port $PORT`.
3.  Note: Render Free Tier spins down after inactivity.
