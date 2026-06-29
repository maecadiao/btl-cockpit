"""Pull Jobber job metrics into metrics.csv.

Metrics written (source="jobber"):
  jobs_today, jobs_week, jobs_scheduled, jobs_late
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

JOBBER_URL = "https://api.getjobber.com/api/graphql"

JOBS_QUERY = """
{
  jobs(filter: { status: [scheduled, active, late] }) {
    nodes {
      id
      jobStatus
      startAt
    }
    totalCount
  }
}
"""


def fetch_jobs(access_token: str) -> dict:
    payload = json.dumps({"query": JOBS_QUERY}).encode()
    req = urllib.request.Request(
        JOBBER_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-JOBBER-GRAPHQL-VERSION": "2024-11-07",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    access_token = env("JOBBER_ACCESS_TOKEN")
    if not access_token:
        write_snapshot("jobber", "error", "JOBBER_ACCESS_TOKEN not set")
        return

    try:
        result = fetch_jobs(access_token)
    except urllib.error.HTTPError as exc:
        write_snapshot("jobber", "error", f"GraphQL request failed: {exc.code} {exc.reason}")
        return
    except Exception as exc:  # noqa: BLE001
        write_snapshot("jobber", "error", f"GraphQL request failed: {exc}")
        return

    errors = result.get("errors")
    if errors:
        write_snapshot("jobber", "error", str(errors[0].get("message", errors)))
        return

    jobs_data = result.get("data", {}).get("jobs", {})
    nodes = jobs_data.get("nodes", [])
    total_count = int(jobs_data.get("totalCount", len(nodes)))

    now_utc = datetime.now(timezone.utc)
    today_date = now_utc.date()

    # Week bounds (Mon–Sun UTC)
    monday = now_utc - timedelta(days=now_utc.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6)
    sunday = sunday.replace(hour=23, minute=59, second=59, microsecond=999999)

    jobs_today = 0
    jobs_week = 0
    jobs_late = 0

    for node in nodes:
        status = (node.get("jobStatus") or "").lower()
        if status == "late":
            jobs_late += 1

        start_at = node.get("startAt")
        if start_at:
            try:
                dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
                if dt.date() == today_date:
                    jobs_today += 1
                if monday <= dt <= sunday:
                    jobs_week += 1
            except ValueError:
                pass

    ts = now_iso()
    metrics = {
        "jobs_today": jobs_today,
        "jobs_week": jobs_week,
        "jobs_scheduled": total_count,
        "jobs_late": jobs_late,
    }
    for metric, value in metrics.items():
        append_row(ts, "jobber", metric, float(value), "ok", "")

    write_snapshot("jobber", "ok")
    print(f"[jobber] {metrics}")


if __name__ == "__main__":
    main()
