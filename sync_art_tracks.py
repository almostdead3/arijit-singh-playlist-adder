import os
import json
import random
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

def extract_cookie_pairs(cookies_raw):
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

    added_tracks = load_added_tracks()
    cookie_pairs = extract_cookie_pairs(cookies_raw)
    added_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US"
        )
        
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
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
            print("Scrolling to load all release items and albums...")
            for _ in range(25):
                page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                page.wait_for_timeout(2000)
        except Exception as e:
            print(f"Notice during scrolling: {e}")

        all_links = page.eval_on_selector_all(
            "a[href*='/watch?v='], a[href*='playlist?list=']",
            "elements => elements.map(e => e.href)"
        )

        expanded_video_ids = []
        
        for link in all_links:
            if "playlist?list=" in link or "list=" in link:
                print(f"Found album/playlist container, expanding tracks...")
                try:
                    page.goto(link, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                    
                    for _ in range(5):
                        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                        page.wait_for_timeout(1000)
                        
                    playlist_links = page.eval_on_selector_all(
                        "a[href*='/watch?v=']",
                        "elements => elements.map(e => e.href)"
                    )
                    for plink in playlist_links:
                        if "watch?v=" in plink:
                            v_id = plink.split("watch?v=")[1].split("&")[0]
                            if v_id not in expanded_video_ids:
                                expanded_video_ids.append(v_id)
                except Exception as e:
                    print(f"Could not expand playlist container: {e}")
            elif "watch?v=" in link:
                v_id = link.split("watch?v=")[1].split("&")[0]
                if v_id not in expanded_video_ids:
                    expanded_video_ids.append(v_id)

        print(f"Total individual track IDs collected (including albums/playlists): {len(expanded_video_ids)}")

        pending = [v for v in expanded_video_ids if v not in added_tracks]
        print(f"Pending tracks remaining to inspect: {len(pending)}")

        if not pending:
            print("All tracks are already up to date!")
            browser.close()
            return

        batch = pending[:BATCH_LIMIT]

        for i, v_id in enumerate(batch):
            try:
                video_url = f"https://www.youtube.com/watch?v={v_id}"
                print(f"[{i + 1}/{len(batch)}] Inspecting and adding track: {v_id}")
                page.goto(video_url, wait_until="domcontentloaded")
                page.wait_for_timeout(random.randint(2500, 4500))

                consent_btn = page.locator("button:has-text('Accept all'), yt-button-renderer:has-text('Accept all')").first
                if consent_btn.is_visible():
                    consent_btn.click()
                    page.wait_for_timeout(1500)

                page.wait_for_selector("ytd-watch-metadata", timeout=6000)
                description = page.inner_text("ytd-watch-metadata")
                
                if "Provided to YouTube by" not in description and "Auto-generated by YouTube" not in description:
                    print(f"Skipping {v_id}: Not identified as an official Art Track.")
                    continue

                save_btn = page.locator("button[aria-label*='Save to playlist'], button[aria-label*='Save']").first
                if not save_btn.is_visible():
                    more_btn = page.locator("button[aria-label='More actions']").first
                    if more_btn.is_visible():
                        more_btn.click()
                        page.wait_for_timeout(1000)

                save_btn.click()
                page.wait_for_timeout(1500)

                playlist_option = page.locator(f"tp-yt-paper-checkbox:has-text('{playlist_id}'), ytd-playlist-add-to-option-renderer:has-text('{playlist_id}')").first
                
                if playlist_option.is_visible():
                    playlist_option.click()
                    print(f"Successfully added official Art Track {v_id} to playlist.")
                    added_tracks.add(v_id)
                    added_count += 1
                    page.wait_for_timeout(1000)
                else:
                    print(f"Could not locate playlist identifier in the menu popup.")

            except Exception as e:
                print(f"Error processing track {v_id}: {e}")
                continue

        save_added_tracks(added_tracks)
        print(f"Batch completed. Successfully verified and added {added_count} official Art Tracks to your playlist!")
        browser.close()

if __name__ == "__main__":
    main()
