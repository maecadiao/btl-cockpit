"""
Agentic OS Dashboard — user config template.

STEP 1: Copy this file to `config.py` in the same folder.
STEP 2: Edit the paths, plan, and SKILLS list below to match your setup.
STEP 3: `streamlit run app.py`

`config.py` is gitignored — your edits stay local.
"""

from pathlib import Path

# ───────────────────────────────────────────────────────────────
# PATHS — edit these to point at your own folders
# ───────────────────────────────────────────────────────────────

# Where Claude Code should run (its working directory). Usually your
# Obsidian vault, a project folder, or wherever your skills expect to operate.
# Windows example: Path(r"C:\Users\YourName\projects\my-vault")
# Mac / Linux:     Path("/Users/yourname/projects/my-vault")
VAULT_PATH = Path(r"C:\Users\YourName\your-folder")

# Display name for the folder (shown in the header).
VAULT_NAME = "my-folder"

# Full path to the `claude` executable.
# Find it with:
#   Windows:  where claude
#   Mac/Linux: which claude
# Windows example: Path(r"C:\Users\YourName\.local\bin\claude.exe")
# Mac / Linux:     Path("/usr/local/bin/claude")
CLAUDE_CLI = Path(r"C:\Users\YourName\.local\bin\claude.exe")

# Where skill runs get logged. Defaults below assume VAULT_PATH has these
# subfolders — change if you organize differently.
DAILY_NOTES_DIR = VAULT_PATH / "daily-notes"
RUNS_DIR = VAULT_PATH / "dashboard-runs"
DRAFTS_AWAITING = VAULT_PATH / "drafts" / "awaiting"

# ───────────────────────────────────────────────────────────────
# YOUR CLAUDE PLAN — sets the daily routine cap per Anthropic policy
# ───────────────────────────────────────────────────────────────
#   "pro"        → 5 routine runs / day
#   "max"        → 15 routine runs / day
#   "team"       → 25 routine runs / day
#   "enterprise" → 25 routine runs / day
CLAUDE_PLAN = "pro"

PLAN_ROUTINE_CAPS = {"pro": 5, "max": 15, "team": 25, "enterprise": 25}

# ───────────────────────────────────────────────────────────────
# USAGE CEILINGS — rough approximations only
# Claude Code's /usage is the ground truth. These are local guesses the
# dashboard uses to paint the gauges. Calibrate against what /usage says
# 100% actually means for your plan + usage pattern.
# ───────────────────────────────────────────────────────────────
LIMITS = {
    "five_hour_tokens": 5_000_000,   # rough 5-hour rolling ceiling
    "weekly_tokens":    60_000_000,  # rough 7-day ceiling
    "daily_routine_runs": PLAN_ROUTINE_CAPS.get(CLAUDE_PLAN, 5),
}

# How long to let a skill run before killing it (seconds).
RUN_TIMEOUT_SEC = 900

# Claude Code permission mode. Options:
#   "bypassPermissions" → no prompts, Claude runs freely (convenient, riskier)
#   "default"           → Claude prompts for each tool use (safer, slower)
PERMISSION_MODE = "bypassPermissions"

# Path to Claude Code's per-session usage data. /usage reads from here too.
# You should NOT need to change this unless Claude Code moved its data dir.
SESSION_META_DIR = Path.home() / ".claude" / "usage-data" / "session-meta"


# ───────────────────────────────────────────────────────────────
# SKILLS — the buttons on the dashboard
# ───────────────────────────────────────────────────────────────
#
# Each entry becomes a clickable button that runs `claude -p "<prompt>"`.
#
# Fields per skill:
#   label             — button text
#   prompt_template   — the prompt sent to Claude. Use `{input}` as a
#                       placeholder for any user-typed input; omit it for
#                       no-input skills.
#   description       — subtitle shown under the label
#   category          — "daily" or "content" (groups buttons visually)
#   input_placeholder — (optional) hint text for input box, only if the
#                       prompt_template contains `{input}`
#
# Pattern to keep things autonomous (no mid-run prompts):
#   "Act autonomously. Do not ask for confirmation. Do not use
#    AskUserQuestion. Run the /your-skill skill"
#
# Replace the examples below with your own Claude Code skills (or /commands).
# Delete any you don't use.
# ───────────────────────────────────────────────────────────────

# ───────────────────────────────────────────────────────────────
# LAYOUT — v1 = legacy single column, v2 = tabbed cockpit (overview/audience/research)
# ───────────────────────────────────────────────────────────────
LAYOUT_VERSION = "v2"

# Per-card toggles. Hide cards by flipping False; useful when forking.
ENABLED_CARDS = {
    "latest_upload":  True,
    "audience_row":   True,
    "tokenburn":      True,   # overview marquee
    "yt_week_review": True,   # audience marquee
    "morning_brief":  True,   # research marquee
    "schedule":       True,   # overview lower-left
    "daily_drivers":  True,   # overview lower-right
}

# ───────────────────────────────────────────────────────────────
# DEMO MODE — when True, all readers fall back to canned data
# so a deployer with an empty vault sees a populated dashboard.
# Set in config.py (gitignored), not here.
# ───────────────────────────────────────────────────────────────
DEMO_MODE = False

DEMO_USAGE = {
    "five_hour": {"input": 1_820_000, "output": 1_300_000, "total": 3_120_000, "sessions": 7},
    "weekly":    {"input": 22_400_000, "output": 18_600_000, "total": 41_000_000, "sessions": 43},
    "today":     {"input": 6_500_000, "output": 4_800_000, "total": 11_300_000,
                  "sessions": 12, "routines": 9, "cost": 14.27, "runs": 18},
}

DEMO_AUDIENCE = {
    "youtube_subs":     {"value": 123_000, "ts": "2026-05-13T17:00:00Z", "status": "mock"},
    "youtube_views_28d": {"value": 9_497_973, "ts": "2026-05-13T17:00:00Z", "status": "mock"},
    "instagram_followers": {"value": 1_460, "ts": "2026-05-13T17:00:00Z", "status": "mock"},
    "tiktok_followers":   {"value": 1_103, "ts": "2026-05-13T17:00:00Z", "status": "mock"},
}

DEMO_LATEST_VIDEO = {
    "title": "claude code vs codex is not a question",
    "video_id": "u_xyjZq-xDU",
    "url": "https://youtu.be/u_xyjZq-xDU",
    "views": 1_571,
    "likes": 51,
    "comments": 1,
    "published_at": "2026-05-13T12:31:07Z",
    "ts": "2026-05-13T17:00:00Z",
    "status": "mock",
}


SKILLS = [
    # ─── DAILY ROUTINES (no input) ───
    {
        "label": "Morning Brief",
        "prompt_template": (
            "Act autonomously. Do not ask for confirmation. "
            "Do not use AskUserQuestion. Run the /morning skill"
        ),
        "description": "Daily briefing — swap for whatever /morning-style skill you have",
        "category": "daily",
    },
    {
        "label": "Inbox Triage",
        "prompt_template": (
            "Act autonomously. Do not ask for confirmation. "
            "Do not use AskUserQuestion. Run the /inbox-brief skill"
        ),
        "description": "Scan recent inbox and categorize",
        "category": "daily",
    },

    # ─── CONTENT / RESEARCH (take input) ───
    {
        "label": "Deep Research",
        "prompt_template": (
            "Act autonomously. Do not ask for confirmation. "
            "Do not use AskUserQuestion. Run /deep-research on: {input}"
        ),
        "description": "Multi-source research across web, YouTube, etc.",
        "category": "content",
        "input_placeholder": "topic to research",
    },
    {
        "label": "Quick Prompt",
        "prompt_template": "{input}",
        "description": "Send any free-form prompt to Claude Code",
        "category": "content",
        "input_placeholder": "type any prompt",
    },
]
