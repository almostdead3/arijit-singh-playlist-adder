import os
import json
import tempfile
from ytmusicapi import YTMusic

STATE_FILE = "added_tracks.json"
ARIJIT_CHANNEL_ID = "UCtjpeRS40g7H8oquOSqkB3g"
BATCH_LIMIT = 20

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

def get_artist_tracks_safely(ytmusic, channel_id):
    """Fetches artist songs across different API response schemas."""
    artist_results = ytmusic.get_artist(channel_id)
    songs_section = artist_results.get("songs", {})
    
    # Method 1: Browse ID present in songs section
    browse_id = songs_section.get("browseId")
    params = songs_section.get("params")
    
    if browse_id:
        try:
            playlist_data = ytmusic.get_playlist(browse_id)
            return playlist_data.get("tracks", [])
        except Exception:
            pass

    # Method 2: Fetch full songs list via get_artist_albums/songs if params exist
    if browse_id and params:
        try:
            return ytmusic.get_artist_albums(channel_id, params)
        except Exception:
            pass

    # Method 3: Direct results array in songs section
    if "results" in songs_section:
        return songs_section["results"]

    # Method 4: Fallback - Search artist's top tracks
    search_results = ytmusic.search(query="Arijit Singh", filter="songs", limit=30)
    return search_results

def main():
    target_playlist_name = os.environ.get("PLAYLIST_ID")
    cookies_raw = os.environ.get("YT_COOKIES")

    if not target_playlist_name or not cookies_raw:
        print("Error: Missing PLAYLIST_ID or YT_COOKIES environment variables.")
        return

    cookie_header = netscape_to_cookie_header(cookies_raw)

    if not cookie_header:
        print("Error: Could not extract valid cookies from YT_COOKIES.")
        return

    # Modern ytmusicapi browser auth structure required by internal parsers
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

    # Write temporary JSON file for ytmusicapi authentication
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

    # Fetch User Playlists
    try:
        playlists = ytmusic.get_library_playlists(limit=None)
    except Exception as e:
        print(f"Error fetching user playlists: {e}")
        return

    target_playlist_id = None
    for pl in playlists:
        if pl.get("title") == target_playlist_name:
            target_playlist_id = pl.get("playlistId")
            break

    if not target_playlist_id:
        print(f"Error: Could not find any playlist named '{target_playlist_name}' in your account.")
        return

    print(f"Found Playlist '{target_playlist_name}' with ID: {target_playlist_id}")

    # Fetch Artist Tracks with fallback logic
    try:
        tracks = get_artist_tracks_safely(ytmusic, ARIJIT_CHANNEL_ID)
    except Exception as e:
        print(f"Error fetching artist tracks: {e}")
        return

    video_ids = [t["videoId"] for t in tracks if isinstance(t, dict) and "videoId" in t]
    print(f"Total tracks retrieved: {len(video_ids)}")

    if not video_ids:
        print("No video IDs found in artist results.")
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
        response = ytmusic.add_playlist_items(target_playlist_id, batch)
        print("API Response status:", response.get("status", "Success"))
        
        for v_id in batch:
            added_tracks.add(v_id)
            
        save_added_tracks(added_tracks)
        print(f"Successfully added {len(batch)} tracks to '{target_playlist_name}'!")
    except Exception as e:
        print(f"Error adding tracks to playlist: {e}")

if __name__ == "__main__":
    main()
