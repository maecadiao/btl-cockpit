"""Background metrics refresh for cloud deployments (Railway).

Locally, a separate Node runner (my-cockpit/runner.js) refreshes metrics.csv
in the real vault on a schedule. That runner only exists on the office PC, so
a cloud deployment has no way to keep its data current on its own — this
module is that missing piece for Railway.

Only runs when the real local vault isn't present (i.e. we're not on the
office PC) — see config.VAULT_PATH. Discovers every scripts/pull_*.py and
runs it as a subprocess, writing into VAULT_PATH via AGENTIC_OS_VAULT, the
same env var scripts/_common.py already honors.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REFRESH_INTERVAL_SEC = 4 * 60 * 60  # matches the local runner's cadence
PER_SCRIPT_TIMEOUT_SEC = 90

_PROJECT_ROOT = Path(__file__).parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"


def _run_one(script_path: Path, vault_path: Path) -> None:
    env = os.environ.copy()
    env["AGENTIC_OS_VAULT"] = str(vault_path)
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(_SCRIPTS_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=PER_SCRIPT_TIMEOUT_SEC,
        )
        print(f"[cloud_scheduler] {script_path.name}: {result.stdout.strip() or result.stderr.strip()}")
    except Exception as exc:  # noqa: BLE001 — never let one bad source kill the loop
        print(f"[cloud_scheduler] {script_path.name} failed: {exc}")


def _run_all(vault_path: Path) -> None:
    for script_path in sorted(_SCRIPTS_DIR.glob("pull_*.py")):
        _run_one(script_path, vault_path)


def _loop(vault_path: Path) -> None:
    while True:
        _run_all(vault_path)
        time.sleep(REFRESH_INTERVAL_SEC)


def _persist_to_volume(vault_path: Path) -> None:
    """Symlink metrics + run history into the Railway volume so they survive
    redeploys. Without this, every deploy wipes metrics.csv (so metric-card
    deltas never accumulate) and the team's run history disappears."""
    data_vol = Path("/data")
    if not data_vol.is_dir():
        return
    for sub in ("metrics", "runs"):
        durable = data_vol / sub
        durable.mkdir(parents=True, exist_ok=True)
        ephemeral = vault_path / "system" / sub
        try:
            if ephemeral.is_symlink():
                continue
            if ephemeral.is_dir():
                # first boot with the volume: keep any files the repo shipped
                for f in ephemeral.rglob("*"):
                    if f.is_file():
                        dest = durable / f.relative_to(ephemeral)
                        if not dest.exists():
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            dest.write_bytes(f.read_bytes())
                shutil.rmtree(ephemeral)
            ephemeral.parent.mkdir(parents=True, exist_ok=True)
            ephemeral.symlink_to(durable, target_is_directory=True)
            print(f"[cloud_scheduler] {ephemeral} -> {durable}")
        except OSError as exc:
            print(f"[cloud_scheduler] persist link failed for {sub}: {exc}")


def start_cloud_scheduler(vault_path: Path, local_vault_marker: Path) -> None:
    """Start the background refresh loop, unless running on the office PC."""
    if local_vault_marker.exists():
        return  # local machine already has its own runner for this
    _persist_to_volume(vault_path)
    thread = threading.Thread(target=_loop, args=(vault_path,), daemon=True)
    thread.start()
