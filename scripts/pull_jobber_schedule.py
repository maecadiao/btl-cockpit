"""pull_jobber_schedule.py — schedule snapshot for the Jobber cockpit tab.

Writes system/metrics/jobber-schedule.json:

  {
    "updated": iso,
    "jobs_today": 0, "jobs_week": 1, "jobs_scheduled": 203, "jobs_late": 3,
    "scheduled_value": 412900.0,           # $ of all upcoming jobs
    "upcoming": [{date, client, title, value, number}, ...],  # next 8 by start
    "late":     [{date, client, title, value, number}, ...],  # up to 6
    "error": null
  }

The cockpit reads this so the Jobber tab renders instantly, with the actual
upcoming jobs and overdue jobs rather than four lonely counts.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import VAULT_METRICS, env, now_iso, write_snapshot

OUT_PATH = VAULT_METRICS / "jobber-schedule.json"

_JOB_FIELDS = "title jobNumber total startAt client { name }"


def _dt(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _fmt(n: dict) -> dict:
    d = _dt(n.get("startAt"))
    return {
        "date": f"{d:%b} {d.day}" if d else "—",
        "client": (n.get("client") or {}).get("name", "—"),
        "title": (n.get("title") or "(no title)").strip(),
        "value": round(float(n.get("total") or 0), 2),
        "number": n.get("jobNumber"),
    }


def main() -> None:
    from pull_jobber import get_access_token, jobber_query, job_count

    out: dict = {"updated": now_iso(), "error": None}
    rt = env("JOBBER_ACCESS_TOKEN")
    if not rt:
        out["error"] = "Jobber: credentials not configured"
        _write(out, "error")
        return
    try:
        token = get_access_token(rt, env("JOBBER_CLIENT_ID"), env("JOBBER_CLIENT_SECRET"))
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Jobber: token refresh failed: {str(e)[:120]}"
        _write(out, "error")
        return

    try:
        # Paginate upcoming jobs (up to ~400) so scheduled revenue is accurate.
        upcoming: list[dict] = []
        cursor = None
        for _ in range(4):
            after = f', after: "{cursor}"' if cursor else ""
            r = jobber_query(token, f"""{{
                jobs(filter: {{ status: upcoming }}, first: 100{after}) {{
                    nodes {{ {_JOB_FIELDS} }}
                    pageInfo {{ hasNextPage endCursor }}
                }}
            }}""")
            j = r["data"]["jobs"]
            upcoming += j["nodes"]
            if not j["pageInfo"]["hasNextPage"]:
                break
            cursor = j["pageInfo"]["endCursor"]

        rl = jobber_query(token, f"""{{
            jobs(filter: {{ status: late }}, first: 20) {{ nodes {{ {_JOB_FIELDS} }} }}
        }}""")
        late = rl["data"]["jobs"]["nodes"]

        today_ct = job_count(token, "today")
        active_ct = job_count(token, "active")
        late_ct = job_count(token, "late")

        today = date.today()
        ws = today - timedelta(days=today.weekday())
        we = today + timedelta(days=6 - today.weekday())
        week_ct = sum(1 for n in upcoming
                      if (_dt(n.get("startAt")) and ws <= _dt(n["startAt"]).date() <= we))

        up_sorted = sorted((n for n in upcoming if _dt(n.get("startAt"))),
                           key=lambda n: _dt(n["startAt"]))
        late_sorted = sorted(late, key=lambda n: _dt(n.get("startAt")) or datetime.max.replace(tzinfo=timezone.utc))

        out.update({
            "jobs_today": today_ct,
            "jobs_week": week_ct,
            "jobs_scheduled": len(upcoming) + today_ct + active_ct,
            "jobs_late": late_ct,
            "scheduled_value": round(sum(float(n.get("total") or 0) for n in upcoming), 2),
            "upcoming": [_fmt(n) for n in up_sorted[:8]],
            "late": [_fmt(n) for n in late_sorted[:6]],
        })
        _write(out, "ok")
        print(f"[jobber_schedule] scheduled={out['jobs_scheduled']} "
              f"value=${out['scheduled_value']:,.0f} upcoming_shown={len(out['upcoming'])}")
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Jobber: {str(e)[:150]}"
        _write(out, "error")


def _write(out: dict, status: str) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    write_snapshot("jobber_schedule", status, out.get("error") or "")


if __name__ == "__main__":
    main()
