# Offlineify

A minimal, powerful web application to download Spotify playlists to your own laptop, as high-quality MP3s with full metadata.

## Features

- 🎵 **Three ways in**: log in with Spotify, paste a playlist link, or upload a CSV export.
- 🔗 **Paste a link**: grab any public playlist URL, no login needed, download the whole thing as a ZIP.
- 🖼️ **Album Art**: embeds high-res Spotify cover art.
- 📜 **M3U8 Generation**: automatically creates playlist files for VLC/iTunes.
- ⚡ **Deduplication**: skips already downloaded songs.
- 💻 **Saves to your laptop**: every file is downloadable from the browser, individually or as one ZIP.
- ⏸️ **Stop/Cancel**: cancel downloads mid-way, completed files remain available.

## How downloads work

```
Spotify metadata  ──►  matcher.py  ──►  yt-dlp  ──►  MP3 + ID3 tags
(login / link /csv)    (finds the        (downloads     (mutagen)
                        right audio)      the audio)
```

- **Metadata** comes from the Spotify API. The login flow uses your NextAuth session; the paste-link
  flow uses `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` (a public playlist only needs app credentials).
- **Matching** happens in `web/api/matcher.py`. It searches YouTube Music's *song* catalog via `ytmusicapi`
  and scores each candidate on duration closeness, artist match, title coverage, and a blocklist of
  words like "live", "remix", "cover", and "video". This is the single place where "is this the right
  audio?" is decided, for all three flows.
- **Downloading** uses `yt-dlp` (audio only) and FFmpeg to produce an MP3, then `mutagen` writes the
  Spotify title, artist, album, track number, year, and cover art.

**Quality note:** YouTube audio tops out around 128–160 kbps. Selecting "320kbps" sets the MP3 output
bitrate, but it cannot add detail the source doesn't have. Use it for compatibility, not fidelity.

## Setup (local)

### 1. Backend (Python)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

FFmpeg is required: `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Linux).

### 2. Frontend (Next.js)

```bash
cd web/ui
npm install
```

### 3. Environment Variables

Create `web/ui/.env.local`:

```env
NEXTAUTH_URL=http://127.0.0.1:3000
NEXTAUTH_SECRET=your_secret_key_here
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

The backend reads `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` from the environment, and falls back to
`web/ui/.env.local` when running locally. Without them, only the paste-link flow is disabled;
login and CSV upload keep working.

### 4. Run it

```bash
# terminal 1 - backend
.venv/bin/uvicorn web.api.main:app --port 8000

# terminal 2 - frontend
cd web/ui && npm run dev
```

Open `http://localhost:3000`. The browser saves downloads to your usual Downloads folder.

## Usage

### Option 1: With Spotify Login

Login → pick playlists → Download → each track becomes a "Save" link, plus a "Download as ZIP" button.

### Option 2: Paste a Playlist Link

Paste any public Spotify playlist URL (`https://open.spotify.com/playlist/...`) → Download Playlist.
Watch progress live, cancel anytime, grab the finished playlist as a ZIP.

### Option 3: CSV Upload (No Login)

Export your playlist as CSV and upload it. Same progress and download behavior as above.

## Where to change things

| I want to... | Edit |
|---|---|
| Tune matching (durations, keywords, scores) | `web/api/matcher.py` — constants at the top |
| Change the download/convert step | `web/api/matcher.py` — `download_match`, `ytdlp_download_options` |
| Change ID3 tags written to files | `web/api/matcher.py` — `write_tags` |
| Change the login/CSV job flow | `web/api/main.py` — `run_download_job` |
| Change the paste-link flow | `web/api/link_download.py` |
| Change what gets deduplicated | `web/api/downloader.py` |
| Change the UI | `web/ui/app/components/` (`Dashboard`, `LinkDownload`, `CSVUpload`) |

Tests live in `tests/`:

```bash
.venv/bin/python tests/test_matcher.py      # offline scoring rules, no network
.venv/bin/python tests/test_live_match.py   # live matching checks (network)
.venv/bin/python tests/test_api_flow.py     # full download + file/zip API flow (network)
```

## API Endpoints

### `/api/download` (POST)

Start a download job with Spotify authentication. Headers: `x-user-id` (email).

### `/api/link-download` (POST)

Start a download from a pasted playlist link. Params: `user_id`. Body: `{ url, quality }`.

### `/api/csv-download` (POST)

Upload CSV and start download. Params: `quality`, `user_id`.

### `/api/cancel` (POST)

Cancel an in-progress download. Params: `user_id`.

### `/api/status` (GET)

Get download progress. Params: `user_id`.

### `/api/file` (GET)

Download a single finished file. Params: `path` (relative to `downloads/`), `user_id`.

### `/api/zip` (GET)

Download everything under a user's folder as one ZIP. Params: `user_id`.

### `/api/playlist-zip` (GET)

Download a single playlist folder as a ZIP. Params: `user_id`, `playlist`.

## Troubleshooting

**A track says "No good match found".**
The matcher refuses candidates that are too different in length or look like videos/live takes.
Try the track on YouTube Music manually; you can loosen `MIN_SCORE` or the duration tolerance in
`web/api/matcher.py`.

**Paste-link says credentials are missing.**
Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `web/ui/.env.local` or the environment.

**Downloads are slow.**
Matching and downloading are rate-limited on purpose to avoid IP blocks. Already-cached tracks are
skipped instantly.

**FFmpeg errors.**
Make sure `ffmpeg -version` works in the same environment that runs the backend.

## Docker

```bash
docker build -t offlineify .
docker run -p 8000:8000 -e SPOTIFY_CLIENT_ID=... -e SPOTIFY_CLIENT_SECRET=... offlineify
```

In Docker there is no browser and no folder picker; use the ZIP buttons to retrieve music.

## Hosting and "where do files go?"

The app has two pieces and they want different hosts:

| Piece | Needs | Suggested host |
|---|---|---|
| Frontend (Next.js) | Static/SSR web hosting | Vercel, Netlify |
| Backend (FastAPI + yt-dlp + ffmpeg) | Long-running process, ~100MB+ disk, background jobs | Render, Railway, Fly.io, or your own machine |

**Do not deploy the backend to Vercel.** Serverless functions cannot run this backend:
they time out long before a playlist finishes, each request may hit a different
instance, the in-memory job state disappears between requests, and there is no
persistent disk for the downloaded MP3s. Vercel is fine for the frontend only.

### How downloads reach your laptop

The backend always writes files on the machine that runs *it*. The web app gets
them to you over HTTP:

- **Save** links fetch one finished song (`/api/file`).
- **Download as ZIP** fetches a whole playlist in one file (`/api/playlist-zip`)
  and the browser saves it to your Downloads folder.

That flow works from any browser, including when the backend runs on a server
somewhere and you only have the frontend URL. There is no extra step to "push"
files to your machine: the ZIP download *is* the transfer.

### Deploying frontend on Vercel + backend on Render

1. Deploy the backend first:
   - New Web Service from this repo; it has a `Dockerfile`, so pick Docker.
   - Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` env vars.
   - Note the service URL, e.g. `https://offlineify-api.onrender.com`.
2. Deploy the frontend on Vercel from the same repo:
   - Root directory: `web/ui`.
   - Env vars: `NEXT_PUBLIC_BACKEND_URL=https://offlineify-api.onrender.com`,
     plus `NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`.
3. In the Spotify Developer Dashboard, add the Vercel domain as a Redirect URI.

Notes:
- Free tiers sleep after inactivity; the first request can take up to a minute.
- Hosted disks are ephemeral: download your ZIPs before the service restarts.

Local alternative that keeps everything on your laptop: `docker compose up --build`
for the backend (keeps `downloads/` on your disk) and `npm run dev` for the frontend.

## License

MIT

**Legal note:** downloading audio from YouTube or YouTube Music is against their Terms of Service
even for personal use, and Spotify's developer terms restrict downloader apps. Keep this tool private
and do not redistribute what you download.
