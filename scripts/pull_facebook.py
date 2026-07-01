"""pull_facebook.py — Facebook Page metrics.

Emits:
  facebook:followers    — page followers
  facebook:total_posts  — total posts published on the page
  facebook:total_likes  — total post likes (last 25 posts)

Credentials needed in ~/.claude/.env:
  FB_PAGE_ACCESS_TOKEN — system user token (never expires)
  FB_PAGE_ID           — your Facebook Page ID

Note: BTL page uses "New Pages Experience" which requires a Page Access Token
for post-level data. This script auto-exchanges the system user token for a
page token before reading posts/likes.
"""

from __future__ import annotations
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import env, now_iso, append_row, write_snapshot, last_known_value

SOURCE = "facebook"
BASE   = "https://graph.facebook.com/v19.0"


def fb_get(path: str, token: str, params: dict | None = None) -> dict:
    p = {"access_token": token}
    if params:
        p.update(params)
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in p.items())
    req = urllib.request.Request(f"{BASE}{path}?{qs}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_page_token(page_id: str, user_token: str) -> str:
    """Exchange a user/system-user token for a Page Access Token.

    Required for New Pages Experience: posts/likes endpoints reject
    user tokens and need a page-scoped token.
    """
    r = fb_get(f"/{page_id}", user_token, {"fields": "access_token"})
    page_token = r.get("access_token")
    if not page_token:
        raise RuntimeError("Could not retrieve page access_token — check manage_pages permission")
    return page_token


def main():
    user_token = env("FB_PAGE_ACCESS_TOKEN")
    page_id    = env("FB_PAGE_ID")

    if not user_token or not page_id:
        write_snapshot(SOURCE, "error",
            "missing FB_PAGE_ACCESS_TOKEN or FB_PAGE_ID in ~/.claude/.env")
        return

    ts = now_iso()
    try:
        # ── Followers (works with user token, public field) ──────────────────
        r = fb_get(f"/{page_id}", user_token, {"fields": "followers_count,fan_count"})
        followers = float(r.get("followers_count") or r.get("fan_count") or 0)
        append_row(ts, SOURCE, "followers", followers, "ok", "")

        # ── Exchange for Page Access Token (needed for New Pages Experience) ─
        page_token = get_page_token(page_id, user_token)

        # ── Total posts (last 100) ───────────────────────────────────────────
        r2 = fb_get(f"/{page_id}/posts", page_token, {"limit": 100, "fields": "id"})
        total_posts = float(len(r2.get("data", [])))
        append_row(ts, SOURCE, "total_posts", total_posts, "ok", "")

        # ── Total likes on last 25 posts ─────────────────────────────────────
        r3 = fb_get(f"/{page_id}/posts", page_token, {
            "fields": "likes.summary(true)",
            "limit":  25,
        })
        total_likes = sum(
            float(post.get("likes", {}).get("summary", {}).get("total_count", 0) or 0)
            for post in r3.get("data", [])
        )
        if total_likes == 0 and r3.get("data"):
            total_likes = last_known_value(SOURCE, "total_likes")
        append_row(ts, SOURCE, "total_likes", total_likes, "ok", "")

        write_snapshot(SOURCE, "ok")

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        write_snapshot(SOURCE, "error", f"HTTP {e.code}: {body}")
    except Exception as e:
        write_snapshot(SOURCE, "error", str(e)[:200])


if __name__ == "__main__":
    main()
