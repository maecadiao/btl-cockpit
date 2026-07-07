"""pull_bizhealth.py — monthly Business Health series for the overview chart.

Writes system/metrics/business-health.json:
  {
    "updated": iso-ts,
    "months":  ["YYYY-MM", ... last 12],
    "series":  { "earnings": [...], "spending": [...], "leads": [...], "jobs": [...] },
    "notes":   { source: "error text" }        # only for sources that failed
  }

Merge-on-write: a failing source keeps its last-known series instead of
blanking the chart. Sources: QBO invoices (earnings) + purchases/bills
(spending), GHL contacts by dateAdded (leads), Jobber jobs by startAt (jobs).
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import VAULT_METRICS, env, now_iso, write_snapshot

OUT_PATH = VAULT_METRICS / "business-health.json"
N_MONTHS = 12


def _months() -> list[str]:
    out = []
    d = date.today().replace(day=1)
    for _ in range(N_MONTHS):
        out.append(d.strftime("%Y-%m"))
        d = (d - timedelta(days=1)).replace(day=1)
    return list(reversed(out))


def _bucket(months: list[str], rows: list[tuple[str, float]]) -> list[float]:
    by_m = {m: 0.0 for m in months}
    for ym, val in rows:
        if ym in by_m:
            by_m[ym] += val
    return [round(by_m[m], 2) for m in months]


# ── QBO: earnings (invoices) + spending (purchases and bills) ────────────────

def qbo_series(months: list[str]) -> tuple[list[float] | None, list[float] | None, str | None]:
    try:
        from pull_qbo import qbo_query, refresh_access_token_with_fallback
        token = refresh_access_token_with_fallback(env("QBO_CLIENT_ID"), env("QBO_CLIENT_SECRET"))
        realm = env("QBO_REALM_ID")
        start = f"{months[0]}-01"

        inv = qbo_query(realm, token,
                        f"SELECT TxnDate, TotalAmt FROM Invoice WHERE TxnDate >= '{start}' MAXRESULTS 1000")
        earnings = _bucket(months, [
            (i.get("TxnDate", "")[:7], float(i.get("TotalAmt", 0)))
            for i in inv.get("QueryResponse", {}).get("Invoice", [])
        ])

        spend_rows: list[tuple[str, float]] = []
        for table in ("Purchase", "Bill"):
            try:
                r = qbo_query(realm, token,
                              f"SELECT TxnDate, TotalAmt FROM {table} WHERE TxnDate >= '{start}' MAXRESULTS 1000")
                spend_rows += [
                    (i.get("TxnDate", "")[:7], float(i.get("TotalAmt", 0)))
                    for i in r.get("QueryResponse", {}).get(table, [])
                ]
            except Exception:  # noqa: BLE001 — one table failing shouldn't kill both
                pass
        spending = _bucket(months, spend_rows) if spend_rows else None
        return earnings, spending, None
    except Exception as e:  # noqa: BLE001
        return None, None, f"QuickBooks: {str(e)[:120]}"


# ── GHL: new leads per month (contacts by dateAdded) ─────────────────────────

def ghl_series(months: list[str]) -> tuple[list[float] | None, str | None]:
    api_key, loc = env("GHL_API_KEY"), env("GHL_LOCATION_ID")
    if not api_key or not loc:
        return None, "GoHighLevel: credentials not configured"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Version": "2021-04-15",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; BTL-Cockpit/1.0)",
    }
    try:
        rows, params = [], {"locationId": loc, "limit": 100}
        for _ in range(10):  # up to 1000 newest contacts
            url = "https://services.leadconnectorhq.com/contacts/?" + urllib.parse.urlencode(params)
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
                data = json.loads(r.read())
            batch = data.get("contacts", [])
            rows += [((c.get("dateAdded") or "")[:7], 1.0) for c in batch]
            if len(batch) < 100 or not batch:
                break
            params = {"locationId": loc, "limit": 100, "startAfterId": batch[-1].get("id", "")}
        return _bucket(months, rows), None
    except urllib.error.HTTPError as e:
        return None, f"GoHighLevel: HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, f"GoHighLevel: {str(e)[:100]}"


# ── Jobber: jobs per month by startAt ─────────────────────────────────────────

def jobber_series(months: list[str]) -> tuple[list[float] | None, str | None]:
    if not env("JOBBER_ACCESS_TOKEN"):
        return None, "Jobber: credentials not configured"
    try:
        from pull_jobber import get_access_token, jobber_query
        token = get_access_token(env("JOBBER_ACCESS_TOKEN"), env("JOBBER_CLIENT_ID"),
                                 env("JOBBER_CLIENT_SECRET"))
        vals = []
        for ym in months:
            y, m = int(ym[:4]), int(ym[5:])
            start = datetime(y, m, 1, tzinfo=timezone.utc)
            end = datetime(y + (m == 12), (m % 12) + 1, 1, tzinfo=timezone.utc)
            r = jobber_query(token, f"""{{
                jobs(filter: {{ startAt: {{ after: "{start.isoformat()}", before: "{end.isoformat()}" }} }}) {{
                    totalCount
                }}
            }}""")
            vals.append(float(r.get("data", {}).get("jobs", {}).get("totalCount", 0)))
        return vals, None
    except urllib.error.HTTPError as e:
        return None, f"Jobber: HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, f"Jobber: {str(e)[:100]}"


def main() -> None:
    months = _months()

    existing: dict = {}
    try:
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    old_series = existing.get("series", {}) if existing.get("months") == months else {}

    earnings, spending, qbo_err = qbo_series(months)
    leads, ghl_err = ghl_series(months)
    jobs, job_err = jobber_series(months)

    series, notes = {}, {}
    for name, fresh, err in [
        ("earnings", earnings, qbo_err),
        ("spending", spending, qbo_err),
        ("leads", leads, ghl_err),
        ("jobs", jobs, job_err),
    ]:
        if fresh is not None:
            series[name] = fresh
        elif name in old_series:
            series[name] = old_series[name]   # keep last-known on failure
            if err:
                notes[name] = err + " (showing last-known data)"
        elif err:
            notes[name] = err

    out = {"updated": now_iso(), "months": months, "series": series, "notes": notes}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    write_snapshot("bizhealth", "ok" if series else "error",
                   "; ".join(notes.values())[:200])
    print(f"[bizhealth] series={list(series)} notes={list(notes)}")


if __name__ == "__main__":
    main()
