"""pull_daily_series.py — daily history so the overview range buttons work.

The headline cards (Revenue, Spending, New Leads, Jobs) become totals over the
selected window (Today / 7D / 30D / 90D / All). That needs per-day numbers,
which the snapshot metrics in metrics.csv don't provide — so this pull builds
a 365-day daily series for each and caches it to
system/metrics/daily-series.json.

  { "updated": iso,
    "days":   ["YYYY-MM-DD", ... last 365],
    "series": { "revenue": [...], "spending": [...], "leads": [...], "jobs": [...] },
    "notes":  { name: "error (showing last-known)" } }

Merge-on-write: a failing source keeps its previous series instead of zeroing
the cards. Runs on the scheduler (pull_*.py) cadence like the other pulls.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import VAULT_METRICS, env, now_iso, write_snapshot

OUT_PATH = VAULT_METRICS / "daily-series.json"
N_DAYS = 365
GHL_CONTACT_CAP = 2000   # ~20 pages; covers well over a year of BTL lead volume
JOBBER_PAGE_CAP = 8      # 100 jobs/page


def _days() -> list[str]:
    today = date.today()
    return [(today - timedelta(days=n)).isoformat() for n in range(N_DAYS - 1, -1, -1)]


def _bucket(days: list[str], rows: list[tuple[str, float]]) -> list[float]:
    by_d = {d: 0.0 for d in days}
    for d, val in rows:
        if d in by_d:
            by_d[d] += val
    return [round(by_d[d], 2) for d in days]


# ── QBO: revenue (invoices) + spending (purchases + bills) by day ────────────

def qbo_series(days: list[str]):
    try:
        from pull_qbo import qbo_query, refresh_access_token_with_fallback
        token = refresh_access_token_with_fallback(env("QBO_CLIENT_ID"), env("QBO_CLIENT_SECRET"))
        realm = env("QBO_REALM_ID")
        start = days[0]

        inv = qbo_query(realm, token,
                        f"SELECT TxnDate, TotalAmt FROM Invoice WHERE TxnDate >= '{start}' MAXRESULTS 1000")
        revenue = _bucket(days, [
            (i.get("TxnDate", "")[:10], float(i.get("TotalAmt", 0)))
            for i in inv.get("QueryResponse", {}).get("Invoice", [])
        ])

        spend_rows: list[tuple[str, float]] = []
        for table in ("Purchase", "Bill"):
            try:
                r = qbo_query(realm, token,
                              f"SELECT TxnDate, TotalAmt FROM {table} WHERE TxnDate >= '{start}' MAXRESULTS 1000")
                spend_rows += [
                    (i.get("TxnDate", "")[:10], float(i.get("TotalAmt", 0)))
                    for i in r.get("QueryResponse", {}).get(table, [])
                ]
            except Exception:  # noqa: BLE001
                pass
        spending = _bucket(days, spend_rows) if spend_rows else None
        return revenue, spending, None
    except Exception as e:  # noqa: BLE001
        return None, None, f"QuickBooks: {str(e)[:120]}"


# ── GHL: new leads per day (contacts by dateAdded) ───────────────────────────

def ghl_series(days: list[str]):
    if not env("GHL_API_KEY"):
        return None, "GoHighLevel: credentials not configured"
    try:
        import pull_ghl
        pull_ghl.HEADERS["Authorization"] = f"Bearer {env('GHL_API_KEY')}"
        contacts, _total = pull_ghl.fetch_all_contacts(cap=GHL_CONTACT_CAP)
        rows = [((c.get("dateAdded") or "")[:10], 1.0) for c in contacts]
        return _bucket(days, rows), None
    except urllib.error.HTTPError as e:
        return None, f"GoHighLevel: HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, f"GoHighLevel: {str(e)[:100]}"


# ── Jobber: jobs per day by startAt ──────────────────────────────────────────

def jobber_series(days: list[str]):
    if not env("JOBBER_ACCESS_TOKEN"):
        return None, "Jobber: credentials not configured"
    try:
        from pull_jobber import get_access_token, jobber_query
        token = get_access_token(env("JOBBER_ACCESS_TOKEN"), env("JOBBER_CLIENT_ID"),
                                 env("JOBBER_CLIENT_SECRET"))
        after = datetime.fromisoformat(days[0] + "T00:00:00+00:00")
        before = datetime.now(timezone.utc) + timedelta(days=1)
        rows: list[tuple[str, float]] = []
        cursor = None
        for _ in range(JOBBER_PAGE_CAP):
            after_arg = f', after: "{cursor}"' if cursor else ""
            r = jobber_query(token, f"""{{
                jobs(first: 100{after_arg},
                     filter: {{ startAt: {{ after: "{after.isoformat()}", before: "{before.isoformat()}" }} }}) {{
                    nodes {{ startAt }}
                    pageInfo {{ hasNextPage endCursor }}
                }}
            }}""")
            jobs = r.get("data", {}).get("jobs", {})
            for n in jobs.get("nodes", []):
                sa = n.get("startAt") or ""
                if sa:
                    rows.append((sa[:10], 1.0))
            pi = jobs.get("pageInfo", {})
            if not pi.get("hasNextPage"):
                break
            cursor = pi.get("endCursor")
        return _bucket(days, rows), None
    except urllib.error.HTTPError as e:
        return None, f"Jobber: HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, f"Jobber: {str(e)[:100]}"


def main() -> None:
    days = _days()

    existing: dict = {}
    try:
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    old_series = existing.get("series", {}) if existing.get("days") == days else {}

    revenue, spending, qbo_err = qbo_series(days)
    leads, ghl_err = ghl_series(days)
    jobs, job_err = jobber_series(days)

    series, notes = {}, {}
    for name, fresh, err in [
        ("revenue", revenue, qbo_err),
        ("spending", spending, qbo_err),
        ("leads", leads, ghl_err),
        ("jobs", jobs, job_err),
    ]:
        if fresh is not None:
            series[name] = fresh
        elif name in old_series:
            series[name] = old_series[name]
            if err:
                notes[name] = err + " (showing last-known)"
        elif err:
            notes[name] = err

    out = {"updated": now_iso(), "days": days, "series": series, "notes": notes}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out), encoding="utf-8")
    write_snapshot("daily_series", "ok" if series else "error",
                   "; ".join(notes.values())[:200])
    print(f"[daily_series] series={list(series)} notes={list(notes)}")


if __name__ == "__main__":
    main()
