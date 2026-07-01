"""pull_instagram.py — Instagram Business account metrics.

Emits:
  instagram:followers    — follower count
  instagram:total_posts  — total media count
  instagram:total_likes  — sum of likes across last 25 posts

Credentials needed in ~/.claude/.env:
  FB_PAGE_ACCESS_TOKEN       — same token used for Facebook (Instagram shares it)
  INSTAGRAM_BUSINESS_ACCT_ID — your Instagram Business Account ID
    How to find it:
    1. In Graph API Explorer, query: GET /{your-fb-page-id}?fields=instagram_business_account
    2. The returned id is your INSTAGRAM_BUSINESS_ACCT_ID
    (Requires your Instagram account to be a Business or Creator account
     connected to your Facebook Page)
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

SOURCE = "instagram"
BASE   = "https://graph.facebook.com/v19.0"


def ig_get(path: str, token: str, params: dict | None = None) -> dict:
    p = {"access_token": token}
    if params:
        p.update(params)
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in p.items())
    req = urllib.request.Request(f"{BASE}{path}?{qs}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    token   = env("FB_PAGE_ACCESS_TOKEN")
    ig_id   = env("INSTAGRAM_BUSINESS_ACCT_ID")

    if not token or not ig_id:
        write_snapshot(SOURCE, "error",
            "missing FB_PAGE_ACCESS_TOKEN or INSTAGRAM_BUSINESS_ACCT_ID in ~/.claude/.env")
        return

    ts = now_iso()
    try:
        # Followers + media count
        r = ig_get(f"/{ig_id}", token, {
            "fields": "followers_count,media_count"
        })
        followers   = float(r.get("followers_count") or 0)
        total_posts = float(r.get("media_count") or 0)
        append_row(ts, SOURCE, "followers",   followers,   "ok", "")
        append_row(ts, SOURCE, "total_posts", total_posts, "ok", "")

        # Likes on recent posts (last 25)
        r2 = ig_get(f"/{ig_id}/media", token, {
            "fields": "like_count",
            "limit":  25,
        })
        total_likes = sum(
            float(m.get("like_count") or 0)
            for m in r2.get("data", [])
        )
        if total_likes == 0 and r2.get("data"):
            total_likes = last_known_value(SOURCE, "total_likes")
        append_row(ts, SOURCE, "total_likes", total_likes, "ok", "")

        write_snapshot(SOURCE, "ok")

    except urllib.error.HTTPError as e:
        write_snapshot(SOURCE, "error", f"HTTP {e.code}: {str(e)[:160]}")
    except Exception as e:
        write_snapshot(SOURCE, "error", str(e)[:200])


if __name__ == "__main__":
    main()
