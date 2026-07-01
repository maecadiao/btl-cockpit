"""pull_jobber.py — Jobber job scheduling metrics.

Emits:
  jobber:jobs_today     — jobs with status 'today' (scheduled for today)
  jobber:jobs_week      — jobs starting this calendar week
  jobber:jobs_scheduled — total upcoming + active jobs
  jobber:jobs_late      — overdue jobs

Credentials in ~/.claude/.env:
  JOBBER_ACCESS_TOKEN  — refresh token (permanent, rotation disabled)
  JOBBER_CLIENT_ID     — from developer.getjobber.com
  JOBBER_CLIENT_SECRET — from developer.getjobber.com
"""

from __future__ import annotations
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import env, now_iso, append_row, write_snapshot

SOURCE    = "jobber"
GQL_URL   = "https://api.getjobber.com/api/graphql"
TOKEN_URL = "https://api.getjobber.com/api/oauth/token"


def get_access_token(refresh_token: str, client_id: str, client_secret: str) -> str:
    body = urllib.parse.urlencode({
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def jobber_query(token: str, query: str) -> dict:
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        GQL_URL,
        data=payload,
        headers={
            "Authorization":             f"Bearer {token}",
            "Content-Type":              "application/json",
            "X-JOBBER-GRAPHQL-VERSION":  "2023-11-15",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def job_count(token: str, status: str) -> int:
    r = jobber_query(token, f"{{ jobs(filter: {{ status: {status} }}) {{ totalCount }} }}")
    return int(r["data"]["jobs"]["totalCount"])


def main():
    refresh_token = env("JOBBER_ACCESS_TOKEN")
    client_id     = env("JOBBER_CLIENT_ID")
    client_secret = env("JOBBER_CLIENT_SECRET")

    if not refresh_token:
        write_snapshot(SOURCE, "error", "missing JOBBER_ACCESS_TOKEN in ~/.claude/.env")
        return

    try:
        token = get_access_token(refresh_token, client_id, client_secret)
    except Exception as e:
        write_snapshot(SOURCE, "error", f"token refresh failed: {str(e)[:160]}")
        return

    ts         = now_iso()
    today      = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    week_end   = (today + timedelta(days=6 - today.weekday())).isoformat()

    try:
        # Jobs today (Jobber's native "today" status)
        jobs_today = job_count(token, "today")
        append_row(ts, SOURCE, "jobs_today", float(jobs_today), "ok", "")

        # Jobs this week by start date
        r = jobber_query(token, f"""{{
            jobs(filter: {{ startAt: {{ after: "{week_start}T00:00:00Z", before: "{week_end}T23:59:59Z" }} }}) {{
                totalCount
            }}
        }}""")
        jobs_week = int(r["data"]["jobs"]["totalCount"])
        append_row(ts, SOURCE, "jobs_week", float(jobs_week), "ok", "")

        # Total scheduled = upcoming + today + active
        upcoming = job_count(token, "upcoming")
        active   = job_count(token, "active")
        jobs_scheduled = upcoming + jobs_today + active
        append_row(ts, SOURCE, "jobs_scheduled", float(jobs_scheduled), "ok", "")

        # Late / overdue jobs
        jobs_late = job_count(token, "late")
        append_row(ts, SOURCE, "jobs_late", float(jobs_late), "ok", "")

        write_snapshot(SOURCE, "ok")
        print(f"Jobber ok — today={jobs_today}, week={jobs_week}, "
              f"scheduled={jobs_scheduled} (upcoming={upcoming} + active={active}), late={jobs_late}")

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        write_snapshot(SOURCE, "error", f"HTTP {e.code}: {body}")
        print(f"Jobber error: {e.code}: {body}")
    except Exception as e:
        write_snapshot(SOURCE, "error", str(e)[:200])
        print(f"Jobber error: {e}")


if __name__ == "__main__":
    main()
