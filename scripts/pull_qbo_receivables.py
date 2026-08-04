"""pull_qbo_receivables.py — accounts-receivable snapshot for the QuickBooks tab.

Writes system/metrics/qbo-receivables.json:

  {
    "updated": iso,
    "total_open": 175014.0,      # total money owed to us
    "open_count": 140,
    "overdue_total": 98230.0,    # portion past its due date
    "aging": [{bucket, count, value}, ...],   # Current / 1-30 / 31-60 / 61-90 / 90+
    "top_unpaid": [{customer, doc, value, due, days_overdue}, ...],  # top 8 by balance
    "error": null
  }

The cockpit reads this so the QuickBooks tab shows who owes what and how late,
instead of four bare totals.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import VAULT_METRICS, env, now_iso, write_snapshot

OUT_PATH = VAULT_METRICS / "qbo-receivables.json"

_BUCKETS = ["Current", "1–30 days", "31–60 days", "61–90 days", "90+ days"]


def _bucket_for(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "Current"
    if days_overdue <= 30:
        return "1–30 days"
    if days_overdue <= 60:
        return "31–60 days"
    if days_overdue <= 90:
        return "61–90 days"
    return "90+ days"


def main() -> None:
    out: dict = {"updated": now_iso(), "error": None}
    try:
        from pull_qbo import qbo_query, refresh_access_token_with_fallback
        token = refresh_access_token_with_fallback(env("QBO_CLIENT_ID"), env("QBO_CLIENT_SECRET"))
        realm = env("QBO_REALM_ID")
        r = qbo_query(realm, token,
                      "SELECT * FROM Invoice WHERE Balance > '0' MAXRESULTS 1000")
    except Exception as e:  # noqa: BLE001
        out["error"] = f"QuickBooks: {str(e)[:130]}"
        _write(out, "error")
        return

    invoices = r.get("QueryResponse", {}).get("Invoice", [])
    today = date.today()

    def _due(inv: dict) -> date | None:
        raw = inv.get("DueDate") or inv.get("TxnDate") or ""
        try:
            return datetime.fromisoformat(raw[:10]).date()
        except (ValueError, TypeError):
            return None

    agg = {b: {"count": 0, "value": 0.0} for b in _BUCKETS}
    rows = []
    overdue_total = 0.0
    for inv in invoices:
        bal = float(inv.get("Balance", 0) or 0)
        if bal < 1.0:
            continue
        due = _due(inv)
        days = (today - due).days if due else 0
        bucket = _bucket_for(days)
        agg[bucket]["count"] += 1
        agg[bucket]["value"] += bal
        if days > 0:
            overdue_total += bal
        rows.append({
            "customer": (inv.get("CustomerRef") or {}).get("name", "Unknown"),
            "doc": inv.get("DocNumber", ""),
            "value": round(bal, 2),
            "due": due.isoformat() if due else "",
            "days_overdue": max(0, days),
        })

    rows.sort(key=lambda x: -x["value"])
    out.update({
        "total_open": round(sum(r2["value"] for r2 in rows), 2),
        "open_count": len(rows),
        "overdue_total": round(overdue_total, 2),
        "aging": [{"bucket": b, "count": agg[b]["count"], "value": round(agg[b]["value"], 2)}
                  for b in _BUCKETS],
        "top_unpaid": rows[:8],
    })
    _write(out, "ok")
    print(f"[qbo_receivables] open={out['open_count']} owed=${out['total_open']:,.0f} "
          f"overdue=${out['overdue_total']:,.0f}")


def _write(out: dict, status: str) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    write_snapshot("qbo_receivables", status, out.get("error") or "")


if __name__ == "__main__":
    main()
