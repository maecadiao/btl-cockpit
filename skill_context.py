"""Live-data enrichment for skill runs on the cloud (Railway) API path.

On the office PC, skills run through the Claude CLI with real tool access, so
they fetch their own data. On Railway they run as a single no-tools Anthropic
API call — whatever data the skill needs must be injected into the prompt.
Each data-dependent skill's SKILL.md instructs the model to USE ONLY the
provided live-data blocks, so this module is what keeps those skills honest
instead of hallucinating numbers.

Every fetcher returns (data_text | None, status_note | None): real data blocks
start with "===" headers; failures become FETCH STATUS notes so the model can
say "data unavailable" rather than guessing. All errors are swallowed — a dead
source must never break a skill run.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPTS_DIR = Path(__file__).parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

BTL_TZ = ZoneInfo("America/Chicago")
FETCH_TIMEOUT = 20


def _env(name: str) -> str:
    if val := os.environ.get(name):
        return val
    dot_env = Path.home() / ".claude" / ".env"
    try:
        for raw in dot_env.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


# ── metrics.csv summary ───────────────────────────────────────────────────────

def _metrics_block(vault_path: Path, sources: list[str]) -> tuple[str | None, str | None]:
    """Latest value per (source, metric) from metrics.csv + per-source pull status."""
    metrics_csv = vault_path / "system" / "metrics" / "metrics.csv"
    snapshot = vault_path / "system" / "metrics" / "last-pull.json"
    latest: dict[tuple[str, str], tuple[str, float]] = {}
    try:
        with metrics_csv.open("r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                src = row.get("source", "")
                if src in sources and row.get("status") in ("ok", "stale"):
                    try:
                        latest[(src, row.get("metric", ""))] = (
                            row.get("timestamp", ""), float(row.get("value", "0")))
                    except ValueError:
                        continue
    except OSError:
        return None, "Metrics file not available."

    status: dict = {}
    try:
        status = json.loads(snapshot.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    lines = ["=== BUSINESS METRICS (latest pulled values) ==="]
    notes = []
    for src in sources:
        rows = {m: (ts, v) for (s, m), (ts, v) in latest.items() if s == src}
        st = status.get(src, {})
        if rows:
            for metric, (ts, val) in sorted(rows.items()):
                lines.append(f"- {src}.{metric} = {val:,.2f} (as of {ts})")
        if st.get("status") == "error":
            notes.append(f"{src}: pull failing — {st.get('error', '')[:120]}")
        elif not rows:
            notes.append(f"{src}: no data pulled yet")
    if len(lines) == 1:
        return None, "; ".join(notes) or "No metrics available."
    return "\n".join(lines) + "\n", ("; ".join(notes) + "\n" if notes else None)


# ── QuickBooks ────────────────────────────────────────────────────────────────

def _qbo_invoices(max_results: int = 1000) -> list[dict]:
    from pull_qbo import qbo_query, refresh_access_token_with_fallback  # scripts/
    token = refresh_access_token_with_fallback(_env("QBO_CLIENT_ID"), _env("QBO_CLIENT_SECRET"))
    realm = _env("QBO_REALM_ID")
    year_ago = (date.today() - timedelta(days=730)).isoformat()
    r = qbo_query(realm, token,
                  f"SELECT * FROM Invoice WHERE TxnDate >= '{year_ago}' "
                  f"ORDERBY TxnDate DESC MAXRESULTS {max_results}")
    return r.get("QueryResponse", {}).get("Invoice", [])


def _qbo_ar_detail() -> tuple[str | None, str | None]:
    """Open-invoice detail with aging buckets for the billing digest."""
    try:
        invoices = _qbo_invoices()
    except Exception as e:  # noqa: BLE001
        return None, f"QuickBooks unavailable: {str(e)[:120]}"
    today = date.today()
    open_inv = [i for i in invoices if float(i.get("Balance", 0)) >= 1.0]
    if not open_inv:
        return "=== QBO OPEN INVOICES — LIVE DATA ===\nNo open invoices. AR is clear.\n", None
    lines = [f"=== QBO OPEN INVOICES — LIVE DATA ({len(open_inv)} invoices, as of {today}) ===",
             "Format: customer | invoice# | open balance | due date | days overdue (negative = not yet due)"]
    for inv in sorted(open_inv, key=lambda i: i.get("DueDate") or i.get("TxnDate") or ""):
        due = inv.get("DueDate") or inv.get("TxnDate") or ""
        try:
            overdue = (today - date.fromisoformat(due)).days
        except ValueError:
            overdue = 0
        cust = (inv.get("CustomerRef") or {}).get("name", "Unknown")
        lines.append(f"- {cust} | #{inv.get('DocNumber', '?')} | "
                     f"${float(inv.get('Balance', 0)):,.2f} | due {due} | {overdue}d")
    return "\n".join(lines) + "\n", None


def _qbo_monthly_revenue(months: int = 25) -> tuple[str | None, str | None]:
    """Invoiced revenue by month for P&L narrative / revenue growth digest."""
    try:
        invoices = _qbo_invoices()
    except Exception as e:  # noqa: BLE001
        return None, f"QuickBooks unavailable: {str(e)[:120]}"
    by_month: dict[str, float] = {}
    for inv in invoices:
        txn = inv.get("TxnDate", "")
        if len(txn) >= 7:
            by_month[txn[:7]] = by_month.get(txn[:7], 0.0) + float(inv.get("TotalAmt", 0))
    if not by_month:
        return None, "QuickBooks returned no invoices for the last 24 months."
    lines = [f"=== QBO INVOICED REVENUE BY MONTH — LIVE DATA (as of {date.today()}) ===",
             "NOTE: figures are total invoiced amounts (gross revenue billed). "
             "Expense/COGS data is NOT available — do not invent expense or profit numbers."]
    for month in sorted(by_month)[-months:]:
        lines.append(f"- {month}: ${by_month[month]:,.2f}")
    return "\n".join(lines) + "\n", None


# ── GoHighLevel pipeline ──────────────────────────────────────────────────────

def _ghl_pipeline() -> tuple[str | None, str | None]:
    """Open opportunities by stage, plus stale + high-value callouts (v1 API)."""
    if not _env("GHL_API_KEY"):
        return None, "GHL credentials not configured."
    try:
        import pull_ghl
        pull_ghl.HEADERS["Authorization"] = f"Bearer {_env('GHL_API_KEY')}"
        opps = pull_ghl.fetch_open_opportunities()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None, ("GHL API key invalid/expired — regenerate in GHL Settings → "
                          "Integrations → API Keys.")
        return None, f"GHL pipeline fetch failed: HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, f"GHL pipeline fetch failed: {str(e)[:120]}"

    # Restrict the review to a SINGLE pipeline (default: the main sales pipeline).
    # Configurable via GHL_PIPELINE_NAME. Matching ignores case, whitespace and
    # hyphen spacing so small punctuation differences in the name still match.
    _target = _env("GHL_PIPELINE_NAME") or "1: Sales Pipeline- All in One"

    def _norm(s: str) -> str:
        return "".join((s or "").lower().split()).replace("-", "")

    _tn = _norm(_target)
    opps = [o for o in opps if _tn and _tn in _norm(o.get("pipelineName"))]
    _pipe_label = _target.strip()

    if not opps:
        return (f"=== GHL OPEN PIPELINE: {_pipe_label} — LIVE DATA ===\n"
                "No open opportunities in this pipeline.\n"), None

    now = datetime.now(timezone.utc)

    def _age_days(o: dict) -> int:
        raw = o.get("lastStatusChangeAt") or o.get("updatedAt") or o.get("createdAt") or ""
        try:
            return (now - datetime.fromisoformat(raw.replace("Z", "+00:00"))).days
        except (ValueError, TypeError):
            return 0

    by_stage: dict[str, list[dict]] = {}
    for o in opps:
        stage = (o.get("pipelineStageName") or o.get("pipelineStageId") or "Unknown")[:60]
        by_stage.setdefault(stage, []).append(o)

    lines = [f"=== GHL OPEN PIPELINE: {_pipe_label} — LIVE DATA ({len(opps)} open opportunities, "
             f"total ${sum(float(o.get('monetaryValue') or 0) for o in opps):,.0f}) ==="]
    for stage, items in sorted(by_stage.items(), key=lambda kv: -len(kv[1])):
        total = sum(float(o.get("monetaryValue") or 0) for o in items)
        avg_age = sum(_age_days(o) for o in items) / len(items)
        lines.append(f"- {stage}: {len(items)} opportunities | ${total:,.0f} | avg {avg_age:.0f} days since last activity")

    def _opp_name(o: dict) -> str:
        return (o.get("name") or (o.get("contact") or {}).get("name")
                or (o.get("contact") or {}).get("email") or "Unknown")

    stale = sorted((o for o in opps if _age_days(o) >= 10),
                   key=lambda o: -_age_days(o))[:10]
    if stale:
        lines.append("\nTOP STALE OPPORTUNITIES (10+ days no activity):")
        for o in stale:
            lines.append(f"- {_opp_name(o)} | {o.get('pipelineStageName', '?')} | "
                         f"${float(o.get('monetaryValue') or 0):,.0f} | {_age_days(o)} days inactive")

    high_value = sorted(opps, key=lambda o: -float(o.get("monetaryValue") or 0))[:5]
    if high_value and float(high_value[0].get("monetaryValue") or 0) > 0:
        lines.append("\nHIGH-VALUE OPPORTUNITIES (top 5 by value):")
        for o in high_value:
            lines.append(f"- {_opp_name(o)} | {o.get('pipelineStageName', '?')} | "
                         f"${float(o.get('monetaryValue') or 0):,.0f} | {_age_days(o)} days since last activity")
    return "\n".join(lines) + "\n", None


# ── Jobber ────────────────────────────────────────────────────────────────────

def _jobber_today() -> tuple[str | None, str | None]:
    if not _env("JOBBER_ACCESS_TOKEN"):
        return None, "Jobber credentials not configured."
    try:
        from pull_jobber import get_access_token, jobber_query  # scripts/pull_jobber.py
        token = get_access_token(_env("JOBBER_ACCESS_TOKEN"), _env("JOBBER_CLIENT_ID"),
                                 _env("JOBBER_CLIENT_SECRET"))
        today_local = datetime.now(BTL_TZ).date()
        start = datetime(today_local.year, today_local.month, today_local.day,
                         tzinfo=BTL_TZ).astimezone(timezone.utc)
        end = start + timedelta(days=1)
        r = jobber_query(token, f"""{{
            jobs(filter: {{ startAt: {{ after: "{start.isoformat()}", before: "{end.isoformat()}" }} }}) {{
                nodes {{
                    title
                    jobStatus
                    startAt
                    client {{ name }}
                    property {{ address {{ street city }} }}
                    instructions
                }}
                totalCount
            }}
        }}""")
        nodes = r.get("data", {}).get("jobs", {}).get("nodes", [])
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return None, ("Jobber token expired — re-authorize the app at "
                          "developer.getjobber.com and update JOBBER_ACCESS_TOKEN.")
        return None, f"Jobber fetch failed: HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, f"Jobber fetch failed: {str(e)[:120]}"

    if not nodes:
        return f"=== JOBBER JOBS TODAY — LIVE DATA ({today_local}) ===\nNo jobs scheduled today.\n", None
    lines = [f"=== JOBBER JOBS TODAY — LIVE DATA ({today_local}, {len(nodes)} jobs) ==="]
    for n in sorted(nodes, key=lambda x: x.get("startAt") or ""):
        start_at = n.get("startAt") or ""
        try:
            t = datetime.fromisoformat(start_at.replace("Z", "+00:00")).astimezone(BTL_TZ)
            time_label = t.strftime("%I:%M %p").lstrip("0")
        except ValueError:
            time_label = "?"
        addr = ((n.get("property") or {}).get("address") or {})
        lines.append(f"- {time_label} | {(n.get('client') or {}).get('name', '?')} | "
                     f"{n.get('title', '')} | {addr.get('street', '')}, {addr.get('city', '')} | "
                     f"status: {n.get('jobStatus', '?')} | notes: {(n.get('instructions') or 'none')[:150]}")
    return "\n".join(lines) + "\n", None


# ── dispatch ──────────────────────────────────────────────────────────────────

# skill name → list of fetcher callables; each is fn(vault_path) -> (data, note)
def build_skill_context(prompt: str, vault_path: Path,
                        calendar_events: list[dict] | None = None) -> str:
    """Return a live-data context block for the skill named in `prompt`, or ""."""
    parts: list[tuple[str | None, str | None]] = []

    if "kpi-dashboard-digest" in prompt:
        parts.append(_metrics_block(vault_path, ["qbo", "ghl", "jobber", "facebook", "instagram"]))
    elif "billing-status-digest" in prompt:
        parts.append(_qbo_ar_detail())
        parts.append(_metrics_block(vault_path, ["qbo"]))
    elif "pl-narrative" in prompt or "revenue-growth-digest" in prompt:
        parts.append(_qbo_monthly_revenue())
        parts.append(_metrics_block(vault_path, ["qbo"]))
    elif "pipeline-review-summary" in prompt:
        parts.append(_ghl_pipeline())
        parts.append(_metrics_block(vault_path, ["ghl"]))
    elif "crew-schedule-brief" in prompt:
        parts.append(_jobber_today())
        if calendar_events:
            cal = "=== GOOGLE CALENDAR TODAY ===\n" + "\n".join(
                f"- {e.get('time', '')} {e.get('label', '')}" for e in calendar_events) + "\n"
            parts.append((cal, None))
    elif "ad-performance-report" in prompt:
        parts.append(_metrics_block(vault_path, ["facebook", "instagram"]))
        parts.append((None, "Per-campaign ad data (CTR, cost per lead, ROAS) is not connected — "
                            "only follower/reach metrics are available. State this limitation "
                            "in the report instead of inventing campaign numbers."))
    else:
        return ""

    data_parts = [d for d, _ in parts if d]
    notes = [n for _, n in parts if n]
    now_local = datetime.now(BTL_TZ)
    sections = [f"=== TODAY ===\n{now_local.strftime('%A, %B %d, %Y')} (America/Chicago)\n"]
    if data_parts:
        sections.append("\n".join(data_parts))
    if notes:
        sections.append("=== FETCH STATUS ===\n" + "\n".join(notes))
    if len(sections) == 1:
        sections.append("=== FETCH STATUS ===\nNo live data sources returned data.")
    return "\n\n".join(sections).strip()
