import os
import json
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

def parse_cookies_flexibly(cookies_raw):
    """Handles both Netscape format and JSON format cookies robustly."""
    cookies = []
    cookies_raw = cookies_raw.strip()
    
    # Try parsing as JSON first (in case the secret is stored as a JSON array)
    if cookies_raw.startswith("[") or cookies_raw.startswith("{"):
        try:
            data = json.loads(cookies_raw)
            if isinstance(data, list):
                for item in data:
                    if "name" in item and "value" in item and "domain" in item:
                        cookies.append({
                            "name": item["name"],
                            "value": item["value"],
                            "domain": item["domain"] if item["domain"].startswith(".") else f".{item['domain']}",
                            "path": item.get("path", "/"),
                            "secure": bool(item.get("secure", True))
                        })
                print(f"Successfully parsed {len(cookies)} cookies from JSON format.")
                return cookies
        except Exception as e:
            print(f"JSON cookie parse attempt failed: {e}")

    # Fallback to Netscape format parsing
    for line in cookies_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue

        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]

        parts = line.split("\t")
        if len(parts) >= 7:
            domain = parts[0].strip()
            path = parts[1].strip() or "/"
            secure_flag = parts[3].strip().upper() == "TRUE"
            name = parts[5].strip()
            value = parts[6].strip()

            if "youtube.com" not in domain and "google.com" not in domain:
                continue

            if not name or not value:
                continue

            formatted_domain = domain if domain.startswith(".") else f".{domain}"

            cookie_dict = {
                "name": name,
                "value": value,
                "domain": formatted_domain,
                "path": path,
                "secure": secure_flag
            }
            
            try:
                expires = float(parts[4].strip())
                if expires > 0:
                    cookie_dict["expires"] = expires
            except (ValueError, IndexError):
                pass

            cookies.append(cookie_dict)
            
    return cookies

def main():
    playlist_id = os.environ.get("PLAYLIST_ID")
    cookies_raw = os.environ.get("YT_COOKIES")

    if not playlist_id or not cookies_raw:
        print("Error: Missing PLAYLIST_ID or YT_COOKIES environment variables.")
        return

    added_tracks = load_added_tracks()
    cookies = parse_cookies_flexibly(cookies_raw)
    print(f"Total valid cookies ready for injection: {len(cookies)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        added_cookie_count = 0
        for c in cookies:
            try:
                context.add_cookies([c])
                added_cookie_count += 1
            except Exception as ex:
                print(f"Failed cookie ({c.get('name')}): {ex}")
                continue
        print(f"Successfully injected {added_cookie_count} cookies into browser context.")

        page = context.new_page()

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

        video_ids = []
        for link in video_links:
            if "watch?v=" in link:
                v_id = link.split("watch?v=")[1].split("&")[0]
                if v_id not in video_ids:
                    video_ids.append(v_id)

        print(f"Total unique video entries collected from releases: {len(video_ids)}")

        pending = [v for v in video_ids if v not in added_tracks]
        print(f"Pending tracks remaining to inspect: {len(pending)}")

        if not pending:
            print("All tracks are already up to date!")
            browser.close()
            return

        batch = pending[:BATCH_LIMIT]
        added_count = 0

        for i, v_id in enumerate(batch):
            try:
                video_url = f"https://www.youtube.com/watch?v={v_id}"
                print(f"[{i + 1}/{len(batch)}] Inspecting track: {v_id}")
                page.goto(video_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                signin_btn = page.locator("a[href*='accounts.google.com/ServiceLogin']").first
                if signin_btn.is_visible():
                    print("Error: Session expired or guest view active. Re-export your cookies.txt file.")
                    break

                page.wait_for_selector("ytd-watch-metadata", timeout=5000)
                description = page.inner_text("ytd-watch-metadata")
                
                # Strict Art Track Check
                if "Provided to YouTube by" not in description and "Auto-generated by YouTube" not in description:
                    print(f"Skipping {v_id}: Not identified as an official Art Track (likely a music video).")
                    continue

                save_btn = page.locator("button[aria-label*='Save to playlist']").first
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
                    print(f"Successfully added official Art Track {v_id} to playlist {playlist_id}.")
                    added_tracks.add(v_id)
                    added_count += 1
                    page.wait_for_timeout(1000)
                else:
                    print(f"Could not locate playlist ID '{playlist_id}' in the Save menu options.")

            except Exception as e:
                print(f"Error processing track {v_id}: {e}")
                continue

        save_added_tracks(added_tracks)
        print(f"Batch completed. Successfully verified and added {added_count} official Art Tracks to your playlist!")
        browser.close()

if __name__ == "__main__":
    main()
