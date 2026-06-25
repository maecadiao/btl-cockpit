"""
Be The Light Decor — Agentic OS Dashboard config.
Outdoor landscape lighting · Covington, Louisiana.

Cloud-safe: DEMO_MODE = True, paths are relative so this runs on
Streamlit Community Cloud (Linux) and locally on Windows.
"""

import os
import shutil
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

# Local Windows path when running on the office machine.
# Falls back to demo-vault on Railway/cloud.
_local_vault = Path(r"C:\Users\labor\the-vault")
_project_root = Path(__file__).parent
VAULT_PATH = _local_vault if _local_vault.exists() else _project_root / "demo-vault"
VAULT_NAME = "BTL Cockpit"

# Skill runner — local enqueue bridge on Windows, system claude on Railway.
_local_cli_bat = Path(r"C:\Users\labor\projects\my-cockpit\runner\enqueue.bat")
_local_cli_py  = Path(r"C:\Users\labor\projects\my-cockpit\runner\enqueue.py")
_system_claude = shutil.which("claude")  # installed via npm on Railway
CLAUDE_CLI = (
    _local_cli_bat if _local_cli_bat.exists() else
    _local_cli_py  if _local_cli_py.exists()  else
    Path(_system_claude) if _system_claude else
    Path("/usr/bin/true")
)

DAILY_NOTES_DIR  = VAULT_PATH / "daily-notes"
RUNS_DIR         = VAULT_PATH / "system" / "runs"
DRAFTS_AWAITING  = VAULT_PATH / "system" / "runs"   # reuse runs dir
QUEUE_DIR        = VAULT_PATH / "system" / "queue"
METRICS_CSV      = VAULT_PATH / "system" / "metrics" / "metrics.csv"

# ── Plan ──────────────────────────────────────────────────────────────────────

CLAUDE_PLAN = "max"
PLAN_ROUTINE_CAPS = {"pro": 5, "max": 15, "team": 25, "enterprise": 25}

LIMITS = {
    "five_hour_tokens":  5_000_000,
    "weekly_tokens":    60_000_000,
    "daily_routine_runs": PLAN_ROUTINE_CAPS.get(CLAUDE_PLAN, 15),
}

RUN_TIMEOUT_SEC  = 120
PERMISSION_MODE  = "bypassPermissions"
SESSION_META_DIR = Path.home() / ".claude" / "usage-data" / "session-meta"

# ── Layout ────────────────────────────────────────────────────────────────────

LAYOUT_VERSION = "v2"

ENABLED_CARDS = {
    "latest_upload":  False,   # YouTube upload card — not used
    "audience_row":   True,    # Facebook + Instagram cards
    "tokenburn":      True,    # overview usage marquee
    "yt_week_review": False,   # YouTube week review — not used
    "morning_brief":  True,    # shows skill runs / recent activity
    "schedule":       True,    # jobs today schedule
    "daily_drivers":  False,
    "throughput":     True,    # 30-day agent-runs chart
}

# ── Demo mode ─────────────────────────────────────────────────────────────────

DEMO_MODE = False  # live data from metrics.csv

DEMO_USAGE = {
    "five_hour": {"input": 820_000, "output": 460_000, "total": 1_280_000, "sessions": 3},
    "weekly":    {"input": 9_400_000, "output": 5_600_000, "total": 15_000_000, "sessions": 22},
    "today":     {
        "input": 2_100_000, "output": 1_300_000, "total": 3_400_000,
        "sessions": 5, "routines": 4, "cost": 4.20, "runs": 7
    },
}

# BTL social metrics (demo values)
DEMO_AUDIENCE = {
    "facebook_followers": {"value": 1_847, "ts": "2026-06-08T12:00:00Z", "status": "mock"},
    "facebook_likes_avg": {"value": 42,    "ts": "2026-06-08T12:00:00Z", "status": "mock"},
    "instagram_followers":{"value": 2_103, "ts": "2026-06-08T12:00:00Z", "status": "mock"},
    "instagram_reach_avg":{"value": 318,   "ts": "2026-06-08T12:00:00Z", "status": "mock"},
    # QBO overview
    "revenue_mtd":        {"value": 24_800, "ts": "2026-06-08T12:00:00Z", "status": "mock"},
    "active_leads":       {"value": 18,     "ts": "2026-06-08T12:00:00Z", "status": "mock"},
    "jobs_today":         {"value": 3,      "ts": "2026-06-08T12:00:00Z", "status": "mock"},
    "open_invoices":      {"value": 7,      "ts": "2026-06-08T12:00:00Z", "status": "mock"},
}

DEMO_LATEST_VIDEO = {
    "title": "Holiday Lighting Install — Covington Estate",
    "video_id": "",
    "url": "",
    "views": 0,
    "likes": 0,
    "comments": 0,
    "published_at": "2026-06-01T12:00:00Z",
    "ts": "2026-06-08T12:00:00Z",
    "status": "mock",
}

# ── Skills ────────────────────────────────────────────────────────────────────

SKILL_CATEGORY_ORDER = ["marketing", "sales", "admin", "production", "executive"]

_AUTO = (
    "Act autonomously. Do not ask for confirmation. "
    "Do not use AskUserQuestion. "
)

SKILLS = [
    # ─── MARKETING ────────────────────────────────────────────────────────
    {
        "label": "Caption Writer",
        "prompt_template": _AUTO + "Run the /caption-writer skill for: {input}",
        "description": "Write a social caption for a post or project",
        "category": "marketing",
        "input_placeholder": "describe the post / job / photo",
    },
    {
        "label": "Content Ideas",
        "prompt_template": _AUTO + "Run the /content-ideas skill",
        "description": "Generate content ideas for BTL's social channels",
        "category": "marketing",
    },
    {
        "label": "Ad Performance",
        "prompt_template": _AUTO + "Run the /ad-performance-report skill",
        "description": "Pull and summarize recent ad performance",
        "category": "marketing",
    },
    {
        "label": "Inbox Digest",
        "prompt_template": _AUTO + "Run the /inbox-monitor-digest skill",
        "description": "Scan inbox and summarize messages needing action",
        "category": "marketing",
    },
    {
        "label": "Inbox Reply Draft",
        "prompt_template": _AUTO + "Run the /inbox-reply-draft skill for: {input}",
        "description": "Draft a reply for an inbox message",
        "category": "marketing",
        "input_placeholder": "paste or describe the message to reply to",
    },

    # ─── SALES ────────────────────────────────────────────────────────────
    {
        "label": "Pipeline Review",
        "prompt_template": _AUTO + "Run the /pipeline-review-summary skill",
        "description": "Full GHL pipeline status and priority actions",
        "category": "sales",
    },
    {
        "label": "Quote Follow-up",
        "prompt_template": _AUTO + "Run the /quote-followup-email skill for: {input}",
        "description": "Write a follow-up email on a sent quote",
        "category": "sales",
        "input_placeholder": "client name + job + how long since quote sent",
    },
    {
        "label": "Lead Qualifier",
        "prompt_template": _AUTO + "Run the /lead-qualifier skill for: {input}",
        "description": "Score and qualify an inbound lead",
        "category": "sales",
        "input_placeholder": "paste lead info or GHL contact details",
    },
    {
        "label": "Write Proposal",
        "prompt_template": _AUTO + "Run the /estimate-proposal-writer skill for: {input}",
        "description": "Generate a professional project proposal",
        "category": "sales",
        "input_placeholder": "property type, scope, location, budget if known",
    },
    {
        "label": "Sales Call Prep",
        "prompt_template": _AUTO + "Run the /sales-call-prep skill for: {input}",
        "description": "Pre-call briefing for a consultation or follow-up",
        "category": "sales",
        "input_placeholder": "client name + what they want + where they are in process",
    },

    # ─── ADMIN ────────────────────────────────────────────────────────────
    {
        "label": "Job Posting",
        "prompt_template": _AUTO + "Run the /job-posting-writer skill for: {input}",
        "description": "Write a job listing for a BTL role",
        "category": "admin",
        "input_placeholder": "role title + key responsibilities",
    },
    {
        "label": "Onboarding Doc",
        "prompt_template": _AUTO + "Run the /onboarding-doc-generator skill for: {input}",
        "description": "Create an onboarding guide for a new team member",
        "category": "admin",
        "input_placeholder": "role being onboarded",
    },
    {
        "label": "Write SOP",
        "prompt_template": _AUTO + "Run the /sop-writer skill for: {input}",
        "description": "Write a standard operating procedure",
        "category": "admin",
        "input_placeholder": "process name + steps if known",
    },
    {
        "label": "Lead Nurture Email",
        "prompt_template": _AUTO + "Run the /lead-nurture-email skill for: {input}",
        "description": "Write a nurture email for a cold or warm lead",
        "category": "admin",
        "input_placeholder": "lead name + interest + last interaction",
    },
    {
        "label": "Billing Digest",
        "prompt_template": _AUTO + "Run the /billing-status-digest skill",
        "description": "Summarize open invoices and AR status from QBO",
        "category": "admin",
    },
    {
        "label": "Meeting Notes",
        "prompt_template": _AUTO + "Run the /meeting-notes-summary skill for: {input}",
        "description": "Turn raw notes into a structured meeting summary",
        "category": "admin",
        "input_placeholder": "paste raw notes or transcript",
    },

    # ─── PRODUCTION ───────────────────────────────────────────────────────
    {
        "label": "Crew Brief",
        "prompt_template": _AUTO + "Run the /crew-schedule-brief skill",
        "description": "Daily crew briefing — jobs, locations, assignments",
        "category": "production",
    },

    # ─── EXECUTIVE ────────────────────────────────────────────────────────
    {
        "label": "P&L Narrative",
        "prompt_template": _AUTO + "Run the /pl-narrative skill",
        "description": "Plain-English P&L analysis from QuickBooks data",
        "category": "executive",
    },
    {
        "label": "KPI Digest",
        "prompt_template": _AUTO + "Run the /kpi-dashboard-digest skill",
        "description": "Weekly KPI scorecard with traffic-light status",
        "category": "executive",
    },
    {
        "label": "Revenue Growth",
        "prompt_template": _AUTO + "Run the /revenue-growth-digest skill",
        "description": "Multi-period revenue trend + opportunities + risks",
        "category": "executive",
    },
]
