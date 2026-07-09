"""Overview-page widgets ported from the original Obsidian cockpit plugin
(my-cockpit): date-range bar, metric cards with range deltas + freshness dots,
and the daily task list. Layout reference: the user's Agentic OS screenshot.

Task store matches the plugin exactly ({date, tasks:[{id,text,done}]},
resetting each day) so the vault file stays interchangeable. On Railway the
vault is wiped every deploy, so tasks live on the persistent /data volume.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

# ── Daily tasks ───────────────────────────────────────────────────────────────

def _tasks_path(vault_path: Path) -> Path:
    data_vol = Path("/data")
    if data_vol.is_dir():
        return data_vol / "daily-tasks.json"
    return vault_path / "system" / "metrics" / "daily-tasks.json"


def _read_tasks(vault_path: Path) -> dict:
    today = date.today().isoformat()
    try:
        store = json.loads(_tasks_path(vault_path).read_text(encoding="utf-8"))
        if store.get("date") != today:            # new day — reset, like the plugin
            return {"date": today, "tasks": []}
        return store
    except (OSError, json.JSONDecodeError):
        return {"date": today, "tasks": []}


def _write_tasks(vault_path: Path, store: dict) -> None:
    path = _tasks_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")


def render_tasks_card(vault_path: Path) -> None:
    """DAILY TASKS card: checklist + add-input, persisted across the team."""
    store = _read_tasks(vault_path)
    tasks = store["tasks"]
    done_n = sum(1 for t in tasks if t.get("done"))

    st.markdown(
        f'<div class="btl-panel-head"><span>Daily tasks</span>'
        f'<span class="btl-panel-meta">{done_n}/{len(tasks)}</span></div>',
        unsafe_allow_html=True,
    )
    if not tasks:
        st.markdown('<div class="btl-tasks-empty">&gt; no tasks yet</div>',
                    unsafe_allow_html=True)
    changed = False
    for t in tasks:
        checked = st.checkbox(
            t.get("text", ""), value=bool(t.get("done")),
            key=f"btl_task_{store['date']}_{t['id']}",
        )
        if checked != bool(t.get("done")):
            t["done"] = checked
            changed = True
    if changed:
        _write_tasks(vault_path, store)

    with st.form(key="btl_task_form", clear_on_submit=True, border=False):
        c1, c2 = st.columns([5, 1], gap="small")
        with c1:
            new_text = st.text_input(
                "new task", key="btl_task_new", placeholder="new task…",
                label_visibility="collapsed",
            )
        with c2:
            submitted = st.form_submit_button("＋", use_container_width=True)
        if submitted and new_text.strip():
            next_id = max((t["id"] for t in tasks), default=0) + 1
            tasks.append({"id": next_id, "text": new_text.strip(), "done": False})
            _write_tasks(vault_path, store)
            st.rerun()


# ── Date-range bar ────────────────────────────────────────────────────────────

_RANGES = [("today", "Today"), ("7d", "7 D"), ("30d", "30 D"), ("90d", "90 D"), ("all", "All")]


def render_range_bar() -> tuple[datetime | None, datetime | None]:
    """RANGE: Today/7D/30D/90D/All pills + custom from/to dates. Returns (start, end)."""
    if "btl_range" not in st.session_state:
        st.session_state.btl_range = "30d"

    cols = st.columns([0.9, 1, 0.8, 0.8, 0.8, 0.8, 2.4, 2.4], gap="small")
    with cols[0]:
        st.markdown('<div class="btl-range-label btl-range-marker">Range</div>',
                    unsafe_allow_html=True)
    for i, (key, label) in enumerate(_RANGES):
        with cols[i + 1]:
            if st.button(
                label, key=f"btl_range_{key}",
                type="primary" if st.session_state.btl_range == key else "secondary",
                use_container_width=True,
            ):
                st.session_state.btl_range = key
                st.session_state.btl_range_from = None
                st.rerun()
    with cols[6]:
        d_from = st.date_input("from", value=None, key="btl_range_from",
                               label_visibility="collapsed", format="MM/DD/YYYY")
    with cols[7]:
        d_to = st.date_input("to", value=None, key="btl_range_to",
                             label_visibility="collapsed", format="MM/DD/YYYY")

    now = datetime.now(timezone.utc)
    if d_from:
        start = datetime(d_from.year, d_from.month, d_from.day, tzinfo=timezone.utc)
        end = (datetime(d_to.year, d_to.month, d_to.day, 23, 59, 59, tzinfo=timezone.utc)
               if d_to else None)
        return start, end, f"since {d_from.strftime('%b %d')}"
    sel = st.session_state.btl_range
    if sel == "today":
        return (now.replace(hour=0, minute=0, second=0, microsecond=0), None,
                "since this morning")
    if sel == "all":
        return None, None, "all time"
    days = {"7d": 7, "30d": 30, "90d": 90}[sel]
    return now - timedelta(days=days), None, f"vs {days} days ago"


# ── Metric cards ──────────────────────────────────────────────────────────────

# Plain-English labels. "snapshot" = a live "right now" value (range can't change
# it); "range" = a total summed over the selected window, from daily-series.json.
OVERVIEW_CARDS = [
    {"mode": "snapshot", "source": "qbo", "metric": "ar_balance",
     "label": "Money Owed to Us", "format": "currency"},
    {"mode": "range", "series": "revenue",  "label": "Revenue",   "format": "currency"},
    {"mode": "range", "series": "spending", "label": "Spending",  "format": "currency"},
    {"mode": "range", "series": "leads",    "label": "New Leads", "format": "integer"},
    {"mode": "range", "series": "jobs",     "label": "Jobs",      "format": "integer"},
]


def _fmt_value(v: float, fmt: str) -> str:
    if fmt == "currency":
        return f"${v:,.0f}"
    if fmt == "integer":
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def metric_snapshots(vault_path: Path, cards: list[dict],
                     start: datetime | None, end: datetime | None) -> dict:
    """Per (source,metric): latest value/ts + %delta vs the range baseline."""
    wanted = {(c["source"], c["metric"]) for c in cards}
    series: dict[tuple, list[tuple[datetime, float]]] = {k: [] for k in wanted}
    metrics_csv = vault_path / "system" / "metrics" / "metrics.csv"
    try:
        with metrics_csv.open("r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = (row.get("source", ""), row.get("metric", ""))
                if key in wanted and row.get("status") in ("ok", "stale"):
                    ts = _parse_ts(row.get("timestamp", ""))
                    if ts:
                        try:
                            series[key].append((ts, float(row.get("value", "0"))))
                        except ValueError:
                            pass
    except OSError:
        pass

    status: dict = {}
    try:
        status = json.loads(
            (vault_path / "system" / "metrics" / "last-pull.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    out: dict = {"__history_start__": None}
    all_ts = [p[0] for pts in series.values() for p in pts]
    if all_ts:
        out["__history_start__"] = min(all_ts)
    now = datetime.now(timezone.utc)
    for key, points in series.items():
        if not points:
            out[key] = None
            continue
        points.sort(key=lambda p: p[0])
        in_range = [p for p in points if (end is None or p[0] <= end)]
        latest_ts, latest_v = in_range[-1] if in_range else points[-1]
        baseline = None
        if start:
            before = [p for p in points if p[0] < start]
            # Only a point that predates the range start is a real comparison;
            # falling back to the earliest in-range point fakes a 0.0% delta.
            baseline = before[-1][1] if before else None
        elif len(points) > 1:
            baseline = points[0][1]   # "all time": compare against first record
        delta_pct = (
            (latest_v - baseline) / abs(baseline) * 100
            if baseline not in (None, 0) else None
        )
        src_status = (status.get(key[0]) or {}).get("status", "")
        age_h = (now - latest_ts).total_seconds() / 3600
        if src_status == "error":
            dot = "error"
        elif age_h > 48:
            dot = "stale"
        elif src_status in ("ok", ""):
            dot = "ok"
        else:
            dot = "stale"
        out[key] = {"value": latest_v, "ts": latest_ts, "delta_pct": delta_pct, "dot": dot}
    return out


def _read_daily_series(vault_path: Path) -> dict:
    try:
        return json.loads(
            (vault_path / "system" / "metrics" / "daily-series.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _range_total(daily: dict, series_name: str,
                 start: datetime | None, end: datetime | None):
    """Sum a daily series over [start, end], plus the immediately-preceding
    equal-length window for a %delta. Returns (total, delta_pct|None, fresh)."""
    days = daily.get("days", [])
    values = daily.get("series", {}).get(series_name)
    if not days or values is None:
        return None, None, False
    day_to_val = dict(zip(days, values))
    end_d = (end.date() if end else date.today())
    start_d = (start.date() if start else date.fromisoformat(days[0]))

    win = [d for d in days if start_d <= date.fromisoformat(d) <= end_d]
    total = sum(day_to_val[d] for d in win)

    delta_pct = None
    if win:
        span = (date.fromisoformat(win[-1]) - date.fromisoformat(win[0])).days + 1
        prev_end = date.fromisoformat(win[0]) - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        prev = [d for d in days
                if prev_start <= date.fromisoformat(d) <= prev_end]
        if prev:
            prev_total = sum(day_to_val[d] for d in prev)
            if prev_total:
                delta_pct = (total - prev_total) / abs(prev_total) * 100
    fresh = series_name not in daily.get("notes", {})
    return total, delta_pct, fresh


def compute_overview(vault_path: Path, cards: list[dict],
                     start: datetime | None, end: datetime | None) -> list[dict]:
    """Resolve each card to {label, value, format, delta_pct, dot, ok} for rendering."""
    snap_cards = [c for c in cards if c.get("mode") == "snapshot"]
    snaps = metric_snapshots(vault_path, snap_cards, start, end) if snap_cards else {}
    daily = _read_daily_series(vault_path)

    out = []
    for c in cards:
        if c.get("mode") == "range":
            total, dp, fresh = _range_total(daily, c["series"], start, end)
            out.append({
                "label": c["label"], "format": c["format"],
                "value": total, "delta_pct": dp,
                "dot": ("ok" if fresh else "stale") if total is not None else "none",
                "ok": total is not None,
            })
        else:
            s = snaps.get((c["source"], c["metric"]))
            out.append({
                "label": c["label"], "format": c["format"],
                "value": (s or {}).get("value"),
                "delta_pct": None,  # AR is a live balance — no window comparison
                "dot": (s or {}).get("dot", "none"),
                "ok": s is not None,
                "snapshot": True,
            })
    return out


def render_metric_cards(computed: list[dict], range_label: str = "") -> None:
    tiles = []
    for c in computed:
        if not c["ok"] or c["value"] is None:
            delta = ('<span class="btl-mc-delta flat">connect to see</span>')
            tiles.append(
                f'<div class="btl-mc"><div class="btl-mc-head">'
                f'<span class="btl-mc-label">{c["label"]}</span>'
                f'<span class="btl-mc-dot none"></span></div>'
                f'<div class="btl-mc-value">—</div>{delta}</div>'
            )
            continue
        if c.get("snapshot"):
            delta_html = '<span class="btl-mc-delta flat">as of now</span>'
        else:
            dp = c["delta_pct"]
            if dp is None:
                delta_html = f'<span class="btl-mc-delta flat">{range_label}</span>'
            elif abs(dp) < 0.05:
                delta_html = f'<span class="btl-mc-delta flat">·&nbsp;flat vs prior period</span>'
            elif dp > 0:
                delta_html = f'<span class="btl-mc-delta up">▲&nbsp;{dp:.0f}% vs prior period</span>'
            else:
                delta_html = f'<span class="btl-mc-delta down">▼&nbsp;{abs(dp):.0f}% vs prior period</span>'
        tiles.append(
            f'<div class="btl-mc"><div class="btl-mc-head">'
            f'<span class="btl-mc-label">{c["label"]}</span>'
            f'<span class="btl-mc-dot {c["dot"]}"></span></div>'
            f'<div class="btl-mc-value">{_fmt_value(c["value"], c["format"])}</div>'
            f'{delta_html}</div>'
        )
    st.markdown(f'<div class="btl-mc-grid">{"".join(tiles)}</div>', unsafe_allow_html=True)
