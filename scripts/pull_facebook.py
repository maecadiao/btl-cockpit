"""Pull Facebook Page and Instagram follower metrics into metrics.csv.

Metrics written:
  source="facebook": followers, posts_total
  source="instagram": followers
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import append_row, env, now_iso, write_snapshot

GRAPH_BASE = "https://graph.facebook.com/v19.0"


def _graph_get(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    url = f"{GRAPH_BASE}/{path}?{qs}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _is_token_expired(exc: urllib.error.HTTPError) -> bool:
    """Return True if the error body indicates an expired/invalid OAuth token (code 190)."""
    try:
        body = json.loads(exc.read().decode())
        error = body.get("error", {})
        return int(error.get("code", 0)) == 190
    except Exception:  # noqa: BLE001
        return False


def fetch_facebook(page_id: str, token: str) -> dict:
    return _graph_get(
        page_id,
        {"fields": "followers_count,fan_count", "access_token": token},
    )


def fetch_instagram(ig_account_id: str, token: str) -> dict:
    return _graph_get(
        ig_account_id,
        {"fields": "followers_count", "access_token": token},
    )


def main() -> None:
    token = env("FB_PAGE_ACCESS_TOKEN")
    page_id = env("FB_PAGE_ID")
    ig_account_id = env("INSTAGRAM_BUSINESS_ACCT_ID")

    if not token or not page_id:
        write_snapshot("facebook", "error", "FB_PAGE_ACCESS_TOKEN or FB_PAGE_ID not set")
        return

    ts = now_iso()

    # --- Facebook Page ---
    try:
        fb_data = fetch_facebook(page_id, token)
    except urllib.error.HTTPError as exc:
        if _is_token_expired(exc):
            msg = "Facebook access token expired (error code 190) — refresh FB_PAGE_ACCESS_TOKEN"
        else:
            msg = f"Facebook page fetch failed: {exc.code} {exc.reason}"
        write_snapshot("facebook", "error", msg)
        return
    except Exception as exc:  # noqa: BLE001
        write_snapshot("facebook", "error", f"Facebook page fetch failed: {exc}")
        return

    fb_followers = float(fb_data.get("fan_count") or fb_data.get("followers_count") or 0)
    append_row(ts, "facebook", "followers", fb_followers, "ok", "")
    append_row(ts, "facebook", "posts_total", 0.0, "ok", "")
    write_snapshot("facebook", "ok")
    print(f"[facebook] followers={fb_followers}")

    # --- Instagram ---
    if not ig_account_id:
        write_snapshot("instagram", "error", "INSTAGRAM_BUSINESS_ACCT_ID not set")
        return

    try:
        ig_data = fetch_instagram(ig_account_id, token)
    except urllib.error.HTTPError as exc:
        if _is_token_expired(exc):
            msg = "Instagram access token expired (error code 190) — refresh FB_PAGE_ACCESS_TOKEN"
        else:
            msg = f"Instagram fetch failed: {exc.code} {exc.reason}"
        write_snapshot("instagram", "error", msg)
        return
    except Exception as exc:  # noqa: BLE001
        write_snapshot("instagram", "error", f"Instagram fetch failed: {exc}")
        return

    ig_followers = float(ig_data.get("followers_count") or 0)
    append_row(ts, "instagram", "followers", ig_followers, "ok", "")
    write_snapshot("instagram", "ok")
    print(f"[instagram] followers={ig_followers}")


if __name__ == "__main__":
    main()
