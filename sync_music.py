import os

def main():
    if not os.path.exists("cookies.txt"):
        print("Error: cookies.txt was not generated from secret.")
        return

    # Parse cookies.txt to extract key-value pairs
    try:
        cookies = {}
        with open("cookies.txt", "r") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]
        
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        
        # Construct the exact headers required so ytmusicapi accepts it as browser auth
        # Including a dummy/placeholder or standard browser authorization structure if needed, 
        # or utilizing the raw format strings.
        import json
        browser_data = [
            {
                "name": "cookie",
                "value": cookie_string
            }
        ]
        
        # Alternatively, write a standard dictionary format that ytmusicapi parses for browser auth:
        browser_config = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "X-Goog-AuthUser": "0",
            "Cookie": cookie_string,
            "authorization": "SAPISIDHASH " # satisfies ytmusicapi browser check if required, or we can use the direct dictionary format
        }
        
        # Let's write out a valid JSON file structure that matches browser auth expectations:
        with open("browser.json", "w") as outfile:
            json.dump({
                "cookie": cookie_string,
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }, outfile, indent=2)
            
        print("Successfully generated browser.json configuration!")
    except Exception as e:
        print(f"Error building browser.json: {e}")
        return

    from ytmusicapi import YTMusic
    yt = YTMusic("browser.json")
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
