import yt_dlp
import os
import json
import pandas as pd
import requests
from PIL import Image
import io
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TALB, TPE1, TIT2, TDRC, TRCK, TXXX, error

DOWNLOAD_INDEX_FILE = 'downloaded_songs.json'
DOWNLOAD_DIR = 'downloads'

def load_download_index():
    if os.path.exists(DOWNLOAD_INDEX_FILE):
        try:
            with open(DOWNLOAD_INDEX_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading index file: {e}")
            return {}
    return {}

def save_download_index(index):
    try:
        with open(DOWNLOAD_INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=4)
    except Exception as e:
        print(f"Error saving index file: {e}")

def process_track(track, ydl_opts=None):
    """
    Downloads a single track using the logic:
    1. Check Index (Deduplication)
    2. Smart Selection (3-way Comparison)
    3. Download
    4. Embed Square-Crop Art
    5. Update Index
    """
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    download_index = load_download_index()
    
    track_uri = track.get('uri')
    track_name = track.get('name')
    artist_name = track.get('artist')
    
    # Use provided output_dir or default
    output_dir = ydl_opts.get('output_dir', DOWNLOAD_DIR) if ydl_opts else DOWNLOAD_DIR
    
    # 1. Deduplication (Check actual file existence too?)
    # For now, we stick to the index check, but maybe we should check the new folder?
    # Let's keep index check global for simplicity.
    # 1. Deduplication (Enhanced for Custom Paths)
    if track_uri in download_index:
        recorded_filename = download_index[track_uri].get('filename')
        if recorded_filename:
            # Check if it exists in the CURRENT output directory
            expected_path = os.path.join(output_dir, recorded_filename)
            if os.path.exists(expected_path):
                 return {"status": "skipped", "message": "Already downloaded", "filename": recorded_filename}

    # Default options if not provided
    if ydl_opts is None:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
        }
    else:
        # Ensure outtmpl uses the correct directory
        if 'output_dir' in ydl_opts:
             ydl_opts['outtmpl'] = os.path.join(ydl_opts['output_dir'], '%(title)s.%(ext)s')
             # Ensure dir exists
             if not os.path.exists(ydl_opts['output_dir']):
                 os.makedirs(ydl_opts['output_dir'])

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # search queries
            query_official = f"{artist_name} - {track_name} audio"
            query_lyrics = f"{artist_name} - {track_name} lyrics"
            
            # 1. Fetch metadata for "Official" search
            info_official = ydl.extract_info(f"ytsearch1:{query_official}", download=False)
            if 'entries' in info_official:
                info_official = info_official['entries'][0]
            
            # 2. Fetch metadata for "Lyrics" search (Top 2)
            info_lyrics_results = ydl.extract_info(f"ytsearch2:{query_lyrics}", download=False)
            lyrics_candidates = []
            if 'entries' in info_lyrics_results:
                 for entry in info_lyrics_results['entries']:
                     lyrics_candidates.append(entry)
            
            # 3. Smart Selection V2
            candidates = [info_official] + lyrics_candidates
            candidates = [c for c in candidates if c]

            if not candidates:
                 return {"status": "error", "message": "No results found"}

            official_duration = info_official.get('duration', 0)
            valid_candidates = [c for c in candidates if c.get('duration', 0) > 30]
            if not valid_candidates:
                 valid_candidates = candidates

            shortest_candidate = min(valid_candidates, key=lambda x: x.get('duration', 0))
            
            # Logic: If max diff > 2s, pick shortest. Else Official.
            max_diff = 0
            if valid_candidates:
                durations = [c.get('duration', 0) for c in valid_candidates]
                max_diff = max(durations) - min(durations)

            selected_info = info_official
            if max_diff > 2:
                selected_info = shortest_candidate

            # 4. Download
            result = ydl.extract_info(selected_info['webpage_url'], download=True)
            if 'entries' in result:
                video_info = result['entries'][0]
            else:
                video_info = result

            original_filename = ydl.prepare_filename(video_info)
            base_name = os.path.splitext(os.path.basename(original_filename))[0]
            final_filename = f"{base_name}.mp3"
            
            # Fix: Use output_dir for the tagging path, NOT the default DOWNLOAD_DIR
            file_path = os.path.join(output_dir, final_filename)
            
            # 5. Embed Cover Art (Force Official Thumbnail + Square Crop)
            # Priority: Provided Spotify URL > Official YouTube Thumbnail
            cover_url = track.get('cover_url') or info_official.get('thumbnail')
            is_spotify_image = bool(track.get('cover_url'))
            
            if cover_url:
                try:
                    resp = requests.get(cover_url)
                    img = Image.open(io.BytesIO(resp.content))
                    
                    # Square Crop (Only if NOT from Spotify)
                    # Spotify images are 640x640 (Square) already.
                    if not is_spotify_image:
                        width, height = img.size
                        min_dim = min(width, height)
                        left = (width - min_dim) / 2
                        top = (height - min_dim) / 2
                        right = (width + min_dim) / 2
                        bottom = (height + min_dim) / 2
                        img_cropped = img.crop((left, top, right, bottom))
                    else:
                        img_cropped = img # No crop needed
                    
                    output_io = io.BytesIO()
                    img_cropped.convert('RGB').save(output_io, format='JPEG')
                    processed_data = output_io.getvalue()
                    
                    audio = MP3(file_path, ID3=ID3)
                    try: audio.add_tags()
                    except error: pass

                    audio.tags.add(
                        APIC(
                            encoding=3,
                            mime='image/jpeg',
                            type=3,
                            desc=u'Cover',
                            data=processed_data
                        )
                    )
                    
                    # Add Standard Metadata
                    audio.tags.add(TIT2(encoding=3, text=track_name))
                    audio.tags.add(TPE1(encoding=3, text=artist_name))
                    
                    if track.get('album'):
                        audio.tags.add(TALB(encoding=3, text=track['album']))
                        
                    if track.get('release_date'):
                         audio.tags.add(TDRC(encoding=3, text=track['release_date']))
                         
                    if track.get('track_number'):
                        # TRCK format: "current/total" or just "current"
                        trck_val = str(track['track_number'])
                        if track.get('total_tracks'):
                            trck_val += f"/{track['total_tracks']}"
                        audio.tags.add(TRCK(encoding=3, text=trck_val))
                        
                    # Explicit Tag (iTunes proprietary but standard)
                    # 1 = Explicit, 0 = Clean, 2 = Clean version of explicit
                    if track.get('explicit') is not None:
                        flag = '1' if track['explicit'] else '0'
                        audio.tags.add(TXXX(encoding=3, desc='ITUNESADVISORY', text=flag))

                    audio.save()
                except Exception as e:
                    print(f"Cover art error: {e}")

            # Update index
            download_index[track_uri] = {
                'name': track_name,
                'artist': artist_name,
                'filename': final_filename,
                'downloaded_at': pd.Timestamp.now().isoformat()
            }
            save_download_index(download_index)
            return {"status": "success", "filename": final_filename}

    except Exception as e:
        return {"status": "error", "message": str(e)}
