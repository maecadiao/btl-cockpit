"""Shared helpers for metric-pull source scripts.

Every pull_*.py imports from here so CSV/snapshot writes stay consistent
with the cockpit's reader.

Vault path resolution order:
  1. AGENTIC_OS_VAULT environment variable
  2. AGENTIC_OS_VAULT entry inside ~/.claude/.env
  3. fallback: ~/the-vault
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ENV_PATH = Path.home() / ".claude" / ".env"
CSV_HEADER = ["timestamp", "source", "metric", "value", "status", "error"]


def load_env_file(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _resolve_vault_root() -> Path:
    if v := os.environ.get("AGENTIC_OS_VAULT"):
        return Path(v)
    if v := load_env_file().get("AGENTIC_OS_VAULT"):
        return Path(v)
    return Path.home() / "the-vault"


VAULT_ROOT = _resolve_vault_root()
VAULT_METRICS = VAULT_ROOT / "system" / "metrics"
CSV_PATH = VAULT_METRICS / "metrics.csv"
SNAPSHOT_PATH = VAULT_METRICS / "last-pull.json"


def env(name: str) -> str | None:
    """Read an env var, falling back to ~/.claude/.env."""
    if val := os.environ.get(name):
        return val
    return load_env_file().get(name)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_csv() -> None:
    VAULT_METRICS.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(CSV_HEADER)


def append_row(
    ts: str, source: str, metric: str, value: float, status: str, error: str
) -> None:
    """Append one row to metrics.csv. Append-only — never rewrite the file."""
    ensure_csv()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow([ts, source, metric, value, status, error])


def write_snapshot(source: str, status: str, error: str = "") -> None:
    """Update last-pull.json with the latest status for `source`.

    Cockpit reads this file to render per-source status dots (ok / error /
    stale). Atomic merge — preserves other sources' entries.
    """
    snapshot: dict = {}
    if SNAPSHOT_PATH.exists():
        try:
            snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            snapshot = {}
    snapshot[source] = {"ts": now_iso(), "status": status, "error": error}
    VAULT_METRICS.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8"
    )


def last_known_value(source: str, metric: str) -> float:
    """Find the most recent non-zero CSV value for (source, metric).

    Useful as a fallback when a scrape fails: emit last known value with
    status='stale' so the cockpit doesn't render zero.
    """
    if not CSV_PATH.exists():
        return 0.0
    last = 0.0
    with CSV_PATH.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("source") == source and row.get("metric") == metric:
                try:
                    v = float(row.get("value", "0"))
                    if v > 0:
                        last = v
                except ValueError:
                    continue
    return last
