# Offlineify

A minimal, powerful web application to download Spotify playlists to your own laptop, with full metadata and cover art — as M4A (YouTube's original audio, no re-encode) or MP3 if you prefer.

## Features

- 🎵 **Three ways in**: log in with Spotify, paste a playlist link, or upload a CSV export.
- 🔗 **Paste a link**: grab any public playlist URL, no login needed, download the whole thing as a ZIP.
- 🖼️ **Album Art**: embeds high-res Spotify cover art.
- 📜 **M3U8 Generation**: automatically creates playlist files for VLC/iTunes.
- ⚡ **Deduplication**: skips already downloaded songs.
- 💻 **Saves to your laptop**: every file is downloadable from the browser, individually or as one ZIP.
- 🪶 **Light on the server**: M4A is copied without re-encoding, one download runs at a time, and the server deletes every file as soon as you have it.
- ⏸️ **Stop/Cancel**: cancel downloads mid-way, completed files remain available.

## How downloads work

```
Spotify metadata  ──►  matcher.py  ──►  yt-dlp  ──►  M4A/MP3 + tags
(login / link /csv)    (finds the        (downloads     (mutagen)
                        right audio)      the audio)
```

- **Metadata** comes from the Spotify API. The login flow uses your NextAuth session; the paste-link
  flow resolves public playlists (via your token when logged in, or the embed page otherwise).
- **Matching** happens in `web/api/matcher.py`. It searches YouTube Music's *song* catalog via `ytmusicapi`
  and scores each candidate on duration closeness, artist match, title coverage, and a blocklist of
  words like "live", "remix", "cover", and "video". This is the single place where "is this the right
  audio?" is decided, for all three flows.
- **Downloading** uses `yt-dlp` (audio only). The default format is **M4A**: YouTube's AAC stream is
  written to disk as-is — no ffmpeg run, no quality loss. Choosing MP3 re-encodes via ffmpeg.
  `mutagen` then writes the Spotify title, artist, album, track number, year, and cover art.

**Quality note:** YouTube audio tops out around 128–160 kbps. M4A keeps that stream bit-for-bit;
the MP3 option is for compatibility, not extra fidelity.

### Keeping the server light

The backend is built to stay cheap to run on a small Linux box:

- **M4A by default, no re-encode.** ffmpeg only runs for tracks with no AAC stream, or when you pick MP3.
- **One download at a time.** Every job passes through a single global slot; extra jobs queue and the
  UI logs "Waiting for another download to finish...".
- **Streamed ZIPs.** No temp archive and no compression (`stored`): bytes flow straight from disk to
  the browser.
- **Delete after delivery.** As soon as your browser has received a file (Save) or archive (ZIP), it is
  removed from the server. Cancel a download mid-way and the files stay.
- **48-hour safety sweep.** Anything never picked up is deleted after `DOWNLOAD_TTL_HOURS`.

| Env var | Default | Meaning |
|---|---|---|
| `MAX_CONCURRENT_JOBS` | `1` | Simultaneous download jobs across all users |
| `DELETE_AFTER_DOWNLOAD` | `1` | Set to `0` to keep files on the server after delivery |
| `DOWNLOAD_TTL_HOURS` | `48` | Delete unclaimed downloads after this many hours (`0` disables the sweep) |

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

These configure the **frontend** only — create `web/ui/.env.local`:

```env
NEXTAUTH_URL=http://127.0.0.1:3000
NEXTAUTH_SECRET=your_secret_key_here
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

**The backend needs no credentials at all.** When you are logged in, the UI sends
your Spotify access token with each request (in memory only, never stored server-side).
Without login, the paste-link flow reads Spotify's public embed page (first 50 tracks).
YouTube matching and downloading use ytmusicapi/yt-dlp anonymously.

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
| Change ID3/MP4 tags written to files | `web/api/matcher.py` — `write_tags` |
| Change the login/CSV job flow | `web/api/main.py` — `run_download_job` |
| Change the paste-link flow | `web/api/link_download.py` |
| Change what gets deduplicated | `web/api/downloader.py` |
| Change queueing / deletion / sweep behavior | `web/api/housekeeping.py` |
| Change the UI | `web/ui/app/components/` (`Dashboard`, `LinkDownload`, `CSVUpload`) |

Tests live in `tests/`:

```bash
.venv/bin/python tests/test_matcher.py      # offline scoring + format rules, no network
.venv/bin/python tests/test_live_match.py   # live matching checks (network)
.venv/bin/python tests/test_api_flow.py     # full download + file/zip API flow (network)
.venv/bin/python tests/test_cover_embed.py  # M4A/MP3 tag + cover embedding (network)
```

## API Endpoints

### `/api/download` (POST)

Start a download job with Spotify authentication. Headers: `x-user-id` (email).

### `/api/link-download` (POST)

Start a download from a pasted playlist link. Params: `user_id`. Body: `{ url, format }` where
`format` is `"m4a"` (default) or `"mp3"`.

### `/api/csv-download` (POST)

Upload CSV and start download. Form fields: `file`, `format`, `user_id`.

### `/api/cancel` (POST)

Cancel an in-progress download. Params: `user_id`.

### `/api/status` (GET)

Get download progress. Params: `user_id`.

### `/api/file` (GET)

Download a single finished file. Params: `path` (relative to `downloads/`), `user_id`.
The file is deleted from the server once the browser has received it.

### `/api/zip` (GET)

Stream everything under a user's folder as one stored ZIP (no temp file). Params: `user_id`.
The folder is cleared once the browser has received the archive.

### `/api/playlist-zip` (GET)

Stream a single playlist folder as a ZIP, then clear it. Params: `user_id`, `playlist`.

## Troubleshooting

**A track says "No good match found".**
The matcher refuses candidates that are too different in length or look like videos/live takes.
Try the track on YouTube Music manually; you can loosen `MIN_SCORE` or the duration tolerance in
`web/api/matcher.py`.

**Paste-link says it cannot read the playlist.**
Public playlists should work without login (first 50 tracks via the embed page).
For full or private playlists, log in first; the UI then sends your token with the request.

**Downloads are slow.**
Matching and downloading are rate-limited on purpose to avoid IP blocks. Already-cached tracks are
skipped instantly.

**FFmpeg errors.**
Make sure `ffmpeg -version` works in the same environment that runs the backend.

## Docker

```bash
docker build -t offlineify .
docker run -p 8000:8000 offlineify
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
files to your machine: the ZIP download *is* the transfer. And because files are
deleted after delivery (see "Keeping the server light"), the server's disk stays
nearly empty no matter how much music passes through it.

### Running the backend on your own Linux server

```bash
# from the repo root, with .venv set up (see Setup)
.venv/bin/uvicorn web.api.main:app --host 0.0.0.0 --port 8000
```

Put it behind nginx/Caddy for TLS, or run the Docker image. A minimal systemd
unit keeps it alive across reboots; run it as a service user, not root.
Set `NEXT_PUBLIC_BACKEND_URL=https://your-server` (or `http://your-server:8000`)
wherever the frontend runs.

### Deploying the frontend on Vercel (backend elsewhere)

1. Deploy the backend first (your Linux server, or a platform like Render with
   the provided `Dockerfile`).
   - No credentials needed; optionally set the housekeeping env vars
     (`MAX_CONCURRENT_JOBS`, `DOWNLOAD_TTL_HOURS`).
   - Note the service URL, e.g. `https://offlineify-api.example.com`.
2. Deploy the frontend on Vercel from the same repo:
   - Root directory: `web/ui`.
   - Env vars: `NEXT_PUBLIC_BACKEND_URL=https://offlineify-api.example.com`,
     plus `NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`.
3. In the Spotify Developer Dashboard, add the Vercel domain as a Redirect URI.

Notes:
- Vercel only hosts the UI in this split; the backend must be a long-running
  process (it downloads in the background and streams ZIPs to your browser).
- Hosted disks are ephemeral on some platforms: download your ZIPs before the
  service restarts.

Local alternative that keeps everything on your laptop: `docker compose up --build`
for the backend (keeps `downloads/` on your disk) and `npm run dev` for the frontend.

## License

MIT

**Legal note:** downloading audio from YouTube or YouTube Music is against their Terms of Service
even for personal use, and Spotify's developer terms restrict downloader apps. Keep this tool private
and do not redistribute what you download.
