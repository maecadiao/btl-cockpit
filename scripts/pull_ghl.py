"""pull_ghl.py — GoHighLevel CRM metrics (legacy v1 API).

GHL stopped honoring Location API keys on the v2 API (services.leadconnectorhq.com)
around late June 2026 — they now work only against the legacy v1 host. All
fetchers here therefore use rest.gohighlevel.com/v1.

Emits:
  ghl:active_leads       — contacts added in last 90 days
  ghl:new_leads_7d       — "New Lead"-tagged contacts added in last 7 days (deduped by phone)
  ghl:stale_leads        — contacts added 14-90 days ago with no recent activity
  ghl:total_contacts     — total contact count
  ghl:pipeline_value     — sum of open opportunity values across all pipelines
  ghl:open_opportunities — count of open opportunities

Credentials in ~/.claude/.env:
  GHL_API_KEY     — Location API Key from Settings (v1-compatible JWT)
  GHL_LOCATION_ID — kept for reference; v1 keys are already location-scoped
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
BASE_V1 = "https://rest.gohighlevel.com/v1"
HEADERS = {
    "Authorization": "",  # filled in main()
    "Accept":        "application/json",
    "User-Agent":    "Mozilla/5.0 (compatible; BTL-Metrics/1.0)",
}


def ghl_get(path_or_url: str, params: dict | None = None) -> dict:
    url = path_or_url if path_or_url.startswith("https://") else BASE_V1 + path_or_url
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_all_contacts(limit: int = 100, cap: int = 1000) -> tuple[list[dict], float]:
    """Page through v1 contacts via meta.nextPageUrl. Returns (contacts, total)."""
    contacts: list[dict] = []
    total = 0.0
    url = f"{BASE_V1}/contacts/?limit={limit}"
    while url and len(contacts) < cap:
        r = ghl_get(url)
        batch = r.get("contacts", [])
        contacts.extend(batch)
        meta = r.get("meta", {})
        total = float(meta.get("total", total) or total)
        nxt = meta.get("nextPageUrl") or ""
        url = nxt if nxt.startswith("https://rest.gohighlevel.com/") else None
        if not batch:
            break
    return contacts, total


def fetch_open_opportunities(cap_per_pipeline: int = 300) -> list[dict]:
    """Open opportunities across every pipeline, with stage names attached."""
    pipes = ghl_get("/pipelines/").get("pipelines", [])
    out: list[dict] = []
    for p in pipes:
        stage_names = {s.get("id"): s.get("name", "?") for s in p.get("stages", [])}
        url = f"{BASE_V1}/pipelines/{p['id']}/opportunities?limit=100"
        fetched = 0
        while url and fetched < cap_per_pipeline:
            r = ghl_get(url)
            batch = r.get("opportunities", [])
            for o in batch:
                if (o.get("status") or "").lower() == "open":
                    o["pipelineStageName"] = stage_names.get(o.get("pipelineStageId"), "Unknown")
                    o["pipelineName"] = p.get("name", "?")
                    out.append(o)
            fetched += len(batch)
            meta = r.get("meta", {})
            nxt = meta.get("nextPageUrl") or ""
            url = nxt if nxt.startswith("https://rest.gohighlevel.com/") else None
            if not batch:
                break
    return out


def main():
    api_key = env("GHL_API_KEY")
    if not api_key:
        write_snapshot(SOURCE, "error", "missing GHL_API_KEY in ~/.claude/.env")
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
        contacts, total_contacts = fetch_all_contacts()
        append_row(ts, SOURCE, "total_contacts", total_contacts, "ok", "")

        cutoff_7d  = now_dt - timedelta(days=7)
        cutoff_14d = now_dt - timedelta(days=14)
        cutoff_90d = now_dt - timedelta(days=90)

        active_leads = 0
        stale_leads  = 0
        seen_new_lead_phones: set[str] = set()
        new_leads_7d = 0

        for c in contacts:
            added    = parse_dt(c.get("dateAdded"))
            activity = parse_dt(c.get("lastActivity") or c.get("dateUpdated"))
            tags_lower = [t.lower().strip() for t in (c.get("tags") or [])]
            is_new_lead = "new lead" in tags_lower

            if added and added >= cutoff_90d:
                active_leads += 1
                if is_new_lead and added >= cutoff_7d:
                    phone = (c.get("phone") or "").strip()
                    dedup_key = phone if phone else c.get("id", "")
                    if dedup_key not in seen_new_lead_phones:
                        seen_new_lead_phones.add(dedup_key)
                        new_leads_7d += 1
                elif added < cutoff_14d:
                    if not activity or activity < cutoff_14d:
                        stale_leads += 1

        append_row(ts, SOURCE, "active_leads",  float(active_leads),  "ok", "")
        append_row(ts, SOURCE, "new_leads_7d",  float(new_leads_7d),  "ok", "")
        append_row(ts, SOURCE, "stale_leads",   float(stale_leads),   "ok", "")

        try:
            opps = fetch_open_opportunities()
            pipeline_value = sum(float(o.get("monetaryValue") or 0) for o in opps)
            append_row(ts, SOURCE, "pipeline_value", pipeline_value, "ok", "")
            append_row(ts, SOURCE, "open_opportunities", float(len(opps)), "ok", "")
        except Exception as e:
            append_row(ts, SOURCE, "pipeline_value", 0.0, "error", str(e)[:100])

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
