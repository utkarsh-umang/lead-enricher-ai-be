import os
import requests
import pandas as pd
from datetime import datetime, timedelta
import math
import time
from dotenv import load_dotenv

load_dotenv()

# =============================
# CONFIG
# =============================

API_KEY = os.getenv("YOUTUBE_API_KEY_V3")
BASE_URL = "https://www.googleapis.com/youtube/v3"

REGION = "US"  # Single region (efficient)
RELEVANCE_LANGUAGE = "en"

MAX_SEARCH_PAGES = 50      # Safety cap - stop after this many pages
PAGES_WITHOUT_LEADS_TO_STOP = 5  # Stop when this many consecutive pages yield 0 leads

EXCLUDE_COUNTRIES = ["IN"]  # ISO 3166-1 alpha-2 codes to exclude (e.g. IN = India)

# =============================
# INPUT SECTION
# =============================

print("\n🎯 YouTube Lead Finder (Efficient + High Quality)\n")

KEYWORD = input("Keyword to search: ").strip()
MIN_SUBS = int(input("Minimum subscribers: ").strip())
MAX_SUBS = int(input("Maximum subscribers: ").strip())

MIN_UPLOADS_30D = int(input("Minimum uploads in last 30 days: ").strip())

min_avg_views_input = input("Minimum average views (optional, press Enter to skip): ").strip()
MIN_AVG_VIEWS = int(min_avg_views_input) if min_avg_views_input else 0


# =============================
# SEARCH CHANNELS (PAGINATED)
# =============================

def search_channels_paginated(keyword):
    """
    Generator that yields one search page at a time.
    Yields: (page_num, channel_ids, has_more_pages)
    """
    next_page_token = None
    for page in range(MAX_SEARCH_PAGES):
        params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "order": "date",
            "maxResults": 50,
            "relevanceLanguage": RELEVANCE_LANGUAGE,
            "regionCode": REGION,
            "key": API_KEY
        }
        if next_page_token:
            params["pageToken"] = next_page_token

        res = requests.get(f"{BASE_URL}/search", params=params).json()
        channel_ids = list({item["snippet"]["channelId"] for item in res.get("items", [])})
        next_page_token = res.get("nextPageToken")

        yield page + 1, channel_ids, next_page_token is not None

        if not next_page_token:
            break
        time.sleep(0.2)


# =============================
# API HELPERS
# =============================

def get_channel_details_batch(channel_ids):
    """
    Batch fetch channel details (max 50 per call).
    Much more efficient than one-by-one.
    """
    channels_data = []

    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]

        params = {
            "part": "statistics,contentDetails,snippet",
            "id": ",".join(batch),
            "key": API_KEY
        }

        res = requests.get(f"{BASE_URL}/channels", params=params).json()
        channels_data.extend(res.get("items", []))

        time.sleep(0.2)

    return channels_data


def get_recent_videos(playlist_id):
    params = {
        "part": "snippet",
        "playlistId": playlist_id,
        "maxResults": 50,
        "key": API_KEY
    }

    res = requests.get(f"{BASE_URL}/playlistItems", params=params).json()
    return res.get("items", [])


def get_video_stats(video_ids):
    if not video_ids:
        return []

    params = {
        "part": "statistics",
        "id": ",".join(video_ids),
        "key": API_KEY
    }

    res = requests.get(f"{BASE_URL}/videos", params=params).json()
    return res.get("items", [])


# =============================
# MAIN LOGIC
# =============================

def evaluate_channel(channel):
    """
    Evaluate a single channel against filters. Returns lead dict if qualified, None otherwise.
    """
    try:
        subs = int(channel["statistics"].get("subscriberCount", 0))
        if subs < MIN_SUBS or subs > MAX_SUBS:
            return None

        channel_country = channel["snippet"].get("country", "")
        if channel_country in EXCLUDE_COUNTRIES:
            return None

        uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
        videos = get_recent_videos(uploads_playlist)

        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_count = 0
        video_ids = []
        last_upload_date = None

        for vid in videos:
            published = datetime.strptime(
                vid["snippet"]["publishedAt"],
                "%Y-%m-%dT%H:%M:%SZ"
            )
            if not last_upload_date:
                last_upload_date = published
            if published > cutoff:
                recent_count += 1
            video_ids.append(vid["snippet"]["resourceId"]["videoId"])

        if recent_count < MIN_UPLOADS_30D:
            return None

        stats = get_video_stats(video_ids[:10])
        views = [int(v["statistics"].get("viewCount", 0)) for v in stats]
        avg_views = sum(views) / len(views) if views else 0
        if avg_views < MIN_AVG_VIEWS:
            return None

        score = (
            recent_count * 3 +
            math.log10(subs) * 2 +
            (avg_views / 10000)
        )
        return {
            "Channel Name": channel["snippet"]["title"],
            "Channel URL": f"https://youtube.com/channel/{channel['id']}",
            "Subscribers": subs,
            "Uploads Last 30d": recent_count,
            "Avg Views (Last 10)": int(avg_views),
            "Last Upload": last_upload_date.strftime("%Y-%m-%d") if last_upload_date else "",
            "Score": round(score, 2)
        }
    except Exception as e:
        print("⚠ Error:", e)
        return None


def run():
    evaluated_channels = set()
    leads = []
    consecutive_pages_without_leads = 0

    for page_num, channel_ids, has_more in search_channels_paginated(KEYWORD):
        print(f"🔍 Fetching search page {page_num}")

        new_channel_ids = [c for c in channel_ids if c not in evaluated_channels]
        if not new_channel_ids:
            if not has_more:
                break
            continue

        evaluated_channels.update(new_channel_ids)
        channels_data = get_channel_details_batch(new_channel_ids)
        leads_from_page = []

        for channel in channels_data:
            lead = evaluate_channel(channel)
            if lead:
                leads_from_page.append(lead)
                print(f"✔ Qualified: {channel['snippet']['title']}")

        leads.extend(leads_from_page)

        if leads_from_page:
            consecutive_pages_without_leads = 0
        else:
            consecutive_pages_without_leads += 1
            print(f"   Page {page_num}: No new leads from {len(new_channel_ids)} channels")

        if consecutive_pages_without_leads >= PAGES_WITHOUT_LEADS_TO_STOP:
            print(f"\n⏹ Stopping early: {PAGES_WITHOUT_LEADS_TO_STOP} consecutive pages without leads")
            break

        if not has_more:
            print("\n📄 No more search results")
            break

    print(f"\n🔎 Evaluated {len(evaluated_channels)} unique channels across {page_num} pages\n")

    df = pd.DataFrame(leads)
    if df.empty:
        print("❌ No leads matched your filters.")
        return

    df = df.sort_values(by="Score", ascending=False)
    filename = f"yt_leads_{KEYWORD.replace(' ', '_')}.csv"
    df.to_csv(filename, index=False)
    print(f"✅ Done! {len(df)} leads saved to {filename}")


if __name__ == "__main__":
    run()

