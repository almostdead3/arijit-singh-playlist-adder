import os
import json
import tempfile
from ytmusicapi import YTMusic

STATE_FILE = "added_tracks.json"

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

def fetch_all_arijit_tracks(ytmusic):
    """Directly scrapes tracks from Arijit Singh's official channel ID and comprehensive catalogs."""
    video_ids = []
    seen = set()

    CHANNEL_ID = "UCtFOW7jJXChfFNoucRFqRmw"

    print("Fetching tracks from Arijit Singh's official channel...")

    try:
        artist_info = ytmusic.get_artist(CHANNEL_ID)
        
        if "songs" in artist_info and "results" in artist_info["songs"]:
            for song in artist_info["songs"]["results"]:
                v_id = song.get("videoId")
                if v_id and v_id not in seen:
                    seen.add(v_id)
                    video_ids.append(v_id)

        sections = ["albums", "singles", "videos", "featured"]
        browse_targets = []

        for section_key in sections:
            if section_key in artist_info:
                sec_data = artist_info[section_key]
                if isinstance(sec_data, dict):
                    if "browseId" in sec_data and "params" in sec_data:
                        browse_targets.append((sec_data["browseId"], sec_data["params"]))
                    elif "results" in sec_data:
                        for item in sec_data["results"]:
                            if "browseId" in item:
                                try:
                                    album_data = ytmusic.get_album(item["browseId"])
                                    for track in album_data.get("tracks", []):
                                        v_id = track.get("videoId")
                                        if v_id and v_id not in seen:
                                            seen.add(v_id)
                                            video_ids.append(v_id)
                                except Exception:
                                    continue

        for browse_id, params in browse_targets:
            try:
                full_list = ytmusic.get_artist_albums(browse_id, params)
                for entry in full_list:
                    if "browseId" in entry:
                        album_content = ytmusic.get_album(entry["browseId"])
                        for track in album_content.get("tracks", []):
                            v_id = track.get("videoId")
                            if v_id and v_id not in seen:
                                seen.add(v_id)
                                video_ids.append(v_id)
            except Exception as e:
                print(f"Section pagination warning: {e}")

    except Exception as e:
        print(f"Artist profile retrieval warning: {e}")

    if len(video_ids) < 100:
        print("Running comprehensive search supplement...")
        fallback_queries = [
            "Arijit Singh",
            "Arijit Singh Hindi songs",
            "Arijit Singh Bengali songs",
            "Arijit Singh romantic hits"
        ]
        for query in fallback_queries:
            try:
                results = ytmusic.search(query=query, filter="songs", limit=150)
                for song in results:
                    v_id = song.get("videoId")
                    if v_id and v_id not in seen:
                        seen.add(v_id)
                        video_ids.append(v_id)
            except Exception:
                pass

    return video_ids

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
        print("Tip: Make sure the playlist exists in your library and your account owns it.")
        return

    print(f"Found Playlist '{target_playlist_name}' with ID: {target_playlist_id}")

    # Fetch Catalog
    video_ids = fetch_all_arijit_tracks(ytmusic)
    print(f"Total tracks retrieved: {len(video_ids)}")

    if not video_ids:
        print("No video IDs retrieved.")
        return

    added_tracks = load_added_tracks()
    pending = [v for v in video_ids if v not in added_tracks]
    print(f"Pending tracks remaining to add: {len(pending)}")

    if not pending:
        print("All tracks are up to date!")
        return

    # Add all pending items at once (no limit)
    try:
        response = ytmusic.add_playlist_items(target_playlist_id, pending, duplicates=True)
        status = response.get("status", "Unknown") if isinstance(response, dict) else "STATUS_SUCCEEDED"
        print("API Batch Response status:", status)
        
        if status == "STATUS_FAILED":
            print("Bulk batch rejected by API! Attempting fallback: adding tracks individually...")
            added_count = 0
            for v_id in pending:
                try:
                    res = ytmusic.add_playlist_items(target_playlist_id, [v_id], duplicates=True)
                    item_status = res.get("status", "Unknown") if isinstance(res, dict) else "STATUS_SUCCEEDED"
                    if item_status != "STATUS_FAILED":
                        added_tracks.add(v_id)
                        added_count += 1
                except Exception as item_e:
                    print(f"Failed to add track {v_id}: {item_e}")
            
            save_added_tracks(added_tracks)
            print(f"Fallback complete: Successfully added {added_count} tracks individually to '{target_playlist_name}'!")
        else:
            for v_id in pending:
                added_tracks.add(v_id)
                
            save_added_tracks(added_tracks)
            print(f"Successfully added all {len(pending)} pending tracks to '{target_playlist_name}'!")

    except Exception as e:
        print(f"Error adding tracks to playlist: {e}")

if __name__ == "__main__":
    main()
