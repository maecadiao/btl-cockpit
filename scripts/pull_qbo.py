"""pull_qbo.py — QuickBooks Online metrics.

Emits:
  qbo:ar_balance        — total outstanding AR (open invoices)
  qbo:revenue_mtd       — revenue billed this calendar month
  qbo:revenue_ytd       — revenue billed this calendar year
  qbo:outstanding_count — number of unpaid invoices

Credentials needed in ~/.claude/.env:
  QBO_CLIENT_ID      — from Intuit Developer Portal (developer.intuit.com)
  QBO_CLIENT_SECRET  — same
  QBO_REFRESH_TOKEN  — obtained once via OAuth consent flow
  QBO_REALM_ID       — your QuickBooks Company ID (shown in URL when logged in)
"""

from __future__ import annotations
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from datetime import date, timezone, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import env, now_iso, append_row, write_snapshot, last_known_value

SOURCE = "qbo"

TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
BASE_URL  = "https://quickbooks.api.intuit.com/v3/company"

# Intuit ROTATES the refresh token: each refresh may invalidate the old value.
# Exactly one machine may own the token, and it must persist every rotation —
# a second machine refreshing with a stale copy kills both. On Railway, set
# QBO_TOKEN_STORE to a path on the persistent volume (e.g. /data/qbo_refresh_token);
# the env-var QBO_REFRESH_TOKEN then only seeds the store on first run.
_TOKEN_STORE = env("QBO_TOKEN_STORE")


def current_refresh_token() -> str:
    """Latest refresh token: token-store file first (survives rotation), then env."""
    if _TOKEN_STORE:
        try:
            stored = Path(_TOKEN_STORE).read_text(encoding="utf-8").strip()
            if stored:
                return stored
        except OSError:
            pass
    return env("QBO_REFRESH_TOKEN") or ""


def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Refresh QBO access token. Saves any new refresh_token Intuit returns so
    the next call doesn't fail due to token rotation."""
    creds = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type":  "application/x-www-form-urlencoded",
            "Accept":        "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    # Intuit sometimes rotates the refresh token. Always save it if present.
    new_rt = data.get("refresh_token")
    if new_rt and new_rt != refresh_token:
        _save_refresh_token(new_rt)
    return data["access_token"]


def _save_refresh_token(new_token: str) -> None:
    """Persist a rotated QBO_REFRESH_TOKEN to the token store (or ~/.claude/.env)."""
    if _TOKEN_STORE:
        try:
            store = Path(_TOKEN_STORE)
            store.parent.mkdir(parents=True, exist_ok=True)
            store.write_text(new_token, encoding="utf-8")
            return
        except OSError:
            pass  # fall through to .env attempt
    import re
    env_path = Path.home() / ".claude" / ".env"
    if not env_path.exists():
        return
    text = env_path.read_text(encoding="utf-8")
    text = re.sub(r"QBO_REFRESH_TOKEN=.*", f"QBO_REFRESH_TOKEN={new_token}", text)
    env_path.write_text(text, encoding="utf-8")


def qbo_query(realm_id: str, token: str, query: str) -> dict:
    url = f"{BASE_URL}/{realm_id}/query?query={urllib.parse.quote(query)}&minorversion=65"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    client_id     = env("QBO_CLIENT_ID")
    client_secret = env("QBO_CLIENT_SECRET")
    refresh_token = current_refresh_token()
    realm_id      = env("QBO_REALM_ID")

    if not all([client_id, client_secret, refresh_token, realm_id]):
        write_snapshot(SOURCE, "error",
            "missing QBO_CLIENT_ID / QBO_CLIENT_SECRET / QBO_REFRESH_TOKEN / QBO_REALM_ID in ~/.claude/.env")
        return

    try:
        token = get_access_token(client_id, client_secret, refresh_token)
    except Exception as e:
        write_snapshot(SOURCE, "error", f"token refresh failed: {str(e)[:160]}")
        return

    ts = now_iso()
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    year_start  = today.replace(month=1, day=1).isoformat()

    try:
        # AR balance — sum of ALL unpaid invoice balances (all-time, every dollar owed)
        r = qbo_query(realm_id, token,
            "SELECT * FROM Invoice WHERE Balance > '0' MAXRESULTS 1000")
        invoices = r.get("QueryResponse", {}).get("Invoice", [])
        ar_balance = sum(float(inv.get("Balance", 0)) for inv in invoices)

        # Open invoice count — PAST-DUE invoices with meaningful balance only.
        # Excludes: future-dated recurring invoices (due date > today) and
        # penny-balance invoices (<$1.00 rounding dust from partial payments).
        today_iso = today.isoformat()
        outstanding_count = sum(
            1 for inv in invoices
            if float(inv.get("Balance", 0)) >= 1.0                      # skip penny dust
            and (inv.get("DueDate") or inv.get("TxnDate") or "") <= today_iso  # skip future invoices
        )
        append_row(ts, SOURCE, "ar_balance",        ar_balance,        "ok", "")
        append_row(ts, SOURCE, "outstanding_count", outstanding_count, "ok", "")

        # Revenue MTD — sum of invoices billed this month
        r = qbo_query(realm_id, token,
            f"SELECT * FROM Invoice WHERE TxnDate >= '{month_start}' MAXRESULTS 1000")
        revenue_mtd = sum(
            float(inv.get("TotalAmt", 0))
            for inv in r.get("QueryResponse", {}).get("Invoice", [])
        )
        append_row(ts, SOURCE, "revenue_mtd", revenue_mtd, "ok", "")

        # Revenue YTD — sum of invoices billed this year
        r = qbo_query(realm_id, token,
            f"SELECT * FROM Invoice WHERE TxnDate >= '{year_start}' MAXRESULTS 1000")
        revenue_ytd = sum(
            float(inv.get("TotalAmt", 0))
            for inv in r.get("QueryResponse", {}).get("Invoice", [])
        )
        append_row(ts, SOURCE, "revenue_ytd", revenue_ytd, "ok", "")

        write_snapshot(SOURCE, "ok")

    except urllib.error.HTTPError as e:
        write_snapshot(SOURCE, "error", f"HTTP {e.code}: {str(e)[:160]}")
    except Exception as e:
        write_snapshot(SOURCE, "error", str(e)[:200])


if __name__ == "__main__":
    main()
