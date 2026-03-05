"""
Monitor @algoverse_org on Instagram for new posts and share them to Discord.

Uses instaloader to fetch recent posts and a Discord webhook to send notifications.
State is tracked in a JSON file to avoid duplicate posts.
"""

import json
import os
import sys
import time
from pathlib import Path

import instaloader
import requests

INSTAGRAM_USER = "algoverse_org"
STATE_FILE = Path(__file__).parent / "last_seen_post.json"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
# How many recent posts to check each run
MAX_POSTS_TO_CHECK = 10


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_seen_shortcode": None, "seen_shortcodes": []}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fetch_recent_posts(username: str, count: int) -> list[dict]:
    """Fetch the most recent posts from a public Instagram profile."""
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )

    # Login if credentials are available (helps avoid rate limits)
    ig_user = os.environ.get("INSTAGRAM_USERNAME")
    ig_pass = os.environ.get("INSTAGRAM_PASSWORD")
    if ig_user and ig_pass:
        try:
            loader.login(ig_user, ig_pass)
        except Exception as e:
            print(f"Warning: Instagram login failed ({e}), continuing without auth")

    profile = instaloader.Profile.from_username(loader.context, username)

    posts = []
    for i, post in enumerate(profile.get_posts()):
        if i >= count:
            break
        posts.append(
            {
                "shortcode": post.shortcode,
                "caption": (post.caption or "")[:300],
                "url": f"https://www.instagram.com/p/{post.shortcode}/",
                "timestamp": post.date_utc.isoformat(),
                "typename": post.typename,
            }
        )

    return posts


def post_to_discord(webhook_url: str, ig_post: dict) -> None:
    """Send an Instagram post link to Discord via webhook."""
    caption_preview = ig_post["caption"]
    if len(caption_preview) > 200:
        caption_preview = caption_preview[:200] + "..."

    payload = {
        "content": (
            f"**New post from @{INSTAGRAM_USER}!**\n"
            f"{ig_post['url']}\n\n"
            f"> {caption_preview}" if caption_preview else f"**New post from @{INSTAGRAM_USER}!**\n{ig_post['url']}"
        ),
    }

    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()
    print(f"Posted to Discord: {ig_post['url']}")


def main():
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_URL environment variable is not set.")
        sys.exit(1)

    state = load_state()
    seen = set(state.get("seen_shortcodes", []))

    print(f"Checking recent posts from @{INSTAGRAM_USER}...")
    posts = fetch_recent_posts(INSTAGRAM_USER, MAX_POSTS_TO_CHECK)

    if not posts:
        print("No posts found.")
        return

    # Posts are returned newest-first; reverse so we post oldest-new ones first
    new_posts = [p for p in reversed(posts) if p["shortcode"] not in seen]

    if not new_posts:
        print("No new posts since last check.")
        return

    print(f"Found {len(new_posts)} new post(s).")

    for post in new_posts:
        try:
            post_to_discord(DISCORD_WEBHOOK_URL, post)
            seen.add(post["shortcode"])
            # Small delay to respect Discord rate limits
            time.sleep(1)
        except Exception as e:
            print(f"Error posting {post['url']} to Discord: {e}")

    # Save updated state
    state["seen_shortcodes"] = list(seen)
    state["last_seen_shortcode"] = posts[0]["shortcode"]  # newest post
    save_state(state)
    print("State saved.")


if __name__ == "__main__":
    main()
