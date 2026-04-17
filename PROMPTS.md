# Starter Prompts

Copy-paste prompts for Claude Code to customize the dashboard. Run from inside the `agentic-os-dashboard` folder.

```bash
claude
```

Then paste any prompt below.

---

## Aesthetic changes

### Swap the color palette

> "This dashboard uses a terracotta + near-black palette defined as CSS custom properties in `app.py` (search for `--accent`, `--bg`, `--bg-card`). I want to swap to [describe palette, e.g., 'arctic blue on deep navy', 'mint green on charcoal', 'purple cyberpunk']. Update the CSS vars only. Show me the diff before applying."

### Rename the header

> "Change the header text from 'AGENTIC OS' to '[MY BRAND]'. Also update the page title in `st.set_page_config` and the favicon path if there is one."

### Change the chart pattern

> "The cumulative activity chart has a subtle blueprint grid + warm radial vignette behind it. I want to swap the pattern for [e.g., 'a dot matrix', 'diagonal hatch lines', 'nothing — make it flat']. Find the relevant CSS in `.activity-chart-wrap::before` and update."

### Tune the boot animation

> "The gauges at the top animate in with a staggered slide-rise over about 2 seconds on page load. Animation rules are in PREMIUM_CSS, search for `boot-rise`, `boot-slide-l`, `boot-slide-r`. I want the gauges to [e.g., 'feel heavier', 'snap in faster', 'be more subtle']. Adjust durations and delays."

---

## Data changes

### Swap the skills

> "Open `config.py`. The `SKILLS` list defines the buttons. Replace all entries with MY skills. Here they are:
>
> - [label] — runs `/[skill-name]` — [description]
> - [label] — runs `/[skill-name]` — [description]
>
> Keep the same `prompt_template` pattern (starts with 'Act autonomously. Do not ask for confirmation. Do not use AskUserQuestion.')."

### Change my Claude plan

> "I'm on the [Pro/Max/Team] plan. Update `CLAUDE_PLAN` in `config.py` and adjust `LIMITS` to match my actual plan ceilings. The five_hour_tokens and weekly_tokens are rough — show me where the dashboard displays actual `/usage` output so I can calibrate."

### Add a new gauge

> "I want a fourth gauge at the top tracking [metric]. Example: GitHub commits today from `git log`, Pomodoros completed from a local file, or emails triaged today. Add it as a fourth column next to the existing three. Match the existing gauge styling (`.gauge-card` + `render_gauge()`). Read the data from [source]."

### Change the vault path

> "My working folder isn't `C:\Users\Chase\the vault`. It's `[my path]`. Update `VAULT_PATH`, `VAULT_NAME`, `DAILY_NOTES_DIR`, and `RUNS_DIR` in `config.py` to point to my folder. Make sure the dashboard still launches Claude Code with the right `cwd`."

---

## Making it always-on

### Windows autostart

> "I want this Streamlit app to launch automatically when I log into Windows. Use Task Scheduler. Run hidden (no visible terminal window). Point me at `http://localhost:8501` once running. Write me a `.bat` file + the Task Scheduler XML import, and walk me through the install steps."

### Mac autostart

> "Set up this Streamlit app to auto-launch on macOS login using launchd. Create a `.plist` file in `~/Library/LaunchAgents/`, show me exactly where to put it, and run `launchctl load` on it. Also redirect logs to `~/Library/Logs/agentic-os-dashboard.log` so I can debug if it fails to start."

### Linux autostart

> "Create a systemd user service that launches this Streamlit app on login. Put it in `~/.config/systemd/user/`. Enable and start it. Walk me through `systemctl --user status` to verify."

### Desktop shortcut (double-click launcher)

> "Make me a double-click launcher for this dashboard. On [Windows: `.bat` / Mac: `.command` / Linux: `.desktop`]. Launcher should: change to the project directory, start the Streamlit server, open the browser to localhost:8501. Put it on my desktop."

---

## Making it a real app

### System tray (simplest native feel)

> "Wrap this Streamlit app in a Python system tray app using `pystray`. Icon in the tray. Left-click opens the dashboard in the default browser. Right-click menu: Start/Stop server, Quit. Bundle the tray launcher as a separate `tray.py` that imports the existing app."

### Tauri desktop app (most polished)

> "I want to ship this as a native desktop app using Tauri. Set up the project structure. On launch: start the Streamlit server in the background, open a native Tauri window pointing at `http://localhost:8501`, hide the browser chrome. On close: kill the server. Walk me through `cargo tauri init` and the config changes I need."

### Electron alternative

> "Same as above but use Electron instead of Tauri. Node.js flavor. Less polished but easier if I don't know Rust."

---

## New features

### Add a "Quick Prompt" input box

> "Add a free-text input at the top of the skills panel. User types any prompt, hits Enter, dashboard runs `claude -p "<prompt>"` with it. Same streaming output as the skill buttons. Keep the existing buttons below."

### Add a history viewer

> "Add a collapsible section showing the last 20 runs — skill name, timestamp, cost, token count, status. Source the data from the existing `session-meta` JSON files. Style it to match the cockpit aesthetic."

### Add a cost tracker

> "Add a small widget next to the MCP strip showing today's total cost in dollars, pulled from `cost_usd` in the session-meta files. Warn visually if I'm above $10/day."

### Add notifications

> "When a routine finishes running, show a desktop notification (OS-level, not browser toast). Use `plyer` on Windows/Linux, `osascript` on Mac. Include skill name and run duration."

---

## Debugging prompts

### "Something broke after I edited"

> "I edited [file] and now the dashboard shows [error / blank screen / weird behavior]. Here's the terminal output: [paste]. Diagnose and fix. Don't add new features."

### "I want to revert my changes"

> "I've made changes I regret. Run `git status` to see what's different from the original repo, then help me decide which changes to keep and which to revert."

### "The data is wrong"

> "The gauges show [X] but `/usage` in Claude Code shows [Y]. The dashboard reads from `~/.claude/usage-data/session-meta/`. Diagnose the discrepancy — calibration issue, missing file, timezone bug, or stale cache?"

---

## Tips for good prompts

1. **Point Claude at the specific file/function** ("search for `render_gauge` in `app.py`") instead of making it hunt.
2. **Ask for the diff before applying** — catches misunderstandings early.
3. **Show, don't tell** — paste the exact error message, not a paraphrase.
4. **One change per prompt** — easier to review and revert.
5. **When stuck, screenshot the UI** and ask Claude to describe what's wrong. It'll see more than you expect.
