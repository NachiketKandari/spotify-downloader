# Offlineify

A minimal, powerful web application to download high-quality Spotify playlists to your local machine.

## Features

- 🎵 **High Quality**: Downloads 320kbps MP3s with full metadata.
- 🖼️ **Album Art**: Embeds high-res Spotify cover art (square 640x640).
- 📂 **Playlist Support**: Organizes downloads into subfolders by playlist name.
- 📜 **M3U8 Generation**: Automatically creates playlist files for VLC/iTunes.
- ⚡ **Deduplication**: Skips already downloaded songs to save time.
- 📱 **Mobile Friendly**: Control the downloader from your phone (if on the same Wi-Fi).
- 📤 **CSV Upload**: Download playlists without logging in - just upload a Spotify CSV export!
- ⏸️ **Stop/Cancel**: Cancel downloads mid-way, completed files remain available.

## Recent Updates (Dec 2023)

### CSV Upload Feature

- **No Login Required**: Upload a Spotify CSV export directly without authentication
- **Real-time Progress**: See downloads happen live with individual file links
- **Stop Anytime**: Cancel downloads mid-way, keep what's completed
- **Concurrent Sessions**: Multiple users can download simultaneously

### UI Improvements

- Full-screen landing page with smooth scrolling
- Mobile-responsive buttons and layouts
- Dark theme throughout (no white flash on scroll)
- Clear upload/download icons

## Architecture

This app supports two modes:

1. **Local Mode (Recommended)**:
    - Runs entirely on your computer.
    - Files saved directly to `downloads/`.
    - No setup required.

2. **Cloud Mode (Render/Netlify)**:
    - **Frontend**: Hosted on Vercel/Netlify.
    - **Backend**: Hosted on Render/Railway.
    - **Filesystem**: Files are saved to the cloud server's specific storage.
    - **Retrieval**: Use the **"Download as ZIP"** button to get your music after the job finishes.

## Prerequisites

1. **Python 3.8+**
2. **Node.js 18+**
3. **FFmpeg** installed (Required for MP3 conversion).

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

### Option 1: With Spotify Login

1. **Start the Backend**:

    ```bash
    python3 -m web.api.main
    ```

2. **Start the Frontend**:

    ```bash
    cd web/ui
    npm run dev
    ```

3. Open `http://localhost:3000` → Login → Download → Enjoy! 🎵

### Option 2: CSV Upload (No Login)

1. **Export your Spotify playlist as CSV** from Spotify
2. **Start Backend & Frontend** (same as above)
3. Open `http://localhost:3000` → Click **"Upload Playlist"**
4. Upload your CSV file → Select quality → Start Download
5. Watch real-time progress and download files individually or as ZIP

**Features**:

- ✅ No authentication required
- ✅ Real-time download progress
- ✅ Stop downloads anytime
- ✅ Individual file downloads or bulk ZIP
- ✅ Concurrent sessions supported

## Hosting Guide

### Deploying the Frontend (Vercel/Netlify)

1. Push this repo to GitHub.
2. Import into Vercel/Netlify.
3. Set Environment Variables (`SPOTIFY_CLIENT_ID`, etc).
4. **Important**: If deploying Frontend to Cloud, you must also deploy Backend to Cloud (due to CORS/Network visibility), OR use a tunnel like **ngrok** for your local backend.

### Deploying the Backend (Render)

1. Create a Web Service on Render.
2. Command: `uvicorn web.api.main:app --host 0.0.0.0 --port $PORT`.
3. Note: Render Free Tier spins down after inactivity.

## API Endpoints

### `/api/download` (POST)

Start a download job with Spotify authentication

- **Headers**: `x-user-id` (email)
- **Body**: `{ playlists, quality, output_path }`

### `/api/csv-download` (POST)

Upload CSV and start download (no auth required)

- **Body**: `multipart/form-data` with CSV file
- **Params**: `quality`, `user_id` (auto-generated)

### `/api/cancel` (POST)

Cancel an in-progress download

- **Params**: `user_id`

### `/api/status` (GET)

Get download progress

- **Params**: `user_id`

### `/api/zip` (GET)

Download all completed files as ZIP

- **Params**: `user_id`

## CSV Format

Expected columns in Spotify CSV export:

- `Track URI`, `Track Name`, `Artist Name(s)`, `Album Name`
- `Album Image URL`, `Album Release Date`, `Track Number`
- `Explicit`

## Mobile Support

The application is fully responsive:

- Buttons stack vertically on small screens
- Full-screen sections for better focus
- Touch-friendly controls
- Smooth scrolling navigation

## Troubleshooting

**Downloads not starting?**

- Check if FFmpeg is installed: `ffmpeg -version`
- Verify backend is running on port 8000
- Check browser console for errors

**White background flash when scrolling?**

- Fixed in latest version with consistent black background

**CSV upload not working?**

- Ensure CSV has all required columns
- Check file format is UTF-8
- Verify backend logs for parsing errors

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## License

MIT
