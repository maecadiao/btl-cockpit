"""Pull GoHighLevel CRM metrics into metrics.csv.

Metrics written (source="ghl"):
  total_contacts, active_leads, new_leads_7d, pipeline_value
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import append_row, env, now_iso, write_snapshot

GHL_BASE = "https://services.leadconnectorhq.com"
MAX_PAGES = 5


def _ghl_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {env('GHL_API_KEY')}",
        "Version": "2021-07-28",
        "Accept": "application/json",
    }


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_ghl_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_contacts(location_id: str) -> tuple[int, int]:
    """Return (total_contacts, new_leads_7d)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    total = 0
    new_7d = 0
    url: str | None = (
        f"{GHL_BASE}/contacts/?locationId={location_id}&limit=100"
    )
    pages = 0
    while url and pages < MAX_PAGES:
        data = _get(url)
        contacts = data.get("contacts", [])
        total += len(contacts)
        for c in contacts:
            date_added = c.get("dateAdded", "")
            if date_added:
                try:
                    # dateAdded may be ISO string or epoch ms
                    if isinstance(date_added, (int, float)):
                        added_dt = datetime.fromtimestamp(
                            date_added / 1000, tz=timezone.utc
                        )
                    else:
                        added_dt = datetime.fromisoformat(
                            date_added.replace("Z", "+00:00")
                        )
                    if added_dt >= cutoff:
                        new_7d += 1
                except (ValueError, OSError):
                    pass
        meta = data.get("meta", {})
        next_url = meta.get("nextPageUrl")
        url = next_url if next_url else None
        pages += 1
    return total, new_7d


def fetch_opportunities(location_id: str) -> tuple[int, float]:
    """Return (active_leads, pipeline_value)."""
    url = (
        f"{GHL_BASE}/opportunities/search"
        f"?location_id={location_id}&limit=100&status=open"
    )
    data = _get(url)
    opps = data.get("opportunities", [])
    pipeline_value = sum(
        float(o.get("monetaryValue") or 0) for o in opps
    )
    return len(opps), pipeline_value


def main() -> None:
    api_key = env("GHL_API_KEY")
    location_id = env("GHL_LOCATION_ID")

    if not api_key or not location_id:
        write_snapshot("ghl", "error", "GHL_API_KEY or GHL_LOCATION_ID not set")
        return

    ts = now_iso()

    try:
        total_contacts, new_leads_7d = fetch_contacts(location_id)
    except urllib.error.HTTPError as exc:
        write_snapshot("ghl", "error", f"contacts fetch failed: {exc.code} {exc.reason}")
        return
    except Exception as exc:  # noqa: BLE001
        write_snapshot("ghl", "error", f"contacts fetch failed: {exc}")
        return

    try:
        active_leads, pipeline_value = fetch_opportunities(location_id)
    except urllib.error.HTTPError as exc:
        write_snapshot("ghl", "error", f"opportunities fetch failed: {exc.code} {exc.reason}")
        return
    except Exception as exc:  # noqa: BLE001
        write_snapshot("ghl", "error", f"opportunities fetch failed: {exc}")
        return

    metrics = {
        "total_contacts": total_contacts,
        "active_leads": active_leads,
        "new_leads_7d": new_leads_7d,
        "pipeline_value": pipeline_value,
    }
    for metric, value in metrics.items():
        append_row(ts, "ghl", metric, float(value), "ok", "")

    write_snapshot("ghl", "ok")
    print(f"[ghl] {metrics}")


if __name__ == "__main__":
    main()
