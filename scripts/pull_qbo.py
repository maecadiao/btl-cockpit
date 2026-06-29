"""Pull QuickBooks Online financial metrics into metrics.csv.

Metrics written (source="qbo"):
  revenue_mtd, revenue_ytd, ar_balance, outstanding_count
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import append_row, env, now_iso, write_snapshot

TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QBO_BASE = "https://quickbooks.api.intuit.com/v3/company"


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Exchange a refresh token for a new access token. Returns the access token string."""
    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()
    body = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError(f"No access_token in response: {data}")
    return access_token


def _qbo_get(url: str, access_token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _extract_pl_total_income(report: dict) -> float:
    """Walk P&L report rows to find the Total Income value."""
    rows = report.get("Rows", {}).get("Row", [])
    for row in rows:
        header = row.get("Header", {})
        col_data = header.get("ColData", [])
        if col_data and "Income" in str(col_data[0].get("value", "")):
            # Try Summary row for this section
            summary = row.get("Summary", {})
            summary_cols = summary.get("ColData", [])
            if len(summary_cols) >= 2:
                try:
                    return float(summary_cols[1].get("value", 0) or 0)
                except (ValueError, TypeError):
                    pass
    # Fallback: look for a row whose first ColData contains "Total Income"
    def _walk(rows_list: list) -> float | None:
        for r in rows_list:
            col_data = r.get("ColData", [])
            if col_data and "Total Income" in str(col_data[0].get("value", "")):
                if len(col_data) >= 2:
                    try:
                        return float(col_data[1].get("value", 0) or 0)
                    except (ValueError, TypeError):
                        pass
            # Recurse into nested rows
            nested = r.get("Rows", {}).get("Row", [])
            if nested:
                found = _walk(nested)
                if found is not None:
                    return found
            # Check Summary
            summary = r.get("Summary", {})
            sc = summary.get("ColData", [])
            if sc and "Total Income" in str(sc[0].get("value", "")):
                if len(sc) >= 2:
                    try:
                        return float(sc[1].get("value", 0) or 0)
                    except (ValueError, TypeError):
                        pass
        return None

    result = _walk(rows)
    return result if result is not None else 0.0


def _extract_ar(report: dict) -> tuple[float, int]:
    """Return (total_ar_balance, count_of_outstanding_invoices) from AgedReceivables."""
    rows = report.get("Rows", {}).get("Row", [])
    total = 0.0
    count = 0

    def _walk(rows_list: list) -> None:
        nonlocal total, count
        for r in rows_list:
            row_type = r.get("type", "")
            col_data = r.get("ColData", [])
            # Data rows have actual invoice amounts
            if row_type == "Data" and col_data:
                # Last column in aged receivables is typically the total
                # Skip header-style rows (first col usually customer name)
                first_val = str(col_data[0].get("value", "")).strip()
                if first_val and first_val not in ("", "TOTAL"):
                    # Sum all amount columns (cols 1 onward, skip non-numeric)
                    row_total = 0.0
                    for col in col_data[1:]:
                        try:
                            v = float(col.get("value", 0) or 0)
                            row_total += v
                        except (ValueError, TypeError):
                            pass
                    if row_total > 0:
                        total += row_total
                        count += 1
            # Check Summary totals
            summary = r.get("Summary", {})
            sc = summary.get("ColData", [])
            if sc and "TOTAL" in str(sc[0].get("value", "")).upper():
                # Use the last numeric column as the grand total
                for col in reversed(sc[1:]):
                    try:
                        v = float(col.get("value", 0) or 0)
                        if v > 0:
                            total = v  # override with authoritative total
                            break
                    except (ValueError, TypeError):
                        pass
            nested = r.get("Rows", {}).get("Row", [])
            if nested:
                _walk(nested)

    _walk(rows)
    return total, count


def main() -> None:
    client_id = env("QBO_CLIENT_ID")
    client_secret = env("QBO_CLIENT_SECRET")
    refresh_token = env("QBO_REFRESH_TOKEN")
    realm_id = env("QBO_REALM_ID")

    if not all([client_id, client_secret, refresh_token, realm_id]):
        write_snapshot(
            "qbo", "error",
            "Missing one or more of: QBO_CLIENT_ID, QBO_CLIENT_SECRET, QBO_REFRESH_TOKEN, QBO_REALM_ID"
        )
        return

    # Step 1: refresh access token
    try:
        access_token = refresh_access_token(client_id, client_secret, refresh_token)
    except urllib.error.HTTPError as exc:
        write_snapshot("qbo", "error", f"Token refresh failed: {exc.code} {exc.reason}")
        return
    except Exception as exc:  # noqa: BLE001
        write_snapshot("qbo", "error", f"Token refresh failed: {exc}")
        return

    now_utc = datetime.now(timezone.utc)
    year = now_utc.year
    month = now_utc.month
    today_str = now_utc.strftime("%Y-%m-%d")
    mtd_start = f"{year}-{month:02d}-01"
    ytd_start = f"{year}-01-01"

    base = f"{QBO_BASE}/{realm_id}"

    # Step 2: MTD P&L
    try:
        pl_mtd = _qbo_get(
            f"{base}/reports/ProfitAndLoss"
            f"?summarize_column_by=Month&start_date={mtd_start}&end_date={today_str}",
            access_token,
        )
        revenue_mtd = _extract_pl_total_income(pl_mtd.get("QueryResponse", pl_mtd))
    except Exception as exc:  # noqa: BLE001
        write_snapshot("qbo", "error", f"P&L MTD fetch failed: {exc}")
        return

    # Step 3: YTD P&L
    try:
        pl_ytd = _qbo_get(
            f"{base}/reports/ProfitAndLoss"
            f"?start_date={ytd_start}&end_date={today_str}",
            access_token,
        )
        revenue_ytd = _extract_pl_total_income(pl_ytd.get("QueryResponse", pl_ytd))
    except Exception as exc:  # noqa: BLE001
        write_snapshot("qbo", "error", f"P&L YTD fetch failed: {exc}")
        return

    # Step 4: Aged Receivables
    try:
        ar_report = _qbo_get(
            f"{base}/reports/AgedReceivables",
            access_token,
        )
        ar_balance, outstanding_count = _extract_ar(
            ar_report.get("QueryResponse", ar_report)
        )
    except Exception as exc:  # noqa: BLE001
        write_snapshot("qbo", "error", f"AgedReceivables fetch failed: {exc}")
        return

    ts = now_iso()
    metrics = {
        "revenue_mtd": revenue_mtd,
        "revenue_ytd": revenue_ytd,
        "ar_balance": ar_balance,
        "outstanding_count": outstanding_count,
    }
    for metric, value in metrics.items():
        append_row(ts, "qbo", metric, float(value), "ok", "")

    write_snapshot("qbo", "ok")
    print(f"[qbo] {metrics}")


if __name__ == "__main__":
    main()
