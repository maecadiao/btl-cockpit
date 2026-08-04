"""pull_ghl_pipeline.py — sales-pipeline snapshot for the GHL cockpit tab.

Writes system/metrics/ghl-pipeline.json, restricted to a SINGLE pipeline
(default: "1: Sales Pipeline- All in One", configurable via GHL_PIPELINE_NAME):

  {
    "updated": iso,
    "pipeline": "1: Sales Pipeline- All in One",
    "open_count": 40,
    "open_value": 205783.0,
    "new_leads_7d": 3,
    "by_stage": [{stage, count, value, avg_age}, ...],   # sorted by value desc
    "stale":     [{name, stage, value, days}, ...],       # 10+ days, top 8
    "high_value":[{name, stage, value, days}, ...],       # top 5 by value
    "error": null
  }

The cockpit reads this so the GHL tab renders instantly without a live API call.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import VAULT_METRICS, env, now_iso, write_snapshot

OUT_PATH = VAULT_METRICS / "ghl-pipeline.json"
DEFAULT_PIPELINE = "1: Sales Pipeline- All in One"


def _norm(s: str) -> str:
    return "".join((s or "").lower().split()).replace("-", "")


def _age_days(o: dict, now: datetime) -> int:
    raw = o.get("lastStatusChangeAt") or o.get("updatedAt") or o.get("createdAt") or ""
    try:
        return (now - datetime.fromisoformat(raw.replace("Z", "+00:00"))).days
    except (ValueError, TypeError):
        return 0


def _created_days(o: dict, now: datetime) -> int:
    raw = o.get("createdAt") or ""
    try:
        return (now - datetime.fromisoformat(raw.replace("Z", "+00:00"))).days
    except (ValueError, TypeError):
        return 9999


def _name(o: dict) -> str:
    return (o.get("name") or (o.get("contact") or {}).get("name")
            or (o.get("contact") or {}).get("email") or "Unknown")


def main() -> None:
    target = env("GHL_PIPELINE_NAME") or DEFAULT_PIPELINE
    out: dict = {"updated": now_iso(), "pipeline": target.strip(), "error": None}

    if not env("GHL_API_KEY"):
        out["error"] = "GoHighLevel: credentials not configured"
        _write(out, "error")
        return

    try:
        import pull_ghl
        pull_ghl.HEADERS["Authorization"] = f"Bearer {env('GHL_API_KEY')}"
        opps = pull_ghl.fetch_open_opportunities()
    except Exception as e:  # noqa: BLE001
        out["error"] = f"GoHighLevel: {str(e)[:120]}"
        _write(out, "error")
        return

    tn = _norm(target)
    opps = [o for o in opps if tn and tn in _norm(o.get("pipelineName"))]

    now = datetime.now(timezone.utc)

    def _val(o: dict) -> float:
        return float(o.get("monetaryValue") or 0)

    by_stage: dict[str, list[dict]] = {}
    for o in opps:
        stage = (o.get("pipelineStageName") or o.get("pipelineStageId") or "Unknown").strip()[:60]
        by_stage.setdefault(stage, []).append(o)

    stages = []
    for stage, items in by_stage.items():
        stages.append({
            "stage": stage,
            "count": len(items),
            "value": round(sum(_val(o) for o in items), 2),
            "avg_age": round(sum(_age_days(o, now) for o in items) / len(items)),
        })
    stages.sort(key=lambda s: -s["value"] if s["value"] else -s["count"] / 1e6)

    stale = sorted((o for o in opps if _age_days(o, now) >= 10),
                   key=lambda o: -_age_days(o, now))[:8]
    high_value = sorted(opps, key=lambda o: -_val(o))[:5]

    out.update({
        "open_count": len(opps),
        "open_value": round(sum(_val(o) for o in opps), 2),
        "new_leads_7d": sum(1 for o in opps if _created_days(o, now) <= 7),
        "by_stage": stages,
        "stale": [{"name": _name(o), "stage": o.get("pipelineStageName", "?"),
                   "value": round(_val(o), 2), "days": _age_days(o, now)} for o in stale],
        "high_value": [{"name": _name(o), "stage": o.get("pipelineStageName", "?"),
                        "value": round(_val(o), 2), "days": _age_days(o, now)}
                       for o in high_value if _val(o) > 0],
    })
    _write(out, "ok")
    print(f"[ghl_pipeline] {out['open_count']} open · ${out['open_value']:,.0f} · "
          f"{len(stages)} stages")


def _write(out: dict, status: str) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    write_snapshot("ghl_pipeline", status, out.get("error") or "")


if __name__ == "__main__":
    main()
