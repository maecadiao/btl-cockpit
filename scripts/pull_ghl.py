"""pull_ghl.py — GoHighLevel CRM metrics (v1 Location API).

Emits:
  ghl:active_leads    — contacts added in last 90 days (active pipeline proxy)
  ghl:new_leads_7d    — contacts added in last 7 days
  ghl:stale_leads     — contacts added 14-90 days ago with no recent activity
  ghl:total_contacts  — total contact count in your CRM
  ghl:pipeline_value  — requires GHL v2 OAuth (0 until upgraded)
  ghl:inbox_unread    — requires GHL v2 OAuth (0 until upgraded)

Credentials in ~/.claude/.env:
  GHL_API_KEY     — Location API Key from Settings → Integrations → API Key
  GHL_LOCATION_ID — Settings → Business Profile → Location ID
"""

from __future__ import annotations
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import env, now_iso, append_row, write_snapshot

SOURCE  = "ghl"
BASE_V2 = "https://services.leadconnectorhq.com"
HEADERS = {
    "Authorization": "",  # filled in main()
    "Version":       "2021-04-15",
    "Accept":        "application/json",
    "User-Agent":    "Mozilla/5.0 (compatible; BTL-Metrics/1.0)",
}


def ghl_get(path: str, params: dict | None = None) -> dict:
    url = BASE_V2 + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_all_contacts(location_id: str, limit: int = 100) -> list[dict]:
    """Page through contacts until we have them all (up to 1000)."""
    contacts: list[dict] = []
    params: dict = {"locationId": location_id, "limit": limit}
    while True:
        r = ghl_get("/contacts/", params)
        batch = r.get("contacts", [])
        contacts.extend(batch)
        meta = r.get("meta", {})
        next_cursor = meta.get("nextPageUrl") or meta.get("startAfter")
        if not next_cursor or len(batch) < limit or len(contacts) >= 1000:
            break
        last_id = batch[-1]["id"] if batch else None
        if not last_id:
            break
        params = {"locationId": location_id, "limit": limit, "startAfterId": last_id}
    return contacts


def main():
    api_key     = env("GHL_API_KEY")
    location_id = env("GHL_LOCATION_ID")

    if not api_key or not location_id:
        write_snapshot(SOURCE, "error",
            "missing GHL_API_KEY or GHL_LOCATION_ID in ~/.claude/.env")
        return

    HEADERS["Authorization"] = f"Bearer {api_key}"
    ts     = now_iso()
    now_dt = datetime.now(timezone.utc)

    def parse_dt(s: str | None) -> datetime | None:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    try:
        # Get total contact count quickly from meta
        r = ghl_get("/contacts/", {"locationId": location_id, "limit": 1})
        total_contacts = float(r.get("meta", {}).get("total", 0))
        append_row(ts, SOURCE, "total_contacts", total_contacts, "ok", "")

        # Fetch recent contacts (last 90 days) for pipeline metrics
        contacts = fetch_all_contacts(location_id, limit=100)

        cutoff_7d  = now_dt - timedelta(days=7)
        cutoff_14d = now_dt - timedelta(days=14)
        cutoff_90d = now_dt - timedelta(days=90)

        active_leads  = 0
        stale_leads   = 0

        # Deduplicate new leads by phone number (GHL sometimes creates duplicate
        # contacts from repeat form submissions / SMS flows)
        seen_new_lead_phones: set[str] = set()
        new_leads_7d = 0

        for c in contacts:
            added    = parse_dt(c.get("dateAdded"))
            activity = parse_dt(c.get("lastActivity") or c.get("dateUpdated"))

            # Check for "New Lead" status via GHL tags (case-insensitive)
            tags_lower = [t.lower().strip() for t in (c.get("tags") or [])]
            is_new_lead = "new lead" in tags_lower

            if added and added >= cutoff_90d:
                active_leads += 1
                # Only count as new_leads_7d if: added this week AND has "New Lead" tag
                # Deduplicate by phone to avoid counting the same person N times
                if is_new_lead and added >= cutoff_7d:
                    phone = (c.get("phone") or "").strip()
                    dedup_key = phone if phone else c.get("id", "")
                    if dedup_key not in seen_new_lead_phones:
                        seen_new_lead_phones.add(dedup_key)
                        new_leads_7d += 1
                # Stale = added 14-90 days ago, no recent activity
                elif added < cutoff_14d:
                    if not activity or activity < cutoff_14d:
                        stale_leads += 1

        append_row(ts, SOURCE, "active_leads",  float(active_leads),  "ok", "")
        append_row(ts, SOURCE, "new_leads_7d",  float(new_leads_7d),  "ok", "")
        append_row(ts, SOURCE, "stale_leads",   float(stale_leads),   "ok", "")

        # Pipeline value from opportunities
        try:
            opp_r = ghl_get("/opportunities/search/", {"location_id": location_id, "limit": 100})
            opps  = opp_r.get("opportunities", [])
            pipeline_value = sum(float(o.get("monetaryValue") or 0) for o in opps)
            append_row(ts, SOURCE, "pipeline_value", pipeline_value, "ok", "")
            append_row(ts, SOURCE, "open_opportunities", float(len(opps)), "ok", "")
        except Exception as e:
            append_row(ts, SOURCE, "pipeline_value", 0.0, "error", str(e)[:100])

        # Unread conversations
        try:
            conv_r = ghl_get("/conversations/search/", {"locationId": location_id, "limit": 25, "unreadOnly": "true"})
            inbox_unread = float(len(conv_r.get("conversations", [])))
            append_row(ts, SOURCE, "inbox_unread", inbox_unread, "ok", "")
        except Exception as e:
            append_row(ts, SOURCE, "inbox_unread", 0.0, "error", str(e)[:100])

        write_snapshot(SOURCE, "ok")
        print(f"GHL ok — {total_contacts:.0f} total contacts, "
              f"{active_leads} active (90d), {new_leads_7d} new (7d), "
              f"{stale_leads} stale")

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        write_snapshot(SOURCE, "error", f"HTTP {e.code}: {body}")
        print(f"GHL error: HTTP {e.code}: {body}")
    except Exception as e:
        write_snapshot(SOURCE, "error", str(e)[:200])
        print(f"GHL error: {e}")


if __name__ == "__main__":
    main()
