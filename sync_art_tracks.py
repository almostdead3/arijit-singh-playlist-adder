import os
import json
import tempfile
from ytmusicapi import YTMusic

STATE_FILE = "added_tracks.json"
BATCH_LIMIT = 2000

def load_added_tracks():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_added_tracks(added_set):
    with open(STATE_FILE, "w") as f:
        json.dump(list(added_set), f, indent=2)

def netscape_to_cookie_header(cookies_raw):
    """Converts raw Netscape cookies into a Cookie header string."""
    cookie_pairs = []
    for line in cookies_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("# ") or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue

        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]

        parts = line.split("\t")
        if len(parts) >= 7:
            domain = parts[0].strip()
            name = parts[5].strip()
            value = parts[6].strip()

            if "youtube.com" in domain or "google.com" in domain:
                if name and value:
                    cookie_pairs.append(f"{name}={value}")

    return "; ".join(cookie_pairs)

def fetch_arijit_tracks(ytmusic):
    """Directly scrapes tracks from Arijit Singh's official channel releases and albums."""
    video_ids = []
    seen = set()
    
    # Arijit Singh's Official Channel ID
    CHANNEL_ID = "UCtFOW7jJXChfFNoucRFqRmw"

    print("Fetching tracks from Arijit Singh's official channel releases...")

    try:
        artist_info = ytmusic.get_artist(CHANNEL_ID)
        
        # 1. Grab tracks directly from featured songs list on his profile
        if "songs" in artist_info and "results" in artist_info["songs"]:
            for song in artist_info["songs"]["results"]:
                if isinstance(song, dict) and "videoId" in song and song["videoId"]:
                    v_id = song["videoId"]
                    if v_id not in seen:
                        seen.add(v_id)
                        video_ids.append(v_id)

        # 2. Iterate through his releases/albums/singles sections
        for key in ["albums", "singles", "videos", "featured", "releases"]:
            if key in artist_info and isinstance(artist_info[key], dict):
                sec = artist_info[key]
                if "browseId" in sec and "params" in sec:
                    try:
                        full_list = ytmusic.get_artist_albums(sec["browseId"], sec["params"])
                        for entry in full_list:
                            if "browseId" in entry:
                                album_data = ytmusic.get_album(entry["browseId"])
                                for track in album_data.get("tracks", []):
                                    if "videoId" in track and track["videoId"]:
                                        v_id = track["videoId"]
                                        if v_id not in seen:
                                            seen.add(v_id)
                                            video_ids.append(v_id)
                    except Exception as e:
                        print(f"Pagination warning for section {key}: {e}")
                elif "results" in sec:
                    for item in sec["results"]:
                        if "browseId" in item:
                            try:
                                album_data = ytmusic.get_album(item["browseId"])
                                for track in album_data.get("tracks", []):
                                    if "videoId" in track and track["videoId"]:
                                        v_id = track["videoId"]
                                        if v_id not in seen:
                                            seen.add(v_id)
                                            video_ids.append(v_id)
                            except Exception:
                                pass
    except Exception as e:
        print(f"Official channel release scraping warning: {e}")

    return video_ids

def main():
    cookies_raw = os.environ.get("YT_COOKIES")
    if not cookies_raw:
        print("Error: Missing YT_COOKIES environment variable.")
        return

    cookie_header = netscape_to_cookie_header(cookies_raw)
    if not cookie_header:
        print("Error: Could not extract valid cookies from YT_COOKIES.")
        return

    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/json",
        "X-Goog-AuthUser": "0",
        "x-origin": "https://music.youtube.com",
        "Cookie": cookie_header,
        "authorization": "SAPISIDHASH 123456789_abcdef"
    }

    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as tmp:
        json.dump(browser_headers, tmp)
        temp_auth_path = tmp.name

    try:
        ytmusic = YTMusic(auth=temp_auth_path)
        print("Successfully authenticated with YouTube Music API!")
    except Exception as e:
        print(f"Standard auth warning: {e}. Falling back to session headers...")
        ytmusic = YTMusic()
        ytmusic.auth = temp_auth_path
        if hasattr(ytmusic, "_session"):
            ytmusic._session.headers.update(browser_headers)
        elif hasattr(ytmusic, "session"):
            ytmusic.session.headers.update(browser_headers)
    finally:
        if os.path.exists(temp_auth_path):
            os.remove(temp_auth_path)

    # Use the direct playlist ID to avoid text lookup or masking issues
    target_playlist_id = "PLIV4BTGhTGJQ"
    print(f"Target Playlist ID set to: {target_playlist_id}")

    # Fetch Tracks from Official Channel Releases
    video_ids = fetch_arijit_tracks(ytmusic)
    print(f"Total tracks retrieved: {len(video_ids)}")

    if not video_ids:
        print("No video IDs retrieved.")
        return

    added_tracks = load_added_tracks()
    pending = [v for v in video_ids if v not in added_tracks]
    print(f"Pending tracks remaining: {len(pending)}")

    if not pending:
        print("All tracks are up to date!")
        return

    batch = pending[:BATCH_LIMIT]
    
    # Add items to playlist
    try:
        response = ytmusic.add_playlist_items(target_playlist_id, batch, duplicates=True)
        status = response.get("status", "Unknown") if isinstance(response, dict) else "STATUS_SUCCEEDED"
        print("API Batch Response status:", status)
        
        if status == "STATUS_FAILED":
            print("Batch rejected by API! Attempting fallback: adding tracks individually...")
            added_count = 0
            for v_id in batch:
                try:
                    res = ytmusic.add_playlist_items(target_playlist_id, [v_id], duplicates=True)
                    item_status = res.get("status", "Unknown") if isinstance(res, dict) else "STATUS_SUCCEEDED"
                    if item_status != "STATUS_FAILED":
                        added_tracks.add(v_id)
                        added_count += 1
                except Exception as item_e:
                    print(f"Failed to add track {v_id}: {item_e}")
            
            save_added_tracks(added_tracks)
            print(f"Fallback complete: Successfully added {added_count} tracks individually!")
        else:
            for v_id in batch:
                added_tracks.add(v_id)
                
            save_added_tracks(added_tracks)
            print(f"Successfully added {len(batch)} tracks to playlist!")

    except Exception as e:
        print(f"Error adding tracks to playlist: {e}")

if __name__ == "__main__":
    main()
