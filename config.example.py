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
    "daily_drivers":  False,  # overview lower-right — write-back loop causes Streamlit
                              # to rerun the whole page on each toggle, which feels jarring
                              # next to Obsidian's instant click. Disabled by default.
                              # Flip to True if you want the experimental checkboxes.
    "throughput":     True,   # 30-day agent-runs chart, sits in the slot drivers used to fill
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


# Category display order (left-to-right on dashboard).
SKILL_CATEGORY_ORDER = ["memory", "productivity", "research", "content", "finance", "custom"]


# Standard autonomy preamble — prepended automatically at runtime by the app's
# _wrap_autonomy() helper so users see only the task portion in the prompt box.
# You can include or omit it here; the app handles both cases idempotently.
_AUTO = (
    "Act autonomously. Do not ask for confirmation. "
    "Do not use AskUserQuestion. "
)


SKILLS = [
    # ─── MEMORY ──────────────────────────────────────────────
    # Skills that manage your second brain — cleanup, indexing,
    # consolidation. Swap with your own slash-commands.
    {
        "label": "Vault Cleanup",
        "prompt_template": _AUTO + "Run the /vault-cleanup skill",
        "description": "Archive stale notes older than 7 days",
        "category": "memory",
    },
    {
        "label": "KB Index",
        "prompt_template": _AUTO + "Run /index-vault on: {input}",
        "description": "Reindex a folder into your knowledge base",
        "category": "memory",
        "input_placeholder": "folder path",
    },
    {
        "label": "KB Query",
        "prompt_template": _AUTO + "Run /kb-query: {input}",
        "description": "Search your knowledge base",
        "category": "memory",
        "input_placeholder": "question for KB",
    },
    {
        "label": "KB Status",
        "prompt_template": _AUTO + "Run the /kb-status skill",
        "description": "Health + indexed doc count",
        "category": "memory",
    },

    # ─── PRODUCTIVITY ────────────────────────────────────────
    # Daily routines — runnable via the parallel queue path
    # (chip click while another run is foregrounded queues this
    # through the runner pool).
    {
        "label": "Morning Brief",
        "prompt_template": _AUTO + "Run the /morning skill",
        "description": "AI trend briefing + inbox triage + sponsor drafts",
        "category": "productivity",
    },
    {
        "label": "Inbox Triage",
        "prompt_template": _AUTO + "Run the /inbox-brief skill",
        "description": "Scan last 24h inbox and categorize",
        "category": "productivity",
    },
    {
        "label": "Plan Today",
        "prompt_template": _AUTO + "Run the /plan-today skill",
        "description": "Build today's plan from calendar + carryover",
        "category": "productivity",
    },
    {
        "label": "Weekly Review",
        "prompt_template": _AUTO + "Run the /weekly-review skill",
        "description": "7-day retrospective with channel + personal sections",
        "category": "productivity",
    },

    # ─── RESEARCH ────────────────────────────────────────────
    # Investigative skills — typically take a topic/URL input.
    {
        "label": "Deep Research",
        "prompt_template": _AUTO + "Run /deep-research on: {input}",
        "description": "Multi-source research (web, YouTube, X, GitHub)",
        "category": "research",
        "input_placeholder": "topic to research",
    },
    {
        "label": "YT Pipeline",
        "prompt_template": _AUTO + "Run /yt-pipeline to research: {input}",
        "description": "YouTube search + NotebookLM analysis pipeline",
        "category": "research",
        "input_placeholder": "research query",
    },
    {
        "label": "YT Search",
        "prompt_template": _AUTO + "Run /yt-search for: {input}",
        "description": "Structured YouTube search with metadata",
        "category": "research",
        "input_placeholder": "search query",
    },
    {
        "label": "NotebookLM",
        "prompt_template": _AUTO + "Run /notebooklm: {input}",
        "description": "Create notebook, add sources, generate artifacts",
        "category": "research",
        "input_placeholder": "topic or source URLs",
    },

    # ─── CONTENT ─────────────────────────────────────────────
    # Content-creation skills — titles, hooks, outlines, cascades.
    {
        "label": "Title Ideas",
        "prompt_template": _AUTO + "Run /yt-titles for a video about: {input}",
        "description": "YouTube title ideation cross-referenced with top performers",
        "category": "content",
        "input_placeholder": "video description",
    },
    {
        "label": "Hooks",
        "prompt_template": _AUTO + "Run /yt-hooks for: {input}",
        "description": "Desire-based hooks + Three Hook Alignment",
        "category": "content",
        "input_placeholder": "video topic",
    },
    {
        "label": "Outline",
        "prompt_template": _AUTO + "Run /outlines for: {input}",
        "description": "Full YouTube outline scaffold",
        "category": "content",
        "input_placeholder": "video concept",
    },
    {
        "label": "Content Cascade",
        "prompt_template": _AUTO + "Run /content-cascade on: {input}",
        "description": "YouTube URL → blog + thread + LinkedIn drafts",
        "category": "content",
        "input_placeholder": "YouTube URL",
    },

    # ─── FINANCE ─────────────────────────────────────────────
    # Bookkeeping placeholders — wire to whatever finance skills you have.
    {
        "label": "Categorize",
        "prompt_template": _AUTO + "Run the /books-categorize skill",
        "description": "Label newest CSV — biz/personal + category",
        "category": "finance",
    },
    {
        "label": "Monthly P&L",
        "prompt_template": _AUTO + "Run /books-monthly for: {input}",
        "description": "Income, expense, net vs prior month",
        "category": "finance",
        "input_placeholder": "month (e.g. 2026-03 or 'last month')",
    },
    {
        "label": "Anomaly Scan",
        "prompt_template": _AUTO + "Run the /books-anomaly skill",
        "description": "Outliers, fraud markers, burn-rate spikes",
        "category": "finance",
    },

    # ─── CUSTOM ──────────────────────────────────────────────
    # Slots for your own custom skills — or stubs to remind you what
    # to build. Set `disabled: True` to render greyed-out placeholders.
    {
        "label": "Quick Prompt",
        "prompt_template": "{input}",
        "description": "Send any free-form prompt to Claude Code",
        "category": "custom",
        "input_placeholder": "type any prompt",
    },
    {
        "label": "Shopify CLI",
        "prompt_template": "",
        "description": "e-commerce ops — coming soon",
        "category": "custom",
        "disabled": True,
    },
    {
        "label": "Stripe CLI",
        "prompt_template": "",
        "description": "SaaS / payments — coming soon",
        "category": "custom",
        "disabled": True,
    },
    {
        "label": "CRM",
        "prompt_template": "",
        "description": "lead pipeline — coming soon",
        "category": "custom",
        "disabled": True,
    },
]
