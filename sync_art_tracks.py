import os
import json
import tempfile
from ytmusicapi import YTMusic
from playwright.sync_api import sync_playwright

STATE_FILE = "added_tracks.json"
CHANNEL_RELEASES_URL = "https://www.youtube.com/channel/UCtFOW7jJXChfFNoucRFqRmw/releases"
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
    """Converts raw Netscape cookies into a Cookie header string for ytmusicapi."""
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

def extract_cookie_pairs(cookies_raw):
    """Extracts name=value pairs for Playwright DOM injection."""
    pairs = []
    cookies_raw = cookies_raw.strip()
    
    if cookies_raw.startswith("[") or cookies_raw.startswith("{"):
        try:
            data = json.loads(cookies_raw)
            if isinstance(data, list):
                for item in data:
                    if "name" in item and "value" in item:
                        pairs.append(f"{item['name']}={item['value']}")
                return pairs
        except Exception:
            pass

    for line in cookies_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]

        parts = line.split("\t")
        if len(parts) >= 7:
            name = parts[5].strip()
            value = parts[6].strip()
            if name and value:
                pairs.append(f"{name}={value}")
    return pairs

def main():
    playlist_id = os.environ.get("PLAYLIST_ID")
    cookies_raw = os.environ.get("YT_COOKIES")

    if not playlist_id or not cookies_raw:
        print("Error: Missing PLAYLIST_ID or YT_COOKIES environment variables.")
        return

    # 1. Initialize ytmusicapi for seamless playlist additions later
    cookie_header = netscape_to_cookie_header(cookies_raw)
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
    except Exception:
        ytmusic = YTMusic()
        ytmusic.auth = temp_auth_path
        if hasattr(ytmusic, "_session"):
            ytmusic._session.headers.update(browser_headers)
        elif hasattr(ytmusic, "session"):
            ytmusic.session.headers.update(browser_headers)
    finally:
        if os.path.exists(temp_auth_path):
            os.remove(temp_auth_path)

    added_tracks = load_added_tracks()
    cookie_pairs = extract_cookie_pairs(cookies_raw)

    # 2. Use Playwright to scrape releases and verify Art Tracks via descriptions
    verified_video_ids = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        page.goto("https://www.youtube.com", wait_until="domcontentloaded")
        for pair in cookie_pairs:
            try:
                page.evaluate(f"document.cookie = '{pair}; domain=.youtube.com; path=/; secure; samesite=none'")
            except Exception:
                continue

        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        print(f"Navigating to Arijit Singh's Official Releases: {CHANNEL_RELEASES_URL}")
        page.goto(CHANNEL_RELEASES_URL, wait_until="domcontentloaded")
        
        try:
            page.wait_for_selector("a#video-title, a.yt-simple-endpoint", timeout=10000)
            print("Scrolling to load release items...")
            for _ in range(25):
                page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                page.wait_for_timeout(2000)
        except Exception as e:
            print(f"Notice during scrolling: {e}")

        video_links = page.eval_on_selector_all(
            "a[href*='/watch?v=']",
            "elements => elements.map(e => e.href)"
        )

        all_video_ids = []
        for link in video_links:
            if "watch?v=" in link:
                v_id = link.split("watch?v=")[1].split("&")[0]
                if v_id not in all_video_ids:
                    all_video_ids.append(v_id)

        print(f"Total unique video entries collected from releases: {len(all_video_ids)}")

        pending = [v for v in all_video_ids if v not in added_tracks]
        print(f"Pending tracks remaining to inspect: {len(pending)}")

        if not pending:
            print("All tracks are already up to date!")
            browser.close()
            return

        batch = pending[:BATCH_LIMIT]

        for i, v_id in enumerate(batch):
            try:
                video_url = f"https://www.youtube.com/watch?v={v_id}"
                print(f"[{i + 1}/{len(batch)}] Inspecting track: {v_id}")
                page.goto(video_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                signin_btn = page.locator("a[href*='accounts.google.com/ServiceLogin']").first
                if signin_btn.is_visible():
                    print("Session expired or guest view active on track check, continuing...")
                    continue

                page.wait_for_selector("ytd-watch-metadata", timeout=4000)
                description = page.inner_text("ytd-watch-metadata")
                
                # Strict Art Track Check
                if "Provided to YouTube by" not in description and "Auto-generated by YouTube" not in description:
                    print(f"Skipping {v_id}: Not identified as an official Art Track (likely a music video).")
                    continue

                print(f"Verified official Art Track: {v_id}")
                verified_video_ids.append(v_id)

            except Exception as e:
                print(f"Error inspecting track {v_id}: {e}")
                continue

        browser.close()

    if not verified_video_ids:
        print("No new verified Art Tracks found to add.")
        return

    # 3. Add verified Art Tracks to the playlist using ytmusicapi
    print(f"Adding {len(verified_video_ids)} verified Art Tracks to playlist {playlist_id} via API...")
    try:
        response = ytmusic.add_playlist_items(playlist_id, verified_video_ids, duplicates=False)
        status = response.get("status", "Unknown") if isinstance(response, dict) else "STATUS_SUCCEEDED"
        print("API Batch Response status:", status)

        for v_id in verified_video_ids:
            added_tracks.add(v_id)
        save_added_tracks(added_tracks)
        print(f"Successfully added {len(verified_video_ids)} verified Art Tracks to your playlist!")

    except Exception as e:
        print(f"Batch API add failed ({e}). Adding individually...")
        added_count = 0
        for v_id in verified_video_ids:
            try:
                res = ytmusic.add_playlist_items(playlist_id, [v_id], duplicates=False)
                item_status = res.get("status", "Unknown") if isinstance(res, dict) else "STATUS_SUCCEEDED"
                if item_status != "STATUS_FAILED":
                    added_tracks.add(v_id)
                    added_count += 1
            except Exception as item_e:
                print(f"Failed to add track {v_id}: {item_e}")
        
        save_added_tracks(added_tracks)
        print(f"Individual fallback complete: Successfully added {added_count} tracks!")

if __name__ == "__main__":
    main()
