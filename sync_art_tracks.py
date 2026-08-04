import os
import json
from ytmusicapi import YTMusic

STATE_FILE = "added_tracks.json"
# Official Arijit Singh - Topic Channel ID
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

def main():
    target_playlist_name = os.environ.get("PLAYLIST_ID")
    cookies_raw = os.environ.get("YT_COOKIES")

    if not target_playlist_name or not cookies_raw:
        print("Error: Missing PLAYLIST_ID or YT_COOKIES environment variables.")
        return

    # Write cookies_raw temporarily for ytmusicapi initialization
    with open("cookie_file.txt", "w") as f:
        f.write(cookies_raw)

    try:
        # Initialize YTMusic with Netscape cookies file directly
        ytmusic = YTMusic("cookie_file.txt")
        print("Successfully authenticated with YouTube Music API!")
    except Exception as e:
        print(f"Authentication Error: {e}")
        return
    finally:
        if os.path.exists("cookie_file.txt"):
            os.remove("cookie_file.txt")

    # Locate Target Playlist ID by Name
    playlists = ytmusic.get_user_playlists()
    target_playlist_id = None

    for pl in playlists:
        if pl.get("title") == target_playlist_name:
            target_playlist_id = pl.get("playlistId")
            break

    if not target_playlist_id:
        print(f"Error: Could not find any playlist named '{target_playlist_name}' in your account.")
        return

    print(f"Found Playlist '{target_playlist_name}' with ID: {target_playlist_id}")

    # Fetch Artist Tracks
    try:
        artist_results = ytmusic.get_artist(ARIJIT_CHANNEL_ID)
        songs_section = artist_results.get("songs", {})
        
        # Get full track list if browseId is available
        if "browseId" in songs_section and songs_section["browseId"]:
            tracks = ytmusic.get_playlist(songs_section["browseId"])["tracks"]
        else:
            tracks = songs_section.get("results", [])
            
    except Exception as e:
        print(f"Error fetching artist tracks: {e}")
        return

    video_ids = [t["videoId"] for t in tracks if "videoId" in t]
    print(f"Total tracks retrieved from channel: {len(video_ids)}")

    added_tracks = load_added_tracks()
    pending = [v for v in video_ids if v not in added_tracks]
    print(f"Pending tracks remaining: {len(pending)}")

    if not pending:
        print("All tracks are up to date!")
        return

    batch = pending[:BATCH_LIMIT]
    
    # Add tracks directly via API
    try:
        response = ytmusic.add_playlist_items(target_playlist_id, batch)
        print("API Response:", response)
        
        for v_id in batch:
            added_tracks.add(v_id)
            
        save_added_tracks(added_tracks)
        print(f"Successfully added {len(batch)} tracks to '{target_playlist_name}'!")
    except Exception as e:
        print(f"Error adding tracks to playlist: {e}")

if __name__ == "__main__":
    main()
