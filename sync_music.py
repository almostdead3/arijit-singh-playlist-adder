import os
import json
from ytmusicapi import YTMusic

def main():
    if not os.path.exists("browser.json"):
        print("Error: browser.json was not generated.")
        return
        
    # Explicitly load the JSON headers and pass them into YTMusic as headers=
    with open("browser.json", "r") as f:
        headers = json.load(f)
    
    yt = YTMusic(headers=headers)
    playlist_id = os.environ.get("PLAYLIST_ID")

    if not playlist_id:
        print("Error: Missing PLAYLIST_ID environment variable.")
        return

    target_url = "https://music.youtube.com/playlist?list=OLAK5uy_nq81InQBifozkEJvDr7L9K3kURX7BfMlo"
    
    print(f"Target Source URL: {target_url}")
    track_ids = []

    try:
        if "playlist?list=" in target_url or "OLAK" in target_url:
            playlist_id_param = target_url.split("list=")[1].split("&")[0]
            print(f"Fetching ALL tracks from source playlist (limit=None)...")
            data = yt.get_playlist(playlist_id_param, limit=None)
            if "tracks" in data:
                for t in data["tracks"]:
                    if "videoId" in t:
                        track_ids.append(t["videoId"])
        elif "channel/" in target_url or "@" in target_url:
            print("Fetching ALL tracks from Artist page...")
            artist_data = yt.get_artist("UCtFOW7jJXChfFNoucRFqRmw")
            for section in ["albums", "singles", "videos"]:
                if section in artist_data and "results" in artist_data[section]:
                    for item in artist_data[section]["results"]:
                        if "browseId" in item:
                            try:
                                album_info = yt.get_album(item["browseId"])
                                if "tracks" in album_info:
                                    for t in album_info["tracks"]:
                                        if "videoId" in t:
                                            track_ids.append(t["videoId"])
                            except Exception:
                                pass
    except Exception as e:
        print(f"Error fetching source tracks: {e}")
        return

    unique_source_ids = list(set(track_ids))
    print(f"Total unique source track IDs found: {len(unique_source_ids)}")

    # Fetch existing playlist items completely
    existing_track_ids = set()
    try:
        playlist_data = yt.get_playlist(playlist_id, limit=None)
        if "tracks" in playlist_data:
            existing_track_ids = {t["videoId"] for t in playlist_data["tracks"] if "videoId" in t}
    except Exception as e:
        print(f"Notice reading existing playlist: {e}")

    pending_ids = [vid for vid in unique_source_ids if vid not in existing_track_ids]
    print(f"Total new songs to add: {len(pending_ids)}")

    if not pending_ids:
        print("Your playlist is already fully up to date!")
        return

    print("Adding every single missing song to your playlist now...")
    try:
        response = yt.add_playlist_items(playlist_id, pending_ids)
        print(f"Success! All {len(pending_ids)} songs have been added.")
    except Exception as e:
        print(f"Error adding tracks: {e}")

if __name__ == "__main__":
    main()
