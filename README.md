# Agentic OS Dashboard

A local visual cockpit for your Claude Code usage + skill dispatch. Three-tab layout (Overview / Audience / Research), live TokenBurn meter, parallel skill runs through a background queue, audience-metric cards, marquees that pull from your vault.

Runs entirely on your machine. Reads from `~/.claude/` and your vault. Nothing ships to the cloud.

---

## What you're getting

**Shared zone (above tabs):**
- **AGENTICOS header** + quicknav pills (terminal / vault / daily note / runs folder / drafts / ↻ pull / status)
- **TokenBurn 5h marquee** — HUD-bracketed bar with live usage %, projection band, scan-line, comet trail. Sources from real `tokens_5h` rows written by the `/metrics-pull` skill into `system/metrics/metrics.csv`.
- **MCP integrations strip** — connected MCP server health dots.

**Three tabs:**
- **Overview** — Schedule (today's calendar) + Agent Runs · 30D chart side-by-side. Below: legacy skill picker + streaming hero + sidebar (background queue, recent runs, 7-day bars, forecast, vault pulse).
- **Audience** — Latest Upload card + 4 platform metric cards (YT subs / YT views 28d / Instagram / TikTok) + YtWeekReview marquee with Altair bar chart + verdict chips + top/under performer cards.
- **Research** — MorningBrief 2×2 grid (Headlines / YT Trending / X Conversation / Content Opps) with coverage chip strip pulled from the latest `/morning` skill output.

**Behavior:**
- Click any skill chip → loads its template into the prompt box (autonomy preamble wrapped invisibly).
- Hit "run →" → spawns `claude.exe -p` inline, streams phases + tokens live into the hero card.
- Click chips DURING a foreground run → queues them via `system/queue/<uuid>.json` so the agentic-os-runner daemon picks them up in parallel. Max 3 concurrent. Visible in the **§ BACKGROUND QUEUE** sidebar card (polls every 3s; dots flip queued → running → done).
- Click `↻ pull` in quicknav → queues `/metrics-pull` skill → refreshes TokenBurn % + audience counts + latest video.

Dark Anthropic-warm palette. Subtle terracotta crosshatch atmosphere. Drop-from-100 boot animation on TokenBurn.

---

## Prerequisites

1. **Python 3.10+** — [download here](https://www.python.org/downloads/). On Windows, check "Add Python to PATH" during install.
2. **Git** — [download here](https://git-scm.com/downloads).
3. **Claude Code CLI** installed + signed in. Run it at least once so it generates session data.
4. **A terminal** (PowerShell / Terminal.app / your shell of choice).

Verify:

```bash
python --version      # 3.10+
git --version
claude --version
```

If any fail, fix that first.

---

## Step 1 — Clone

```bash
git clone https://github.com/cth9191/agentic-os-dashboard.git
cd agentic-os-dashboard
```

---

## Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

Installs Streamlit, Altair, plotly, pandas. ~1 minute.

Permission errors on Mac/Linux? Try `pip install --user -r requirements.txt`.

---

## Step 3 — Create your `config.py`

```bash
# Windows
copy config.example.py config.py
# Mac / Linux
cp config.example.py config.py
```

Open `config.py` in an editor. Edit the top section:

- **`VAULT_PATH`** — folder Claude Code runs in. Usually your Obsidian vault or main project folder. Mac example: `Path("/Users/yourname/Documents/my-vault")`.
- **`VAULT_NAME`** — display name shown in the header.
- **`CLAUDE_CLI`** — full path to `claude` executable. Find with `where claude` (Windows) or `which claude` (Mac/Linux).
- **`CLAUDE_PLAN`** — `"pro"`, `"max"`, `"team"`, or `"enterprise"`. Controls daily routine cap.

The `SKILLS` list at the bottom defines the chip buttons. The example ships with placeholder skills across memory/productivity/research/content/finance/custom categories — keep, swap, or delete to taste.

`config.py` is gitignored. Your edits stay local.

---

## Step 4 — Run it

```bash
streamlit run app.py
```

Opens `http://localhost:8501`. If it doesn't auto-open, paste the URL.

**First-run expectations:**

- If you've been using Claude Code, TokenBurn populates once `/metrics-pull` runs (click the ↻ pull pill in quicknav).
- Empty vault? Set `DEMO_MODE = True` in `config.py` — all cards render mocked data so you can verify the layout before wiring real feeds.
- Audience cards expect `<vault>/system/metrics/metrics.csv` with `claude_code/tokens_5h` + `youtube/subscribers` + `instagram/followers` + `tiktok/followers` rows. The `/metrics-pull` skill writes them.

**Stop:** `Ctrl+C` in the terminal.

---

## Step 5 — Adapt it (with Claude Code)

The dashboard was built with Claude Code and is built to be modified with Claude Code.

In the repo folder run `claude` and try:

> "Look at this dashboard. Swap the terracotta accent for a cool blue palette. Show me the changes before applying."

> "Add a metric card row for my Stripe MRR — read the latest `stripe/mrr` row from `<vault>/system/metrics/metrics.csv`."

> "Rename the skill chips and replace them with the slash commands I actually use. Here are mine: [list]."

> "Hide the audience tab if I don't have audience metrics yet."

> "Re-skin the TokenBurn marquee in a green palette for my framework demo recording."

See `PROMPTS.md` for tested starter prompts.

---

## Wiring the live data feeds

Three feeds populate the dashboard. All are optional — the layout renders coherently when any are missing.

### `system/metrics/metrics.csv`
Append-only CSV: `timestamp,source,metric,value,status,error`. Each row is one metric snapshot. The dashboard reads the **latest** row per `(source, metric)` pair.

Cards consume:
- `claude_code/tokens_5h` → TokenBurn %
- `youtube/subscribers`, `youtube/views_28d` → audience cards
- `instagram/followers`, `tiktok/followers` → audience cards

Populate via the `/metrics-pull` skill (separate repo). Click the `↻ pull` pill in quicknav to queue a refresh.

### `system/metrics/latest-video.json`
JSON written by your YouTube pull script:
```json
{"title": "…", "url": "https://youtu.be/…", "views": 1571, "likes": 51,
 "comments": 1, "published_at": "…", "ts": "…", "status": "ok"}
```
Feeds the Latest Upload card.

### `inbox/reports/yt-reviews/*.md` + `inbox/reports/morning/*.md`
Markdown reports the dashboard parses to populate the YtWeekReview marquee + MorningBrief grid. Frontmatter + standard section headings (TL;DR / Uploads / Top performer / Underperformer for reviews; Headlines / YouTube Trending / Web / X / GitHub / Content Opportunities for briefs). See `inbox/reports/_index.md` in the [agentic-os-vault-template] repo for the expected shape.

---

## Parallel skill runs

Two execution paths:

**Foreground** — form submit. Spawns `claude.exe -p` in a daemon thread on the Streamlit server. Streams stream-json events back into the live hero card. Page refresh during a foreground run loses the live feed (subprocess keeps running, output saves to `dashboard-runs/<date>/`).

**Background queue** — chip click during a foreground run, or the `↻ pull` pill. Writes intent JSON to `system/queue/<uuid>.json`. The agentic-os-runner daemon (separate repo) picks up + executes via its own pool (MAX_CONCURRENT=3 by default). Queue panel polls every 3s and shows live status (queued → running → ok/err) with deep-link to the deliverable on completion.

Queueable skills are limited to runner-known names (see `RUNNER_SKILLS` set in `app.py` near line ~4790). Skills outside that allowlist toast a warning instead of queueing. The runner repo can be extended to add more — see [agentic-os-runner].

---

## Making it "always on" (optional)

### Double-click launcher
Windows `start-dashboard.bat`:
```bat
@echo off
cd /d C:\path\to\agentic-os-dashboard
start "" http://localhost:8501
streamlit run app.py
```
Mac `start-dashboard.command`:
```bash
#!/bin/bash
cd /path/to/agentic-os-dashboard
open http://localhost:8501
streamlit run app.py
```
`chmod +x` and double-click.

### Autostart on login
Ask Claude Code:
> "Set up this Streamlit app to auto-launch on Windows login via Task Scheduler. Run in background, no visible terminal. Open at localhost:8501."

Or for Mac:
> "Set up this Streamlit app to auto-launch on macOS login via launchd."

### System tray
> "Wrap this Streamlit app in a Python system-tray app via `pystray`. Icon starts/stops the server and opens browser."

### Native desktop wrapper
> "Wrap this Streamlit app in a Tauri shell. On launch, start the Streamlit server in the background and open a native window pointing at localhost:8501."

---

## Troubleshooting

**"streamlit: command not found"** — Python installed but scripts folder not on PATH. Windows: reinstall Python with "Add to PATH" checked. Mac: `export PATH="$HOME/.local/bin:$PATH"` in `~/.zshrc`.

**TokenBurn stuck at 0%** — no `claude_code/tokens_5h` row in `<vault>/system/metrics/metrics.csv` yet. Click the `↻ pull` pill in quicknav to queue `/metrics-pull`. If the skill isn't installed, install it from the agentic-os-vault-template repo or set `DEMO_MODE = True` temporarily.

**"Permission denied" when a skill runs** — `PERMISSION_MODE` in `config.py` is `bypassPermissions` by default. Change to `"default"` if you want Claude to prompt per-tool.

**Port 8501 already in use** — `streamlit run app.py --server.port 8502`.

**Queue chips do nothing** — skills outside the runner allowlist can't queue. Either run them foreground (load template into prompt + hit "run →"), or extend the runner's dispatch table.

**Page refresh during a run loses the streaming view** — by design. Subprocess keeps running, output saves to `dashboard-runs/`. Use the queue path (chip click during a foreground run) for long jobs you want to walk away from.

---

## File map

- `app.py` — the whole dashboard (one big Streamlit file)
- `config.example.py` — template config. Copy to `config.py` and edit.
- `config.py` — **gitignored**. Your personal paths, plan, and skills.
- `requirements.txt` — Python deps
- `.streamlit/config.toml` — Streamlit theme + server settings
- `assets/` — images, mascot sprites
- `PROMPTS.md` — starter prompts for customizing with Claude Code
- `DESIGN.md` — visual + architecture notes
- `HANDOFF.md` — original v1 build log

---

## Companion repos

- **agentic-os-runner** — background daemon that picks up `system/queue/*.json` intents and executes via `claude.exe -p`. Required for parallel queue runs to actually fire.
- **agentic-os-vault-template** — opinionated vault skeleton with `system/metrics/`, `system/queue/`, `system/runs/`, `inbox/reports/`, daily-note schema. Drop-in companion to the dashboard.

---

## License

MIT. Build whatever you want with it.
