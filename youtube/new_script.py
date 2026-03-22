import os
import requests
import pandas as pd
from datetime import datetime, timedelta
import math
import time
import re
from dotenv import load_dotenv

load_dotenv()

# =============================
# CONFIG
# =============================

API_KEY = os.getenv("YOUTUBE_API_KEY_V3")
BASE_URL = "https://www.googleapis.com/youtube/v3"

REGION = "US"
RELEVANCE_LANGUAGE = "en"

MAX_SEARCH_PAGES = 60
LOW_YIELD_PAGES_TO_STOP = 3
MIN_NEW_CHANNELS_PER_PAGE = 5

SEARCH_ORDERS = ["date", "viewCount", "relevance"]

EXCLUDE_COUNTRIES = ["IN"]

TARGET_CHANNEL_POOL = 2000

# =============================
# INPUT
# =============================

print("\n🎯 YouTube Lead Finder (Optimized)\n")

KEYWORD = input("Keyword to search: ").strip()
MIN_SUBS = int(input("Minimum subscribers: ").strip())
MAX_SUBS = int(input("Maximum subscribers: ").strip())

MIN_UPLOADS_30D = int(input("Minimum uploads in last 30 days: ").strip())

min_avg_views_input = input("Minimum average views (optional): ").strip()
MIN_AVG_VIEWS = int(min_avg_views_input) if min_avg_views_input else 0

# =============================
# EMAIL EXTRACTION
# =============================

def extract_emails(text):
    if not text:
        return []

    emails = re.findall(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}",
        text
    )

    return list(set(emails))


# =============================
# SEARCH COLLECTION
# =============================

def collect_channel_ids(keyword):

    all_channel_ids = set()
    low_yield_pages = 0

    for order in SEARCH_ORDERS:

        print(f"\n🔎 Using order: {order}")

        next_page_token = None

        for page in range(MAX_SEARCH_PAGES // len(SEARCH_ORDERS)):

            params = {
                "part": "snippet",
                "q": keyword,
                "type": "video",
                "order": order,
                "maxResults": 50,
                "relevanceLanguage": RELEVANCE_LANGUAGE,
                "regionCode": REGION,
                "key": API_KEY
            }

            if next_page_token:
                params["pageToken"] = next_page_token

            res = requests.get(f"{BASE_URL}/search", params=params).json()

            channel_ids = list({item["snippet"]["channelId"] for item in res.get("items", [])})

            prev_count = len(all_channel_ids)
            all_channel_ids.update(channel_ids)
            new_added = len(all_channel_ids) - prev_count

            print(f"Page {page+1} → +{new_added} new channels")

            # Low yield detection
            if new_added < MIN_NEW_CHANNELS_PER_PAGE:
                low_yield_pages += 1
            else:
                low_yield_pages = 0

            if low_yield_pages >= LOW_YIELD_PAGES_TO_STOP:
                print("⏹ Stopping: low discovery yield")
                break

            if len(all_channel_ids) >= TARGET_CHANNEL_POOL:
                print("🎯 Target channel pool reached")
                break

            next_page_token = res.get("nextPageToken")
            if not next_page_token:
                break

            time.sleep(0.2)

        if len(all_channel_ids) >= TARGET_CHANNEL_POOL:
            break

    print(f"\nCollected {len(all_channel_ids)} unique channels\n")
    return list(all_channel_ids)


# =============================
# API HELPERS
# =============================

def get_channel_details_batch(channel_ids):

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
        "maxResults": 15,  # reduced
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
# EVALUATION
# =============================

def evaluate_channel(channel):

    try:
        subs = int(channel["statistics"].get("subscriberCount", 0))

        if subs < MIN_SUBS or subs > MAX_SUBS:
            return None

        country = channel["snippet"].get("country", "")
        if country in EXCLUDE_COUNTRIES:
            return None

        # Skip inactive channels early
        video_count = int(channel["statistics"].get("videoCount", 0))
        if video_count < 20:
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

        stats = get_video_stats(video_ids[:20])
        views = [int(v["statistics"].get("viewCount", 0)) for v in stats]

        avg_views = sum(views) / len(views) if views else 0

        if avg_views < MIN_AVG_VIEWS:
            return None

        # Email extraction
        description = channel["snippet"].get("description", "")
        emails = extract_emails(description)

        if emails:
            email_value = ",".join(emails)
        elif "business" in description.lower() or "contact" in description.lower():
            email_value = "CAPTCHA"
        else:
            email_value = ""

        score = (
            recent_count * 3 +
            math.log10(subs + 1) * 2 +
            (avg_views / 10000)
        )

        return {
            "Channel Name": channel["snippet"]["title"],
            "Channel URL": f"https://youtube.com/channel/{channel['id']}",
            "Subscribers": subs,
            "Uploads Last 30d": recent_count,
            "Avg Views (Last 10)": int(avg_views),
            "Last Upload": last_upload_date.strftime("%Y-%m-%d") if last_upload_date else "",
            "Score": round(score, 2),
            "Email": email_value
        }

    except Exception as e:
        print("⚠ Error:", e)
        return None


# =============================
# MAIN
# =============================

def run():

    channel_ids = collect_channel_ids(KEYWORD)

    print("📦 Fetching channel details...\n")
    channels_data = get_channel_details_batch(channel_ids)

    leads = []

    for idx, channel in enumerate(channels_data):

        lead = evaluate_channel(channel)

        if lead:
            leads.append(lead)
            print(f"✔ {lead['Channel Name']}")

        if idx % 50 == 0:
            print(f"Progress: {idx}/{len(channels_data)}")

    df = pd.DataFrame(leads)

    if df.empty:
        print("❌ No leads found")
        return

    df = df.sort_values(by="Score", ascending=False)

    filename = f"yt_leads_{KEYWORD.replace(' ', '_')}.csv"
    df.to_csv(filename, index=False)

    print(f"\n✅ Done! {len(df)} leads saved to {filename}")


if __name__ == "__main__":
    run()