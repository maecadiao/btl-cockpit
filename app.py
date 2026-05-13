import subprocess
import threading
import queue
import re
import json
import time
import shutil
import base64
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from itertools import groupby

import streamlit as st
import altair as alt
import pandas as pd

from config import (
    VAULT_PATH,
    VAULT_NAME,
    CLAUDE_CLI,
    DAILY_NOTES_DIR,
    RUNS_DIR,
    DRAFTS_AWAITING,
    SKILLS,
    SKILL_CATEGORY_ORDER,
    RUN_TIMEOUT_SEC,
    PERMISSION_MODE,
    LIMITS,
    SESSION_META_DIR,
    CLAUDE_PLAN,
)
import config as _cfg  # for getattr lookups (DEMO_MODE, ENABLED_CARDS, DEMO_*)

st.set_page_config(page_title="Agentic OS", page_icon="◆", layout="wide")

# ═══════════════════════════════════════════════════════════
# GLOBAL RUNTIME (shared across reruns, lives in module scope)
# ═══════════════════════════════════════════════════════════


@st.cache_resource
def get_runtime():
    return {
        "proc": None,
        "buffer": [],           # raw stdout text chunks
        "text": "",             # accumulated assistant text (parsed)
        "phases": [],           # tool_use phase log
        "current_phase": None,  # latest phase label
        "cost_usd": None,
        "tokens_in": None,
        "tokens_out": None,
        "done": False,
        "cancelled": False,
        "error": None,
        "start_time": None,
    }


RT = get_runtime()


def reset_runtime():
    RT["proc"] = None
    RT["buffer"] = []
    RT["text"] = ""
    RT["phases"] = []
    RT["current_phase"] = None
    RT["cost_usd"] = None
    RT["tokens_in"] = None
    RT["tokens_out"] = None
    RT["done"] = False
    RT["cancelled"] = False
    RT["error"] = None
    RT["start_time"] = None


# ═══════════════════════════════════════════════════════════
# STYLES
# ═══════════════════════════════════════════════════════════

PREMIUM_CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg:         #0e0f10;
    --bg-elev:    #141516;
    --bg-card:    #1c1b19;
    --bg-card-hi: #222120;
    --ring-soft:  rgba(209, 207, 197, 0.18);
    --ring-mid:   rgba(209, 207, 197, 0.30);
    --ring-hard:  #b0aea5;
    --fg:         #faf9f5;
    --fg-dim:     #b0aea5;
    --fg-mute:    #87867f;
    --accent:     #c96442;
    --accent-soft: rgba(201, 100, 66, 0.12);
    --warn:       #d9a566;
    --danger:     #b53333;
    --good:       #8fb97a;

    /* legacy aliases (keep existing class selectors resolving) */
    --text:          var(--fg);
    --text-dim:      var(--fg-dim);
    --text-mute:     var(--fg-mute);
    --border:        var(--ring-soft);
    --border-strong: var(--ring-mid);
    --ring-warm:     var(--ring-soft);
    --ring-deep:     var(--ring-mid);
    --accent-glow:   rgba(201, 100, 66, 0.32);
    --coral:         #d97757;
    --amber:         var(--warn);
}

html, body, [class*="css"] {
    font-family: 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace;
    color: var(--fg);
}

.stApp { background: var(--bg); }
body   { background: var(--bg); }

h1, h2, h3, h4, h5, h6 {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    letter-spacing: 0.02em;
    color: var(--fg);
    text-transform: uppercase;
}

.hero-title {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 2.8rem !important;
    font-weight: 600;
    letter-spacing: 0.05em;
    line-height: 1;
    color: var(--fg);
    margin: 0 0 0.5rem 0;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 0.8rem;
}
.hero-title em {
    font-style: normal;
    color: var(--accent);
    font-weight: 600;
    margin-left: 0;
}
.hero-title .hero-word { display: inline-block; }

.title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1.2rem;
    flex-wrap: wrap;
    margin-bottom: 0.3rem;
}
.title-crumb {
    margin: 0;
    text-align: right;
    max-width: 60%;
}

/* Sprite-sheet mascot: 7 frames × 12x32, scaled 2× → 24x64 rendered */
.hero-title .mascot {
    display: inline-block;
    width: 24px;
    height: 64px;
    background-image: var(--idle);
    background-repeat: no-repeat;
    background-position: 0 0;
    background-size: 168px 64px;
    image-rendering: pixelated;
    image-rendering: crisp-edges;
    -ms-interpolation-mode: nearest-neighbor;
    vertical-align: middle;
    margin-right: 0.2em;
    margin-top: 0;
    filter: none;
    animation: robot-idle 0.85s steps(7) infinite;
    will-change: background-position, transform;
    transition: filter 0.2s ease;
    transform: translateY(-14px);
}
@keyframes robot-idle {
    from { background-position:    0  0; }
    to   { background-position: -168px 0; }
}
.hero-title .mascot:hover {
    background-image: var(--run);
    animation: robot-run 0.55s steps(7) infinite;
    filter: none;
    transform: translateY(0);
}
@keyframes robot-run {
    from { background-position:    0  0; }
    to   { background-position: -168px 0; }
}

.caption-mono {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    color: var(--fg-mute);
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

[data-testid="stStatusWidget"], [data-testid="stToolbar"],
#MainMenu, footer, [data-testid="stDecoration"],
[data-testid="stHeader"], header[data-testid="stHeader"] {
    display: none !important;
    height: 0 !important;
}

.block-container {
    padding-top: 1rem !important;
    padding-bottom: 1rem !important;
    max-width: 1480px;
}

.cat-label, .chip-cat, .cpt-cat {
    color: var(--accent);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.2em;
    font-weight: 500;
    text-transform: uppercase;
    margin: 0.8rem 0 0.5rem 0;
    padding: 0.35rem 0 0.35rem 0;
    border-bottom: 1px solid var(--ring-soft);
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.cat-label::before, .cat-label::after,
.cpt-cat::before, .cpt-cat::after { content: none; }
.chip-cat, .cpt-cat.chip-cat {
    margin: 0.8rem 0 0.4rem 0;
    font-size: 0.58rem;
    letter-spacing: 0.22em;
}
.brand-ico {
    width: 12px;
    height: 12px;
    vertical-align: middle;
    margin-right: 0.35rem;
    display: inline-block;
    flex-shrink: 0;
}
.header-link-btn,
.header-link-btn:link,
.header-link-btn:visited {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: var(--bg-card);
    color: var(--fg-dim) !important;
    border: none;
    border-radius: 2px;
    padding: 0.4rem 0.7rem;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    font-size: 0.66rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    text-align: left;
    text-decoration: none !important;
    cursor: pointer;
    transition: box-shadow 0.12s, color 0.12s;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
.header-link-btn:hover,
.header-link-btn:focus,
.header-link-btn:active {
    color: var(--accent) !important;
    text-decoration: none !important;
    outline: none;
    box-shadow: 0 0 0 1px var(--accent);
}
.header-link-btn * { text-decoration: none !important; }

/* Chip buttons (compact) */
[data-testid="stButton"] > button[kind="secondary"] {
    padding: 0.45rem 0.6rem;
    font-size: 0.72rem;
}
.stTextArea textarea {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.82rem !important;
    background: #1c1b19 !important;
    color: var(--fg) !important;
    border: none !important;
    border-radius: 3px !important;
    line-height: 1.6 !important;
    padding: 0.75rem 0.9rem !important;
    box-shadow:
        0 0 0 1px var(--ring-mid),
        inset 0 1px 0 rgba(255, 255, 255, 0.03),
        0 6px 20px rgba(0, 0, 0, 0.35) !important;
    transition: box-shadow 0.15s ease !important;
}
.stTextArea textarea:hover {
    box-shadow:
        0 0 0 1px rgba(201, 100, 66, 0.45),
        inset 0 1px 0 rgba(255, 255, 255, 0.04),
        0 6px 22px rgba(0, 0, 0, 0.4) !important;
}
.stTextArea textarea:focus {
    background: #201e1c !important;
    box-shadow:
        0 0 0 1px var(--accent),
        0 0 0 4px rgba(201, 100, 66, 0.12),
        inset 0 1px 0 rgba(255, 255, 255, 0.04),
        0 8px 28px rgba(0, 0, 0, 0.45) !important;
    outline: none !important;
}

.stButton > button, .stFormSubmitButton > button {
    background: var(--bg-card);
    color: var(--fg-dim);
    border: none;
    border-radius: 2px;
    padding: 0.5rem 0.7rem;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    transition: box-shadow 0.12s, color 0.12s;
    text-align: left;
    height: auto;
    white-space: normal;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
    color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
}
.stButton > button:active, .stFormSubmitButton > button:active {
    background: rgba(201, 100, 66, 0.1) !important;
    color: var(--accent) !important;
    box-shadow: 0 0 0 1px var(--accent) !important;
}
.stButton > button:disabled, .stFormSubmitButton > button:disabled {
    opacity: 0.35;
    color: var(--fg-mute);
    cursor: not-allowed;
}

.stTextInput > div > div > input {
    background: var(--bg-elev);
    color: var(--fg);
    border: none;
    border-radius: 3px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    padding: 0.5rem 0.75rem;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
.stTextInput > div > div > input:focus {
    box-shadow: 0 0 0 1px var(--accent);
    outline: none;
}
.stTextInput > div > div > input::placeholder { color: var(--fg-mute); }

pre, code, [data-testid="stCodeBlock"] {
    font-family: 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace !important;
    font-size: 0.76rem !important;
    background: var(--bg-elev) !important;
    border: none !important;
    border-radius: 3px !important;
    color: var(--fg-dim) !important;
    line-height: 1.55 !important;
    box-shadow: 0 0 0 1px var(--ring-soft) !important;
}

hr {
    border: none !important;
    border-top: 1px solid var(--ring-soft) !important;
    margin: 0.9rem 0 !important;
}
hr.chapter {
    border: none !important;
    border-top: 1px solid var(--ring-soft) !important;
    height: 0 !important;
    background: none !important;
    margin: 1rem 0 !important;
    position: relative;
    overflow: visible;
}
hr.chapter::after { content: none; }

.hero-card {
    background: var(--bg-card);
    border: none;
    border-radius: 3px;
    padding: 0.75rem 0.9rem;
    box-shadow: 0 0 0 1px var(--ring-soft);
    min-height: 80px;
    position: relative;
    overflow: hidden;
}
.hero-card::before { content: none; }
.hero-card.running {
    box-shadow: 0 0 0 1px var(--accent);
    animation: hero-pulse 2.4s ease-in-out infinite;
}
.hero-card.error {
    background: rgba(181, 51, 51, 0.05);
    box-shadow: 0 0 0 1px rgba(181, 51, 51, 0.55);
}
.hero-card.error .hero-label { color: var(--danger); }
.hero-card.error .hero-headline em { color: var(--danger); }
.error-detail {
    background: var(--bg-elev);
    border: none;
    border-radius: 2px;
    padding: 0.55rem 0.75rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: #e8b8b8;
    box-shadow: 0 0 0 1px rgba(181, 51, 51, 0.35);
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 200px;
    overflow-y: auto;
    margin: 0.4rem 0;
    line-height: 1.5;
}
.error-hint {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    color: var(--fg-mute);
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.skill-desc {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    color: var(--fg-mute);
    margin: -0.1rem 0 0.4rem 0.1rem;
    letter-spacing: 0.02em;
    line-height: 1.35;
    text-transform: uppercase;
}
@keyframes hero-pulse {
    0%, 100% { box-shadow: 0 0 0 1px var(--accent); }
    50%      { box-shadow: 0 0 0 1px var(--accent), 0 0 18px rgba(201, 100, 66, 0.28); }
}

.hero-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--fg-mute);
    margin-bottom: 0.3rem;
}
.hero-headline {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--fg);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    line-height: 1.2;
    margin: 0 0 0.3rem 0;
}
.hero-headline em { font-style: normal; color: var(--accent); }

.cursor-blink {
    display: inline-block;
    color: var(--accent);
    font-family: 'JetBrains Mono', monospace;
    font-weight: 400;
    margin-left: 0.35rem;
    line-height: 1;
    animation: cursor-blink 1.05s steps(2) infinite;
}
@keyframes cursor-blink {
    0%, 49%   { opacity: 1; }
    50%, 100% { opacity: 0; }
}

@keyframes pulse {
    0%, 100% { opacity: 0.4; }
    50%      { opacity: 1.0; }
}
.pulse-dot {
    width: 8px; height: 8px;
    background: var(--accent);
    border-radius: 50%;
    display: inline-block;
    margin-right: 0.5rem;
    vertical-align: middle;
    animation: pulse 1.1s ease-in-out infinite;
}
.pulse-dot.idle {
    background: var(--warn);
    animation: idle-pulse 2.8s ease-in-out infinite;
}
@keyframes idle-pulse {
    0%, 100% { opacity: 0.5; }
    50%      { opacity: 1; }
}
.pulse-dot.small { width: 6px; height: 6px; }

.status-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.35rem 0.7rem;
    background: transparent;
    border: none;
    border-radius: 2px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--fg-dim);
    box-shadow: 0 0 0 1px var(--ring-soft);
    float: right;
    margin-top: 0.55rem;
}
.status-chip.running {
    color: var(--accent);
    background: rgba(201, 100, 66, 0.06);
    box-shadow: 0 0 0 1px var(--accent);
    animation: chip-pulse 2.4s ease-in-out infinite;
}
@keyframes chip-pulse {
    0%, 100% { box-shadow: 0 0 0 1px var(--accent); }
    50%      { box-shadow: 0 0 0 1px var(--accent), 0 0 10px rgba(201, 100, 66, 0.3); }
}

.activity-feed {
    background: var(--bg-card);
    border: none;
    border-radius: 3px;
    padding: 0.6rem 0.8rem;
    box-shadow: 0 0 0 1px var(--ring-soft);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.74rem;
    color: var(--fg-dim);
    max-height: 500px;
    overflow-y: auto;
    line-height: 1.6;
}
.activity-feed h1, .activity-feed h2, .activity-feed h3 {
    font-family: 'JetBrains Mono', monospace;
    color: var(--fg);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.activity-feed p { margin: 0.2rem 0 !important; }
.activity-feed ul { padding-left: 1rem; }

.obsidian-link, .meta-link {
    display: inline-block;
    color: var(--accent);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.66rem;
    text-decoration: none;
    padding: 0.25rem 0.55rem;
    margin: 0.2rem 0.3rem 0.1rem 0;
    border: none;
    border-radius: 2px;
    background: rgba(201, 100, 66, 0.05);
    box-shadow: 0 0 0 1px rgba(201, 100, 66, 0.3);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    transition: box-shadow 0.12s, background 0.12s;
}
.obsidian-link:hover, .meta-link:hover {
    background: rgba(201, 100, 66, 0.1);
    box-shadow: 0 0 0 1px var(--accent);
}
.meta-link {
    color: var(--fg-dim);
    background: transparent;
    box-shadow: 0 0 0 1px var(--ring-soft);
}

[data-testid="stForm"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
}

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(209, 207, 197, 0.12); border-radius: 0; }
::-webkit-scrollbar-thumb:hover { background: rgba(209, 207, 197, 0.22); }

.stream-output {
    background: var(--bg-elev);
    border: none;
    border-radius: 3px;
    padding: 0.7rem 0.9rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--fg-dim);
    box-shadow: 0 0 0 1px var(--ring-soft);
    max-height: 340px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
    margin-top: 0.7rem;
    line-height: 1.6;
    letter-spacing: 0.005em;
}

/* Body-copy treatment for rendered markdown output (cockpit mono) */
.output-body + [data-testid="stMarkdownContainer"] p,
.output-body ~ [data-testid="stMarkdownContainer"] p {
    line-height: 1.55;
    font-size: 0.82rem;
    color: var(--fg);
    font-family: 'JetBrains Mono', monospace;
}
.output-body + [data-testid="stMarkdownContainer"] h1,
.output-body + [data-testid="stMarkdownContainer"] h2,
.output-body + [data-testid="stMarkdownContainer"] h3 {
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--fg-dim);
    margin-top: 1rem;
    margin-bottom: 0.4rem;
}
.output-body + [data-testid="stMarkdownContainer"] li {
    line-height: 1.5;
    margin-bottom: 0.25rem;
    font-family: 'JetBrains Mono', monospace;
}
.output-body + [data-testid="stMarkdownContainer"] blockquote {
    border-left: 2px solid var(--accent);
    padding-left: 0.8rem;
    font-family: 'JetBrains Mono', monospace;
    font-style: normal;
    color: var(--fg-dim);
    margin: 0.7rem 0;
}

.phase-line {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    color: var(--fg-dim);
    margin-top: 0.4rem;
    letter-spacing: 0.04em;
}
.phase-line .phase-name { color: var(--accent); }

.meta-row {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.66rem;
    color: var(--fg-mute);
    margin-top: 0.5rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.meta-row .meta-val { color: var(--fg-dim); }

/* Recent runs card wrapper */
.runs-card {
    background: var(--bg-card);
    border: none;
    border-radius: 3px;
    padding: 0.55rem 0.75rem;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
.runs-card .cat-label {
    margin: 0 0 0.35rem 0;
    padding: 0 0 0.35rem 0;
    border-bottom: 1px solid var(--ring-soft);
}
.run-list {
    display: flex;
    flex-direction: column;
    padding: 0;
    margin: 0;
}
.run-row {
    display: grid;
    grid-template-columns: 3.2rem 1fr auto;
    align-items: center;
    column-gap: 0.6rem;
    padding: 0.4rem 0.1rem;
    border-top: 1px solid var(--ring-soft);
    background: transparent;
}
.run-row:first-child { border-top: none; }
.run-row .run-time {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    color: var(--fg-mute);
    letter-spacing: 0.04em;
}
.run-row .run-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.76rem;
    font-weight: 500;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--fg);
    line-height: 1.25;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.run-row:hover .run-label { color: var(--accent); }
.run-row a {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    color: var(--fg-mute);
    text-decoration: none;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    transition: color 0.12s;
}
.run-row a:hover { color: var(--accent); }

.approval-card {
    background: var(--bg-card);
    border: none;
    border-radius: 3px;
    padding: 0.6rem 0.8rem;
    margin-bottom: 0.5rem;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
.approval-card h4 {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    margin: 0 0 0.3rem 0;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.approval-card .approval-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.64rem;
    color: var(--fg-mute);
    letter-spacing: 0.06em;
    margin-bottom: 0.4rem;
}

/* Danger button variant (cancel) */
.cancel-btn .stButton > button {
    background: rgba(181, 51, 51, 0.06) !important;
    box-shadow: 0 0 0 1px rgba(181, 51, 51, 0.35) !important;
    color: var(--danger) !important;
}
.cancel-btn .stButton > button:hover {
    background: rgba(181, 51, 51, 0.14) !important;
    box-shadow: 0 0 0 1px var(--danger) !important;
    color: #fff !important;
}

/* Quick-nav pill bar */
.quicknav {
    display: flex;
    gap: 0.35rem;
    flex-wrap: wrap;
    align-items: center;
    margin: 0 0 0.7rem 0;
}
.quicknav a {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.35rem 0.7rem;
    background: transparent;
    border: none;
    border-radius: 2px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.66rem;
    font-weight: 500;
    color: var(--fg-dim);
    text-decoration: none;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    box-shadow: 0 0 0 1px var(--ring-soft);
    transition: box-shadow 0.12s, color 0.12s;
}
.quicknav a:hover {
    color: var(--accent);
    background: transparent;
    box-shadow: 0 0 0 1px var(--accent);
}
.quicknav a em, .quicknav .qn-icon {
    font-family: 'JetBrains Mono', monospace;
    font-style: normal;
    font-weight: 500;
    color: var(--accent);
    font-size: 0.7rem;
    letter-spacing: 0.06em;
}

/* Claude code pill — terracotta-tinted + traveling-dot border pulse */
.quicknav a.qn-claude {
    position: relative;
    overflow: visible;
    padding: 0.4rem 0.85rem;
    color: var(--fg);
    box-shadow: 0 0 0 1px var(--accent), 0 0 0 3px rgba(201, 100, 66, 0.08);
    background: rgba(201, 100, 66, 0.04);
}
.quicknav a.qn-claude:hover {
    background: rgba(201, 100, 66, 0.09);
    box-shadow: 0 0 0 1px var(--accent), 0 0 12px rgba(201, 100, 66, 0.35);
}
.quicknav a.qn-claude .qn-arrow {
    color: var(--accent);
    margin-left: 0.15rem;
    font-size: 0.66rem;
    opacity: 0.85;
}
.quicknav a.qn-claude > span { position: relative; z-index: 1; }
.qn-pulse-svg {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    overflow: visible;
    z-index: 0;
}

/* Status chip when embedded in quicknav — push to right edge */
.quicknav .qn-status {
    float: none !important;
    margin: 0 0 0 auto !important;
}

/* Metric tiles */
.metric-tile {
    background: var(--bg-card);
    border: none;
    border-radius: 3px;
    padding: 0.55rem 0.75rem;
    min-height: 64px;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
.metric-tile::before { content: none; }
.metric-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.58rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--fg-mute);
    margin-bottom: 0.3rem;
}
.metric-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.1rem;
    font-weight: 500;
    color: var(--fg);
    letter-spacing: 0.02em;
    line-height: 1.1;
}
.metric-value .unit {
    font-size: 0.72rem;
    color: var(--fg-mute);
    margin-left: 0.2rem;
}
.metric-value.highlight { color: var(--accent); }

/* MCP health strip */
.mcp-strip {
    display: flex;
    gap: 0.9rem;
    align-items: center;
    flex-wrap: wrap;
    margin: 0.4rem 0 0.8rem 0;
    padding: 0.45rem 0.75rem;
    background: var(--bg-card);
    border: none;
    border-radius: 3px;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
.mcp-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.58rem;
    text-transform: uppercase;
    letter-spacing: 0.22em;
    color: var(--accent);
    margin-right: 0.3rem;
    padding-right: 0.75rem;
    border-right: 1px solid var(--ring-soft);
}
.mcp-item {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.66rem;
    font-weight: 500;
    color: var(--fg-dim);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    transition: color 0.12s;
}
.mcp-item:hover { color: var(--accent); }
.mcp-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--fg-mute);
    flex-shrink: 0;
}
.mcp-dot.ready, .mcp-dot.connected {
    background: var(--accent);
    box-shadow: 0 0 4px rgba(201, 100, 66, 0.55);
}
.mcp-dot.needs_auth, .mcp-dot.needs-auth { background: var(--warn); }
.mcp-dot.failed, .mcp-dot.error { background: var(--danger); }
.mcp-dot.connecting {
    background: var(--fg-dim);
    animation: mcp-pulse 1.4s ease-in-out infinite;
}
@keyframes mcp-pulse {
    0%, 100% { opacity: 0.5; }
    50%      { opacity: 1; }
}

/* Chart container */
.chart-card, .cpt-chart-card {
    background: var(--bg-card);
    border: none;
    border-radius: 3px;
    padding: 0.5rem 0.7rem 0.3rem;
    margin-bottom: 0.7rem;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
/* Parchment variant — stripped in cockpit (kept as no-op for compatibility) */
.chart-card.parchment {
    background: var(--bg-card);
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    padding: 0.5rem 0.7rem 0.3rem;
    border-radius: 3px;
    box-shadow: 0 0 0 1px var(--ring-soft);
    margin: 0.3rem 0 0.7rem 0;
}
.chart-card.parchment .chart-title,
.chart-card.parchment .cpt-chart-title { color: var(--fg-dim); }
.chart-card.parchment .chart-title span,
.chart-card.parchment .cpt-chart-title span { color: var(--fg-mute) !important; }
.chart-card.mini-chart, .cpt-chart-card.mini-chart {
    padding: 0.4rem 0.6rem 0.25rem;
    border-radius: 3px;
    margin-top: 0.6rem;
}
.chart-title, .cpt-chart-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.66rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--fg-dim);
    margin-bottom: 0.3rem;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
}
.chart-title em, .cpt-chart-title em {
    font-family: 'JetBrains Mono', monospace;
    font-style: normal;
    font-weight: 500;
    color: var(--accent);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-size: 0.66rem;
}
.chart-title span, .cpt-chart-title span {
    color: var(--fg-mute);
    font-size: 0.6rem;
    letter-spacing: 0.06em;
}

/* Inline SVG cumulative activity chart (replaces plotly) */
.activity-chart-wrap {
    position: relative;
    margin: 0.2rem 0 0.1rem;
    isolation: isolate;
}
.activity-chart-wrap::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    background-image:
        radial-gradient(ellipse 78% 62% at 50% 55%, rgba(201, 100, 66, 0.055) 0%, rgba(201, 100, 66, 0) 72%),
        linear-gradient(180deg, rgba(0, 0, 0, 0) 55%, rgba(0, 0, 0, 0.18) 100%),
        repeating-linear-gradient(90deg, transparent 0 59px, rgba(209, 207, 197, 0.05) 59px 60px),
        repeating-linear-gradient(0deg,  transparent 0 39px, rgba(209, 207, 197, 0.05) 39px 40px),
        repeating-linear-gradient(90deg, transparent 0 11px, rgba(209, 207, 197, 0.022) 11px 12px),
        repeating-linear-gradient(0deg,  transparent 0 7px,  rgba(209, 207, 197, 0.022) 7px 8px);
}
.activity-svg {
    display: block;
    width: 100%;
    height: 170px;
    overflow: visible;
    position: relative;
    z-index: 1;
}
.activity-axis {
    display: flex;
    justify-content: space-between;
    padding: 0.25rem 0.1rem 0.15rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.56rem;
    color: var(--fg-mute);
    letter-spacing: 0.1em;
    text-transform: uppercase;
}

/* Gauge cards — htop-style hatched block bars */
.gauge-card, .cpt-gauge {
    background: var(--bg-card);
    border: none;
    border-radius: 3px;
    padding: 0.55rem 0.75rem;
    min-height: 64px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 0 0 1px var(--ring-soft);
    transition: box-shadow 0.12s;
}
.gauge-card:hover, .cpt-gauge:hover { box-shadow: 0 0 0 1px var(--ring-mid); }
.gauge-card::before, .cpt-gauge::before { content: none; }
.gauge-header, .cpt-gauge-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.58rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    margin-bottom: 0.28rem;
}
.gauge-label, .cpt-gauge-label { color: var(--fg-dim); }
.gauge-reset, .cpt-gauge-reset { color: var(--fg-mute); font-size: 0.56rem; letter-spacing: 0.08em; }
.gauge-track, .cpt-gauge-track {
    height: 10px;
    background: rgba(209, 207, 197, 0.08);
    border-radius: 0;
    overflow: hidden;
    margin-bottom: 0.35rem;
    position: relative;
}
.gauge-track::before, .cpt-gauge-track::before {
    content: "";
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(90deg, transparent 0 4px, var(--bg-card) 4px 5px);
    pointer-events: none;
    z-index: 2;
}
.gauge-fill, .cpt-gauge-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 0;
    transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    box-shadow: none;
}
.gauge-fill.warning, .cpt-gauge-fill.warning,
.cpt-gauge-fill.warn { background: var(--warn); box-shadow: none; }
.gauge-fill.danger, .cpt-gauge-fill.danger  { background: var(--danger); box-shadow: none; }
.gauge-stats, .cpt-gauge-stats {
    display: flex;
    align-items: baseline;
    gap: 0.3rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.9rem;
    letter-spacing: 0.02em;
    color: var(--fg);
}
.gauge-max, .cpt-gauge-max {
    font-size: 0.7rem;
    color: var(--fg-mute);
    font-family: 'JetBrains Mono', monospace;
}
.gauge-sub, .cpt-gauge-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    color: var(--fg-mute);
    margin-left: auto;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.gauge-delta, .cpt-gauge-delta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.58rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-left: auto;
    padding: 0.1rem 0.45rem;
    border-radius: 2px;
    border: none;
    color: var(--fg-mute);
    background: transparent;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
.gauge-delta.up, .cpt-gauge-delta.up         { color: var(--accent); box-shadow: 0 0 0 1px rgba(201, 100, 66, 0.40); background: rgba(201, 100, 66, 0.06); }
.gauge-delta.down, .cpt-gauge-delta.down     { color: var(--fg-dim); box-shadow: 0 0 0 1px var(--ring-soft); background: transparent; }
.gauge-delta.neutral, .cpt-gauge-delta.neutral { color: var(--fg-mute); }

/* ─── Cockpit forecast card ─── */
.cpt-forecast {
    background: var(--bg-card);
    border: none;
    border-radius: 3px;
    padding: 0.6rem 0.8rem;
    margin-top: 0.6rem;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
.cpt-forecast-head {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: var(--fg);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.25rem;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
}
.cpt-forecast-head em { font-style: normal; color: var(--accent); }
.cpt-forecast-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.58rem;
    color: var(--fg-mute);
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.cpt-forecast-track {
    height: 18px;
    background: rgba(209, 207, 197, 0.06);
    box-shadow: inset 0 0 0 1px var(--ring-soft);
    position: relative;
    margin: 0.5rem 0 0.3rem;
}
.cpt-forecast-elapsed {
    position: absolute;
    left: 0; top: 0; bottom: 0;
    background: rgba(201, 100, 66, 0.35);
    border-right: 1px solid var(--accent);
}
.cpt-forecast-proj {
    position: absolute;
    top: 0; bottom: 0;
    background: repeating-linear-gradient(45deg,
        rgba(201, 100, 66, 0.12) 0 5px,
        rgba(201, 100, 66, 0.28) 5px 10px);
    border-right: 1px dashed var(--accent);
}
.cpt-forecast-now {
    position: absolute;
    top: -2px; bottom: -2px;
    width: 2px;
    background: var(--fg);
}
.cpt-forecast-legend {
    display: flex;
    gap: 0.9rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.56rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--fg-mute);
    margin-top: 0.3rem;
    flex-wrap: wrap;
}

/* Scheduled-routine rows under forecast */
.cpt-sched {
    margin-top: 0.7rem;
    padding-top: 0.55rem;
    border-top: 1px solid var(--ring-soft);
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}
.cpt-sched-row {
    display: grid;
    grid-template-columns: 3.2rem 1fr auto;
    align-items: baseline;
    column-gap: 0.6rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.66rem;
    letter-spacing: 0.04em;
}
.cpt-sched-time {
    color: var(--accent);
    font-weight: 500;
}
.cpt-sched-label {
    color: var(--fg);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.cpt-sched-in {
    color: var(--fg-mute);
    font-size: 0.58rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.cpt-forecast-legend em { font-style: normal; color: var(--fg-dim); }

/* ─── Cockpit vault pulse ─── */
.cpt-pulse-card {
    background: var(--bg-card);
    border: none;
    border-radius: 3px;
    padding: 0.55rem 0.75rem;
    margin-top: 0.6rem;
    box-shadow: 0 0 0 1px var(--ring-soft);
}
.cpt-pulse-card > .cpt-cat {
    margin: 0 0 0.35rem 0;
    padding-top: 0;
}
.cpt-pulse {
    display: grid;
    grid-template-columns: 4.6rem 1fr auto;
    gap: 0.5rem;
    align-items: center;
    padding: 0.35rem 0.1rem;
    border-top: 1px solid var(--ring-soft);
    font-family: 'JetBrains Mono', monospace;
}
.cpt-pulse:first-of-type { border-top: none; }
.cpt-pulse-main { min-width: 0; }
.cpt-verb {
    font-size: 0.56rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 0.12rem 0.4rem;
    border-radius: 2px;
    text-align: center;
    box-shadow: 0 0 0 1px var(--ring-soft);
    color: var(--fg-dim);
    font-weight: 500;
    display: inline-block;
}
.cpt-verb.created {
    color: var(--accent);
    box-shadow: 0 0 0 1px rgba(201, 100, 66, 0.35);
    background: rgba(201, 100, 66, 0.08);
}
.cpt-verb.appended {
    color: var(--warn);
    box-shadow: 0 0 0 1px rgba(217, 165, 102, 0.35);
    background: rgba(217, 165, 102, 0.06);
}
.cpt-verb.updated { color: var(--fg-dim); }
.cpt-verb.linked {
    color: var(--good);
    box-shadow: 0 0 0 1px rgba(143, 185, 122, 0.35);
    background: rgba(143, 185, 122, 0.06);
}
.cpt-pulse-name {
    color: var(--fg);
    font-size: 0.74rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    letter-spacing: 0.02em;
}
.cpt-pulse-dir {
    color: var(--fg-mute);
    font-size: 0.56rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.cpt-pulse-ago {
    color: var(--fg-mute);
    font-size: 0.58rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

/* ─── Header bar — wraps the col row via :has() + hidden marker ─── */
[data-testid="stVerticalBlock"]:has(> div > .cpt-header-marker),
[data-testid="stHorizontalBlock"]:has(.cpt-header-marker) {
    padding: 0.3rem 0.7rem !important;
    box-shadow: 0 0 0 1px var(--ring-soft);
    border-radius: 3px;
    background: var(--bg-card);
    margin-bottom: 0.7rem !important;
    align-items: center;
}
.cpt-header-marker { display: none; }

/* ─── Skill chips (anchor-based, 4-column grid) ─── */
.cpt-skill-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.45rem;
    margin: 0 0 0.55rem 0;
}
@media (max-width: 1100px) {
    .cpt-skill-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 800px) {
    .cpt-skill-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.cpt-skill {
    background: var(--bg-card);
    box-shadow: 0 0 0 1px var(--ring-soft);
    border-radius: 2px;
    padding: 0.45rem 0.6rem;
    font-family: 'JetBrains Mono', monospace;
    text-align: left;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 0.12rem;
    transition: box-shadow 0.12s, color 0.12s;
    text-decoration: none !important;
    color: inherit;
    min-width: 0;
}
.cpt-skill:hover {
    box-shadow: 0 0 0 1px var(--accent);
    text-decoration: none !important;
}
.cpt-skill.loaded { box-shadow: 0 0 0 1px var(--accent); }
.cpt-skill.disabled {
    cursor: not-allowed;
    opacity: 0.55;
    border: 1px dashed var(--ring-soft);
    box-shadow: none;
}
.cpt-skill.disabled:hover {
    box-shadow: none;
    border-color: var(--ring-soft);
}
.cpt-skill.disabled .cpt-skill-name { color: var(--fg-mute); }
.cpt-skill.disabled:hover .cpt-skill-name { color: var(--fg-mute); }
.cpt-skill-name {
    color: var(--fg);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.cpt-skill:hover .cpt-skill-name { color: var(--accent); }
.cpt-skill-desc {
    color: var(--fg-mute);
    font-size: 0.6rem;
    letter-spacing: 0.02em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    line-height: 1.3;
}

/* Reveal body after PREMIUM_CSS parses — overrides pre-hide from earlier inline style. */
body { opacity: 1; transition: opacity 0.18s ease-out; }
</style>
"""

# ═══════════════════════════════════════════════════════════
# BOOT ANIMATION CSS — injected only on first render of a session.
# Prevents animations replaying on every Streamlit rerun (button clicks etc).
# ═══════════════════════════════════════════════════════════
BOOT_ANIMATION_CSS = """
<style>
@keyframes boot-rise {
    0%   { opacity: 0; transform: translateY(28px) scale(0.96); }
    100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes boot-slide-l {
    0%   { opacity: 0; transform: translateX(-40px); }
    100% { opacity: 1; transform: translateX(0); }
}
@keyframes boot-slide-r {
    0%   { opacity: 0; transform: translateX(40px); }
    100% { opacity: 1; transform: translateX(0); }
}
.title-row {
    animation: boot-rise 0.75s cubic-bezier(0.22, 1, 0.36, 1) 0s both;
}
.quicknav {
    animation: boot-rise 0.75s cubic-bezier(0.22, 1, 0.36, 1) 0.18s both;
}
[data-testid="stColumn"]:nth-of-type(1) .gauge-card,
[data-testid="column"]:nth-of-type(1) .gauge-card {
    animation: boot-slide-l 1.45s cubic-bezier(0.22, 1, 0.36, 1) 0.55s both;
}
[data-testid="stColumn"]:nth-of-type(2) .gauge-card,
[data-testid="column"]:nth-of-type(2) .gauge-card {
    animation: boot-rise 1.45s cubic-bezier(0.22, 1, 0.36, 1) 0.80s both;
}
[data-testid="stColumn"]:nth-of-type(3) .gauge-card,
[data-testid="column"]:nth-of-type(3) .gauge-card {
    animation: boot-slide-r 1.45s cubic-bezier(0.22, 1, 0.36, 1) 0.55s both;
}
.chart-card {
    animation: boot-rise 0.85s cubic-bezier(0.22, 1, 0.36, 1) 0.55s both;
}
.mcp-strip {
    animation: boot-rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.95s both;
}

/* ── v2 card boot sequence ──
   One soft-rise keyframe reused across every card, staggered by delay.
   TokenBurn gets a "drop-from-100" motion: bar shrinks from 100% to
   target, counter ticks down from 100 to target via CSS @property. */
@keyframes boot-rise-soft {
    0%   { opacity: 0; transform: translateY(10px); }
    100% { opacity: 1; transform: translateY(0); }
}

@keyframes boot-fill-shrink {
    0%   { width: 100%; }
    100% { width: var(--tb-target); }
}
@keyframes boot-endpoint-slide {
    0%   { left: 100%; }
    100% { left: var(--tb-target); }
}
@keyframes boot-comet-slide {
    0%   { left: calc(100% - 80px); width: 80px; }
    100% { left: max(0px, calc(var(--tb-target) - 80px)); width: min(80px, var(--tb-target)); }
}
@keyframes boot-pct-fade-in {
    0%   { opacity: 0; transform: scale(0.88); }
    100% { opacity: 1; transform: scale(1); }
}

/* Shared smooth deceleration curve — expo ease-out, no overshoot.
   Counter-tick animation was removed because Streamlit reruns drop
   BOOT_ANIMATION_CSS (gated by _boot_animated session flag), which
   left the CSS @property + counter() trick blank on rerun. Pct text
   now renders as static int + just fades in alongside the bar. */
.v2-tb-wrap     { animation: boot-rise-soft       0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.05s both; }
.v2-tb-fill     { animation: boot-fill-shrink     1.80s cubic-bezier(0.16, 1, 0.30, 1) 0.45s both; }
.v2-tb-endpoint { animation: boot-endpoint-slide  1.80s cubic-bezier(0.16, 1, 0.30, 1) 0.45s both; }
.v2-tb-comet    { animation: boot-comet-slide     1.80s cubic-bezier(0.16, 1, 0.30, 1) 0.45s both; }
.v2-tb-pct-num  { animation: boot-pct-fade-in     0.80s cubic-bezier(0.16, 1, 0.30, 1) 1.10s both; }

/* Audience row + Latest Upload + marquees + panels — cascading rise */
.v2-latest                { animation: boot-rise-soft 0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.30s both; }
.v2-audience-card         { animation: boot-rise-soft 0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.35s both; }
[data-testid="column"]:nth-of-type(1) .v2-audience-card { animation-delay: 0.30s; }
[data-testid="column"]:nth-of-type(2) .v2-audience-card { animation-delay: 0.36s; }
[data-testid="column"]:nth-of-type(3) .v2-audience-card { animation-delay: 0.42s; }
[data-testid="column"]:nth-of-type(4) .v2-audience-card { animation-delay: 0.48s; }
.v2-ytr-card              { animation: boot-rise-soft 0.60s cubic-bezier(0.22, 1, 0.36, 1) 0.40s both; }
.v2-mb-grid               { animation: boot-rise-soft 0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.30s both; }
.v2-mb-coverage           { animation: boot-rise-soft 0.45s cubic-bezier(0.22, 1, 0.36, 1) 0.20s both; }
.v2-sched-panel           { animation: boot-rise-soft 0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.45s both; }
.v2-thru-panel            { animation: boot-rise-soft 0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.55s both; }
</style>
"""

# Hide body + Streamlit chrome immediately — PREMIUM_CSS reveals body via fade once parsed.
# Kills the brief flash of unstyled cards + Deploy button before CSS attaches.
st.markdown(
    "<style>"
    "body{opacity:0}"
    '[data-testid="stToolbar"],[data-testid="stStatusWidget"],[data-testid="stHeader"],'
    '[data-testid="stDecoration"],#MainMenu,footer,header{display:none!important;height:0!important}'
    "</style>",
    unsafe_allow_html=True,
)
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ───────────────────────────────────────────────────────────────
# V2 cockpit-port CSS — Latest Upload, audience cards, TokenBurn,
# YtWeekReview, MorningBrief, Schedule + Daily Drivers.
# Injected after PREMIUM_CSS so it cascades on top of legacy rules.
# ───────────────────────────────────────────────────────────────
V2_CSS = r"""
<style>
:root {
    /* Mirror Obsidian cockpit's token names (cc-* aliases). Keep legacy var() refs working. */
    --cc-ring:        rgba(250, 249, 245, 0.08);
    --cc-ring-strong: rgba(250, 249, 245, 0.14);
    --cc-fg-0:        #faf9f5;
    --cc-fg-1:        #c6c5be;
    --cc-fg-2:        #87867f;
    --cc-accent:      #c96442;
    --cc-accent-soft: rgba(201, 100, 66, 0.18);
    --cc-accent-bg:   rgba(201, 100, 66, 0.10);

    /* Platform tones — kept saturated but with terracotta-led mix */
    --card-tone-youtube:    rgba(255, 51, 51, 0.10);
    --card-tone-youtube-bd: rgba(255, 51, 51, 0.32);
    --card-tone-instagram:    rgba(225, 48, 108, 0.10);
    --card-tone-instagram-bd: rgba(225, 48, 108, 0.32);
    --card-tone-tiktok:    rgba(0, 240, 255, 0.08);
    --card-tone-tiktok-bd: rgba(0, 240, 255, 0.30);
    --card-tone-claude:    rgba(201, 100, 66, 0.10);
    --card-tone-claude-bd: rgba(201, 100, 66, 0.36);
}

/* All v2 cards use tabular numerics so values lock to a grid */
.v2-latest, .v2-audience-card, .v2-tb-wrap, .v2-ytr-card,
.v2-mb-tile, .v2-panel, .v2-sched-row, .v2-driver-row {
    font-variant-numeric: tabular-nums;
}

/* Streamlit column gap override — tighter packing, mirror cockpit's 10-12px gutters */
[data-testid="stHorizontalBlock"] > [data-testid="column"] {
    padding-left: 6px !important;
    padding-right: 6px !important;
}

/* Terracotta atmosphere — visible crosshatch + grid + radial halos */
.stApp {
    background:
        /* primary 45° crosshatch */
        repeating-linear-gradient(
            45deg,
            rgba(219, 116, 70, 0.070) 0,
            rgba(219, 116, 70, 0.070) 1px,
            transparent 1px,
            transparent 16px
        ),
        /* counter-hatch at -45° */
        repeating-linear-gradient(
            -45deg,
            rgba(219, 116, 70, 0.045) 0,
            rgba(219, 116, 70, 0.045) 1px,
            transparent 1px,
            transparent 16px
        ),
        /* horizontal scanlines */
        repeating-linear-gradient(
            0deg,
            rgba(255, 138, 92, 0.018) 0,
            rgba(255, 138, 92, 0.018) 1px,
            transparent 1px,
            transparent 4px
        ),
        /* top halo behind header */
        radial-gradient(ellipse 80% 40% at 50% 0%, rgba(219, 116, 70, 0.13) 0%, transparent 65%),
        /* bottom-left ambient warmth */
        radial-gradient(circle at 0% 100%, rgba(201, 100, 66, 0.10) 0%, transparent 50%),
        /* bottom-right ambient warmth */
        radial-gradient(circle at 100% 100%, rgba(219, 116, 70, 0.09) 0%, transparent 50%),
        var(--bg) !important;
    background-attachment: fixed !important;
}
/* Card backgrounds opaque-ish so the texture doesn't bleed through */
.v2-latest, .v2-audience-card, .v2-tb-wrap, .v2-ytr-card,
.v2-mb-tile, .v2-panel, .v2-perf-card {
    backdrop-filter: blur(2px);
}

/* ── Latest Upload card ───────────────────────────────────── */
.v2-latest {
    position: relative;
    background: var(--bg-card);
    border: 1px solid var(--cc-ring);
    border-radius: 3px;
    padding: 12px 16px 12px 18px;
    margin: 6px 0 10px 0;
    overflow: hidden;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.v2-latest:hover {
    border-color: rgba(201, 100, 66, 0.45);
    box-shadow:
        inset 0 0 0 1px rgba(201, 100, 66, 0.16),
        0 0 14px -2px rgba(201, 100, 66, 0.18);
}
.v2-latest::before {
    content: "";
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
    background: linear-gradient(180deg, var(--cc-accent) 0%, rgba(201,100,66,0.18) 100%);
}
.v2-latest::after {
    content: "▶";
    position: absolute;
    right: 14px;
    bottom: 6px;
    font-size: 3.2rem;
    line-height: 1;
    color: var(--cc-accent);
    opacity: 0.07;
    pointer-events: none;
    font-family: 'JetBrains Mono', monospace;
}
.v2-latest-head {
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--cc-fg-2);
    margin-bottom: 4px;
}
.v2-latest-head .v2-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--good);
    box-shadow: 0 0 0 2px rgba(143, 185, 122, 0.18), 0 0 8px rgba(143, 185, 122, 0.55);
}
.v2-latest-head .v2-dot.mock  { background: var(--warn);   box-shadow: 0 0 0 2px rgba(217, 165, 102, 0.18), 0 0 8px rgba(217, 165, 102, 0.55); }
.v2-latest-head .v2-dot.err   { background: var(--danger); box-shadow: 0 0 0 2px rgba(181, 51, 51, 0.20),   0 0 8px rgba(181, 51, 51, 0.55); }
.v2-latest-head .v2-dot.stale { background: var(--cc-fg-2); box-shadow: 0 0 0 2px rgba(135, 134, 127, 0.18); }
.v2-latest-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 15px;
    color: var(--cc-fg-0);
    line-height: 1.3;
    margin: 2px 0 6px 0;
    font-weight: 500;
    max-width: 78%;
}
.v2-latest-title a { color: inherit; text-decoration: none; border-bottom: 1px dotted transparent; }
.v2-latest-title a:hover { border-bottom-color: var(--cc-accent); color: var(--cc-accent); }
.v2-latest-stats {
    display: flex;
    gap: 18px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--cc-fg-1);
}
.v2-latest-stats .v2-stat-val { color: var(--cc-fg-0); font-weight: 500; }
.v2-latest-stats .v2-stat-lbl { color: var(--cc-fg-2); margin-left: 4px; font-size: 9px; text-transform: uppercase; letter-spacing: 0.14em; }

/* ── Audience metric cards ───────────────────────────────── */
.v2-audience-card {
    position: relative;
    background: var(--bg-card);
    border: 1px solid var(--cc-ring);
    border-radius: 3px;
    padding: 11px 14px;
    overflow: hidden;
    min-height: 76px;
    transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}
.v2-audience-card:hover {
    border-color: rgba(201, 100, 66, 0.45);
    box-shadow:
        inset 0 0 0 1px rgba(201, 100, 66, 0.16),
        0 0 14px -2px rgba(201, 100, 66, 0.18);
    transform: translateY(-1px);
}
.v2-audience-card[data-tone="youtube"]   { background: linear-gradient(135deg, var(--card-tone-youtube) 0%, var(--bg-card) 70%); border-color: var(--card-tone-youtube-bd); }
.v2-audience-card[data-tone="instagram"] { background: linear-gradient(135deg, var(--card-tone-instagram) 0%, var(--bg-card) 70%); border-color: var(--card-tone-instagram-bd); }
.v2-audience-card[data-tone="tiktok"]    { background: linear-gradient(135deg, var(--card-tone-tiktok) 0%, var(--bg-card) 70%); border-color: var(--card-tone-tiktok-bd); }
.v2-audience-card[data-tone="claude"]    { background: linear-gradient(135deg, var(--card-tone-claude) 0%, var(--bg-card) 70%); border-color: var(--card-tone-claude-bd); }
.v2-audience-watermark {
    position: absolute;
    right: -6px;
    bottom: -16px;
    font-size: 3.4rem;
    line-height: 1;
    opacity: 0.085;
    pointer-events: none;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
}
.v2-audience-head {
    display: flex;
    align-items: center;
    gap: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--cc-fg-2);
    margin-bottom: 4px;
}
.v2-audience-head .v2-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--good);
    box-shadow: 0 0 0 2px rgba(143, 185, 122, 0.18), 0 0 8px rgba(143, 185, 122, 0.55);
}
.v2-audience-head .v2-dot.mock  { background: var(--warn);   box-shadow: 0 0 0 2px rgba(217, 165, 102, 0.18), 0 0 8px rgba(217, 165, 102, 0.55); }
.v2-audience-head .v2-dot.err   { background: var(--danger); box-shadow: 0 0 0 2px rgba(181, 51, 51, 0.20),   0 0 8px rgba(181, 51, 51, 0.55); }
.v2-audience-head .v2-dot.stale { background: var(--cc-fg-2); box-shadow: 0 0 0 2px rgba(135, 134, 127, 0.18); }
.v2-audience-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 26px;
    line-height: 1;
    color: var(--cc-fg-0);
    font-weight: 600;
    margin: 4px 0 4px 0;
    letter-spacing: -0.01em;
}
.v2-audience-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--cc-fg-2);
    letter-spacing: 0.05em;
    text-transform: lowercase;
}

/* ── TokenBurn marquee (mirrors Obsidian cockpit) ───────────── */
.v2-tb-wrap {
    --tb-tone: 219, 116, 70;
    --tb-fill-stop-mid: #e07a48;
    --tb-fill-stop-end: #ff9a5c;
    position: relative;
    background:
        linear-gradient(180deg, rgba(219, 116, 70, 0.14), rgba(219, 116, 70, 0.04) 60%, transparent 100%),
        var(--bg-card);
    border: 1px solid rgba(219, 116, 70, 0.40);
    border-radius: 3px;
    padding: 16px 22px 14px;
    margin: 6px 0 10px 0;
    display: flex;
    flex-direction: column;
    gap: 14px;
    overflow: hidden;
    box-shadow: 0 0 24px -10px rgba(219, 116, 70, 0.40);
}
.v2-tb-wrap::after {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(201, 100, 66, 0.65) 30%, rgba(201, 100, 66, 0.65) 70%, transparent);
}
.v2-tb-wrap.warn { border-color: rgba(217, 165, 102, 0.4); --tb-fill-stop-mid: #e6963c; --tb-fill-stop-end: #ffb05c; }
.v2-tb-wrap.critical {
    border-color: rgba(240, 80, 50, 0.45);
    --tb-fill-stop-mid: #f04f3a; --tb-fill-stop-end: #ff7a4a;
    background:
        linear-gradient(180deg, rgba(240, 80, 50, 0.12), rgba(240, 80, 50, 0.02) 60%, transparent 100%),
        var(--bg-card);
}
.v2-tb-wrap.critical .v2-tb-pct-num { color: #f04f3a; text-shadow: 0 0 16px rgba(240, 80, 50, 0.5); animation: v2-tb-throb 1.2s ease-in-out infinite; }
@keyframes v2-tb-throb { 0%,100%{opacity:1} 50%{opacity:0.7} }

/* HUD corner brackets — 4 explicit spans */
.v2-tb-corner {
    position: absolute;
    width: 12px; height: 12px;
    border-color: var(--cc-accent);
    border-style: solid;
    border-width: 0;
    opacity: 0.7;
    pointer-events: none;
}
.v2-tb-corner.tl { top: 5px; left: 5px;     border-top-width: 1.5px; border-left-width: 1.5px; }
.v2-tb-corner.tr { top: 5px; right: 5px;    border-top-width: 1.5px; border-right-width: 1.5px; }
.v2-tb-corner.bl { bottom: 5px; left: 5px;  border-bottom-width: 1.5px; border-left-width: 1.5px; }
.v2-tb-corner.br { bottom: 5px; right: 5px; border-bottom-width: 1.5px; border-right-width: 1.5px; }
.v2-tb-wrap.critical .v2-tb-corner { border-color: #f04f3a; animation: v2-tb-corner-blink 1.2s ease-in-out infinite; }
@keyframes v2-tb-corner-blink { 0%,100%{opacity:0.4} 50%{opacity:1} }

.v2-tb-head {
    display: flex;
    align-items: baseline;
    gap: 16px;
}
.v2-tb-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: var(--cc-accent);
    font-weight: 600;
}
.v2-tb-live {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--cc-accent);
}
.v2-tb-live-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--cc-accent);
    box-shadow: 0 0 6px rgba(201, 100, 66, 0.8);
    animation: v2-tb-pulse 1.6s ease-in-out infinite;
}
@keyframes v2-tb-pulse {
    0%,100% { opacity: 0.35; transform: scale(0.85); }
    50%     { opacity: 1;    transform: scale(1.15); }
}
.v2-tb-meta {
    margin-left: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--cc-fg-2);
    letter-spacing: 0.06em;
    font-variant-numeric: tabular-nums;
}

/* meter row: pct | bar | counts */
.v2-tb-meter {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 22px;
    align-items: start;
}
.v2-tb-pct {
    display: flex;
    align-items: baseline;
    gap: 2px;
    color: #e07a48;
    font-variant-numeric: tabular-nums;
    text-shadow: 0 0 18px rgba(255, 138, 92, 0.55);
    font-family: 'JetBrains Mono', monospace;
    /* Nudge pct up so its baseline sits on the bar's vertical center
       instead of the bar+ticks group center. 64px line aligned to 38px bar. */
    margin-top: -10px;
}
.v2-tb-counts { align-self: center; }
.v2-tb-pct-num {
    font-size: 64px;
    font-weight: 600;
    letter-spacing: -0.03em;
    line-height: 1;
    /* Lock width to 3 digits + right-align so the counter ticking
       100→10→9→3 doesn't reflow neighbouring elements at the tail
       end of the animation. tabular-nums already inherited from
       .v2-tb-pct ensures fixed-width glyphs. */
    display: inline-block;
    min-width: 1.85em;
    text-align: right;
}
.v2-tb-pct-unit {
    font-size: 22px;
    color: rgba(224, 122, 72, 0.75);
    font-weight: 500;
}
.v2-tb-bar-wrap {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
}
.v2-tb-track {
    position: relative;
    height: 38px;
    border-radius: 2px;
    overflow: hidden;
    isolation: isolate;
    background:
        repeating-linear-gradient(
            135deg,
            rgba(250, 249, 245, 0.025) 0 6px,
            transparent 6px 12px
        ),
        linear-gradient(180deg, rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0.18)),
        var(--bg);
    border: 1px solid rgba(250, 249, 245, 0.06);
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.4);
    margin-top: 0;
}
.v2-tb-track::after {
    content: "";
    position: absolute;
    inset: 4px 0;
    border-radius: 2px;
    background: repeating-linear-gradient(
        90deg,
        transparent 0 calc(5% - 1px),
        rgba(250, 249, 245, 0.12) calc(5% - 1px) 5%
    );
    pointer-events: none;
    z-index: 1;
    -webkit-mask-image: linear-gradient(180deg, transparent 0%, black 25%, black 75%, transparent 100%);
            mask-image: linear-gradient(180deg, transparent 0%, black 25%, black 75%, transparent 100%);
}
.v2-tb-fill {
    position: absolute;
    left: 0; top: 0; bottom: 0;
    border-radius: 2px 0 0 2px;
    background:
        linear-gradient(180deg, rgba(255, 211, 181, 0.28) 0%, transparent 40%),
        linear-gradient(90deg, rgba(var(--tb-tone), 0.70) 0%, var(--tb-fill-stop-mid) 75%, var(--tb-fill-stop-end) 100%);
    box-shadow:
        inset 0 0 14px rgba(255, 154, 92, 0.50),
        0 0 22px rgba(var(--tb-tone), 0.50);
    transition: width 600ms cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
    z-index: 2;
}
.v2-tb-proj {
    position: absolute;
    top: 0; bottom: 0;
    background: repeating-linear-gradient(
        135deg,
        rgba(201, 100, 66, 0.18) 0 6px,
        transparent 6px 12px
    );
    border-top: 1px solid rgba(201, 100, 66, 0.22);
    border-bottom: 1px solid rgba(201, 100, 66, 0.22);
    pointer-events: none;
    transition: width 600ms cubic-bezier(0.4, 0, 0.2, 1), left 600ms cubic-bezier(0.4, 0, 0.2, 1);
}
.v2-tb-scan {
    position: absolute;
    top: 0; bottom: 0;
    width: 50%;
    background: linear-gradient(
        90deg,
        transparent 0%,
        rgba(255, 255, 255, 0.06) 40%,
        rgba(255, 255, 255, 0.12) 50%,
        rgba(255, 255, 255, 0.06) 60%,
        transparent 100%
    );
    animation: v2-scan 4s linear infinite;
    pointer-events: none;
    z-index: 3;
}
@keyframes v2-scan {
    0%   { transform: translateX(-100%); }
    100% { transform: translateX(220%); }
}
.v2-tb-comet {
    position: absolute;
    top: 0; bottom: 0;
    width: 80px;
    max-width: 100%;
    background: linear-gradient(
        90deg,
        transparent 0%,
        rgba(255, 211, 181, 0.05) 30%,
        rgba(255, 211, 181, 0.16) 60%,
        rgba(255, 240, 220, 0.35) 90%,
        rgba(255, 245, 230, 0.55) 100%
    );
    pointer-events: none;
    mix-blend-mode: screen;
    z-index: 2;
}
.v2-tb-endpoint {
    position: absolute;
    top: 0; bottom: 0;
    width: 2px;
    margin-left: -1px;
    background: linear-gradient(180deg, rgba(255, 211, 181, 0.8), var(--cc-accent) 40%, var(--cc-accent) 60%, rgba(255, 211, 181, 0.8));
    box-shadow: 0 0 8px rgba(255, 138, 92, 0.6);
    pointer-events: none;
    z-index: 4;
}
.v2-tb-ticks {
    display: flex;
    justify-content: space-between;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    color: var(--cc-fg-2);
    margin-top: 4px;
    letter-spacing: 0.08em;
}
.v2-tb-counts {
    text-align: right;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--cc-fg-1);
    line-height: 1.5;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
.v2-tb-counts .v2-tb-used { color: var(--cc-fg-0); font-size: 14px; font-weight: 500; }
.v2-tb-counts .v2-tb-proj-label { color: var(--cc-accent); font-size: 10px; letter-spacing: 0.06em; }

/* ── YtWeekReview card ────────────────────────────────────── */
.v2-ytr-card {
    background: var(--bg-card);
    border: 1px solid var(--cc-ring);
    border-radius: 3px;
    padding: 14px 18px 14px 18px;
    margin: 6px 0 10px 0;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.v2-ytr-card:hover {
    border-color: rgba(201, 100, 66, 0.32);
    box-shadow: 0 0 18px -8px rgba(201, 100, 66, 0.30);
}
.v2-ytr-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 8px;
}
.v2-ytr-head .v2-ytr-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--cc-fg-2);
}
.v2-ytr-head .v2-ytr-actions {
    display: flex;
    gap: 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
}
.v2-ytr-head .v2-ytr-actions a {
    color: var(--cc-accent);
    text-decoration: none;
    letter-spacing: 0.14em;
    text-transform: uppercase;
}
.v2-ytr-head .v2-ytr-actions a:hover { text-decoration: underline; }
.v2-ytr-tldr {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--cc-fg-1);
    line-height: 1.5;
    margin: 4px 0 8px 0;
    padding-left: 16px;
}
.v2-ytr-tldr li { margin: 3px 0; }
.v2-chip-row {
    display: flex; gap: 6px;
    margin: 6px 0;
    flex-wrap: wrap;
}
.v2-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border: 1px solid var(--cc-ring);
    border-radius: 99px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--cc-fg-2);
    background: var(--bg-elev);
}
.v2-chip.hit       { color: var(--good); border-color: rgba(143,185,122,0.4); }
.v2-chip.steady    { color: var(--cc-fg-1); }
.v2-chip.climbing  { color: var(--warn); border-color: rgba(217,165,102,0.4); }
.v2-chip.miss      { color: var(--cc-accent); border-color: rgba(201,100,66,0.4); }
.v2-ytr-perfs {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-top: 8px;
}
.v2-perf-card {
    border: 1px solid var(--cc-ring);
    border-radius: 3px;
    padding: 9px 11px;
    background: var(--bg-elev);
}
.v2-perf-card.top { border-left: 3px solid var(--good); }
.v2-perf-card.under { border-left: 3px solid var(--cc-accent); }
.v2-perf-card .v2-perf-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--cc-fg-2);
}
.v2-perf-card .v2-perf-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--cc-fg-0);
    margin: 3px 0;
    line-height: 1.35;
}

/* ── MorningBrief 2x2 grid ───────────────────────────────── */
.v2-mb-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin: 6px 0 10px 0;
}
.v2-mb-tile {
    background: var(--bg-card);
    border: 1px solid var(--cc-ring);
    border-radius: 3px;
    padding: 11px 14px;
    min-height: 120px;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.v2-mb-tile:hover {
    border-color: rgba(201, 100, 66, 0.32);
    box-shadow: 0 0 14px -8px rgba(201, 100, 66, 0.30);
}
.v2-mb-tile .v2-mb-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--cc-fg-2);
    margin-bottom: 6px;
}
.v2-mb-tile ul {
    margin: 0;
    padding-left: 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--cc-fg-0);
    line-height: 1.5;
}
.v2-mb-tile li { margin: 3px 0; }
.v2-mb-coverage {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--cc-fg-2);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 8px;
}
.v2-mb-coverage span { padding: 3px 9px; border: 1px solid var(--cc-ring); border-radius: 99px; }

/* ── Schedule + Daily Drivers ─────────────────────────────── */
.v2-panel {
    background: var(--bg-card);
    border: 1px solid rgba(201, 100, 66, 0.28);
    border-radius: 3px;
    padding: 14px 18px 16px;
    box-shadow: 0 0 18px -8px rgba(201, 100, 66, 0.35);
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.v2-panel:hover {
    border-color: rgba(201, 100, 66, 0.45);
    box-shadow: 0 0 22px -8px rgba(201, 100, 66, 0.50);
}
.v2-panel-head {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--cc-fg-2);
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
}
.v2-sched-list {
    column-count: 2;
    column-gap: 24px;
    column-rule: 1px dashed var(--cc-ring);
}
.v2-sched-row {
    display: grid;
    grid-template-columns: 52px 1fr;
    gap: 10px;
    align-items: center;
    padding: 5px 0;
    border-bottom: 1px dashed var(--cc-ring);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.4;
    break-inside: avoid;
}
.v2-sched-row:last-child { border-bottom: none; }
.v2-sched-row .v2-sched-time { color: var(--cc-accent); font-weight: 500; }
.v2-sched-row .v2-sched-label { color: var(--cc-fg-0); }
.v2-driver-row {
    display: grid;
    grid-template-columns: 16px 1fr;
    gap: 10px;
    align-items: center;
    padding: 6px 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--cc-fg-0);
}
.v2-driver-row .v2-driver-box {
    width: 14px; height: 14px;
    border: 1px solid var(--cc-ring-strong);
    border-radius: 2px;
    display: inline-block;
    text-align: center;
    line-height: 12px;
    font-size: 11px;
    color: var(--cc-accent);
}
.v2-driver-row.done .v2-driver-box { background: var(--cc-accent); color: var(--bg); border-color: var(--cc-accent); }
.v2-driver-row.done .v2-driver-label { color: var(--cc-fg-2); text-decoration: line-through; }

/* ── Throughput + Schedule panels — matched heights ─────── */
.v2-sched-panel, .v2-thru-panel {
    min-height: 240px;
    display: flex;
    flex-direction: column;
    padding: 16px 20px 14px;
}
.v2-sched-panel .v2-panel-head,
.v2-thru-panel .v2-panel-head {
    margin-bottom: 8px;
}
.v2-sched-panel > .v2-sched-list,
.v2-sched-panel > .v2-sched-list-single { flex: 1 1 auto; }
.v2-thru-panel .v2-panel-head {
    justify-content: space-between;
}
.v2-thru-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.06em;
    color: var(--cc-fg-2);
    text-transform: none;
    font-variant-numeric: tabular-nums;
}
.v2-thru-svg {
    margin: 6px -6px 0 -6px;
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    justify-content: stretch;
}
.v2-thru-svg .activity-chart-wrap { margin: 0; flex: 1 1 auto; display: flex; flex-direction: column; }
.v2-thru-svg .activity-svg { height: 160px; width: 100%; flex: 1 1 auto; }
.v2-thru-svg .activity-axis {
    font-size: 9px;
    color: var(--cc-fg-2);
    margin-top: 4px;
    padding: 0 4px;
}

/* Native st.checkbox style override for Daily Drivers — write-back enabled. */
.v2-panel-drivers-head {
    /* the panel-head card sits directly above the checkbox stack so they read as one block */
    margin-bottom: 6px !important;
    padding-bottom: 8px;
}
[data-testid="stCheckbox"] {
    padding: 4px 0 !important;
    font-family: 'JetBrains Mono', monospace !important;
}
[data-testid="stCheckbox"] label {
    font-size: 12px !important;
    font-family: 'JetBrains Mono', monospace !important;
    color: var(--cc-fg-0) !important;
    align-items: center !important;
    gap: 10px !important;
}
[data-testid="stCheckbox"] label p {
    font-size: 12px !important;
    line-height: 1.4 !important;
    color: var(--cc-fg-0) !important;
    margin: 0 !important;
}
[data-testid="stCheckbox"] label > div:first-child {
    margin-right: 0 !important;
}
/* The square */
[data-testid="stCheckbox"] [role="checkbox"],
[data-testid="stCheckbox"] [data-baseweb="checkbox"] > div:first-child {
    width: 14px !important;
    height: 14px !important;
    min-width: 14px !important;
    border-radius: 2px !important;
    border: 1px solid var(--cc-ring-strong) !important;
    background: transparent !important;
}
[data-testid="stCheckbox"] [aria-checked="true"],
[data-testid="stCheckbox"] [data-baseweb="checkbox"] > div[data-checked="true"] {
    background: var(--cc-accent) !important;
    border-color: var(--cc-accent) !important;
}
[data-testid="stCheckbox"] [aria-checked="true"] + div p,
[data-testid="stCheckbox"]:has([aria-checked="true"]) label p {
    color: var(--cc-fg-2) !important;
    text-decoration: line-through;
}

/* Quicknav pull pill — terracotta-tinted, matches status chip footprint */
.quicknav .qn-pull {
    background: rgba(219, 116, 70, 0.10);
    color: var(--cc-accent) !important;
    border: 1px solid rgba(219, 116, 70, 0.32);
}
.quicknav .qn-pull:hover {
    background: rgba(219, 116, 70, 0.22);
    border-color: rgba(219, 116, 70, 0.55);
    box-shadow: 0 0 10px -2px rgba(219, 116, 70, 0.45);
}

/* ── Demo-mode pill ───────────────────────────────────────── */
.v2-demo-pill {
    display: inline-block;
    padding: 2px 8px;
    background: var(--cc-accent-soft);
    color: var(--cc-accent);
    border: 1px solid rgba(201,100,66,0.4);
    border-radius: 99px;
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    font-weight: 500;
}
</style>
"""
st.markdown(V2_CSS, unsafe_allow_html=True)

# Boot animations only on fresh page mount — not on every Streamlit rerun (button clicks).
# Session state persists per tab; fresh Ctrl+R creates a new session → animation replays.
if not st.session_state.get("_boot_animated"):
    st.session_state._boot_animated = True
    st.markdown(BOOT_ANIMATION_CSS, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@st.cache_resource
def _asset_data_url(filename: str) -> str:
    p = Path(__file__).parent / "assets" / filename
    if not p.exists():
        return ""
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


MASCOT_IDLE_URL = _asset_data_url("robot-idle-normalized.png")
MASCOT_RUN_URL = _asset_data_url("robot-run-normalized.png")
# 7 frames per row, 12×32 px each → sheet is 84×32 native.
MASCOT_FRAMES = 7
MASCOT_FRAME_W = 12
MASCOT_FRAME_H = 32
MASCOT_SCALE = 3  # rendered at 36×96 px (scaled 3×)


PHASE_LABELS = {
    "Read": "reading file",
    "Write": "writing file",
    "Edit": "editing file",
    "MultiEdit": "editing file",
    "Bash": "running command",
    "Glob": "finding files",
    "Grep": "searching code",
    "Task": "delegating subagent",
    "Agent": "spawning agent",
    "TodoWrite": "tracking tasks",
    "WebFetch": "fetching page",
    "WebSearch": "searching web",
    "NotebookEdit": "editing notebook",
    "Skill": "invoking skill",
    "ToolSearch": "searching tools",
    "EnterPlanMode": "entering plan mode",
    "ExitPlanMode": "exiting plan mode",
    "EnterWorktree": "entering worktree",
    "ExitWorktree": "exiting worktree",
    "ScheduleWakeup": "scheduling wakeup",
    "SendMessage": "sending message",
    "TaskCreate": "creating task",
    "TaskUpdate": "updating task",
    "TaskGet": "reading task",
    "TaskList": "listing tasks",
    "TaskStop": "stopping task",
    "TaskOutput": "reading task output",
    "AskUserQuestion": "asking question",
    "PushNotification": "sending notification",
    "RemoteTrigger": "triggering remote",
    "Monitor": "monitoring process",
    "CronCreate": "creating schedule",
    "CronDelete": "deleting schedule",
    "CronList": "listing schedules",
    "TeamCreate": "creating team",
    "TeamDelete": "deleting team",
}


def pretty_phase(name: str) -> str:
    if not name:
        return "starting"
    if name in PHASE_LABELS:
        return PHASE_LABELS[name]
    if name.startswith("mcp__"):
        parts = name.split("__")
        if len(parts) >= 3:
            service = parts[1].replace("_", " ")
            action = "__".join(parts[2:]).replace("_", " ")
            return f"{service} · {action}"
    # CamelCase → spaced, lowercase
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()
    return spaced or name


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s or "run"


def today_daily_note() -> Path:
    return DAILY_NOTES_DIR / f"{date.today().isoformat()}.md"


def read_activity() -> str:
    note = today_daily_note()
    if not note.exists():
        return "_No activity yet today._"
    return note.read_text(encoding="utf-8", errors="replace")


def log_run(label: str, ok: bool):
    note = today_daily_note()
    note.parent.mkdir(parents=True, exist_ok=True)
    if not note.exists():
        note.write_text(f"# {date.today().isoformat()}\n\n## Runs\n\n", encoding="utf-8")
    status = "OK" if ok else "ERR"
    stamp = datetime.now().strftime("%H:%M")
    with note.open("a", encoding="utf-8") as f:
        f.write(f"- {stamp} [{status}] {label}\n")


def save_run_output(label: str, prompt: str, output: str, meta: dict | None = None) -> Path:
    today_str = date.today().isoformat()
    now = datetime.now().strftime("%H-%M")
    day_dir = RUNS_DIR / today_str
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{now}-{slugify(label)}.md"
    meta_block = ""
    if meta:
        for k, v in meta.items():
            if v is not None:
                meta_block += f"{k}: {v}\n"
    body = (
        f"---\nskill: {label}\ntime: {datetime.now().isoformat(timespec='seconds')}\n"
        f"{meta_block}---\n\n"
        f"**Prompt**\n\n```\n{prompt}\n```\n\n"
        f"**Output**\n\n{output}\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def obsidian_uri(vault_path: Path) -> str:
    rel = vault_path.relative_to(VAULT_PATH).as_posix()
    return f"obsidian://open?vault={quote(VAULT_NAME)}&file={quote(rel)}"


def open_claude_terminal() -> None:
    wt = Path(r"C:\Users\Chase\AppData\Local\Microsoft\WindowsApps\wt.exe")
    if wt.exists():
        subprocess.Popen(
            [str(wt), "-d", str(VAULT_PATH), str(CLAUDE_CLI)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    else:
        subprocess.Popen(
            ["cmd.exe", "/k", f'cd /d "{VAULT_PATH}" && "{CLAUDE_CLI}"'],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )


def list_recent_runs(limit: int = 10):
    if not RUNS_DIR.exists():
        return []
    files = sorted(RUNS_DIR.glob("*/*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def list_awaiting_approvals():
    if not DRAFTS_AWAITING.exists():
        return []
    return sorted(DRAFTS_AWAITING.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)


def list_vault_pulse(limit: int = 6):
    """Recent vault .md changes, sorted by mtime desc. Verb inferred from mtime-vs-ctime delta."""
    if not VAULT_PATH.exists():
        return []
    skip_parts = {".obsidian", ".trash", "node_modules", ".git"}
    files = []
    for p in VAULT_PATH.rglob("*.md"):
        if any(part in skip_parts for part in p.parts):
            continue
        try:
            st_ = p.stat()
        except OSError:
            continue
        files.append((p, st_))
    files.sort(key=lambda t: t[1].st_mtime, reverse=True)
    files = files[:limit]

    now = time.time()
    out = []
    for p, st_ in files:
        age = now - st_.st_mtime
        # verb inference: created if mtime ~= ctime (within 2 min),
        # linked if file contains wiki-links and was touched recently,
        # appended if touched in last 10 min, else updated.
        created_delta = abs(st_.st_mtime - st_.st_ctime)
        has_wikilink = False
        if age < 900:
            try:
                has_wikilink = "[[" in p.read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                pass
        if created_delta < 120:
            verb = "created"
        elif has_wikilink and age < 300:
            verb = "linked"
        elif age < 600:
            verb = "appended"
        else:
            verb = "updated"
        try:
            rel = p.relative_to(VAULT_PATH).as_posix()
        except ValueError:
            rel = p.name
        directory = str(Path(rel).parent).replace("\\", "/")
        if directory == ".":
            directory = "vault"
        out.append({
            "verb": verb,
            "name": p.stem,
            "dir": directory,
            "age_sec": int(age),
            "path": p,
        })
    return out


def fmt_ago(sec: int) -> str:
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m"
    if sec < 86400:
        return f"{sec // 3600}h"
    return f"{sec // 86400}d"


# ─── Metrics / chart data / MCP cache ───

CACHE_DIR = Path(__file__).parent / ".cache"
MCP_CACHE = CACHE_DIR / "mcp.json"
RATE_CACHE = CACHE_DIR / "rate_limits.json"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")[:2500]
    meta = {"file": path.name, "path": str(path)}
    m = _FRONTMATTER_RE.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    return meta


def scan_runs(days: int = 30) -> list[dict]:
    if not RUNS_DIR.exists():
        return []
    cutoff = date.today() - timedelta(days=days)
    out = []
    for day_dir in RUNS_DIR.iterdir():
        if not day_dir.is_dir():
            continue
        try:
            d = date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        if d < cutoff:
            continue
        for f in day_dir.glob("*.md"):
            meta = _parse_frontmatter(f)
            meta["date"] = d.isoformat()
            out.append(meta)
    return out


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def calc_metrics() -> dict:
    runs = scan_runs(30)
    today_str = date.today().isoformat()
    month_str = date.today().strftime("%Y-%m")
    runs_today = sum(1 for r in runs if r.get("date") == today_str)
    cost_month = sum(
        _to_float(r.get("cost_usd"))
        for r in runs if (r.get("date") or "").startswith(month_str)
    )
    tokens_30d = sum(
        _to_int(r.get("tokens_in")) + _to_int(r.get("tokens_out"))
        for r in runs
    )
    approvals = len(list_awaiting_approvals())
    return {
        "runs_today": runs_today,
        "cost_month": cost_month,
        "tokens_30d": tokens_30d,
        "approvals": approvals,
    }


def runs_per_day(days: int = 14) -> pd.DataFrame:
    today = date.today()
    counts = {(today - timedelta(days=i)).isoformat(): 0 for i in range(days - 1, -1, -1)}
    for r in scan_runs(days):
        if r.get("date") in counts:
            counts[r["date"]] += 1
    df = pd.DataFrame([{"date": k, "runs": v} for k, v in counts.items()])
    df["date"] = pd.to_datetime(df["date"])
    return df


def tokens_per_day(days: int = 14) -> pd.DataFrame:
    today = date.today()
    buckets = {(today - timedelta(days=i)).isoformat(): 0 for i in range(days - 1, -1, -1)}
    for m in _read_session_metas():
        t = _parse_session_time(m)
        if t is None:
            continue
        k = t.date().isoformat()
        if k in buckets:
            buckets[k] += int(m.get("input_tokens") or 0) + int(m.get("output_tokens") or 0)
    df = pd.DataFrame([{"date": k, "tokens": v} for k, v in buckets.items()])
    df["date"] = pd.to_datetime(df["date"])
    return df


def compute_delta(current: float, prior: float, threshold_pct: float = 5.0) -> tuple[str, float, str]:
    if prior <= 0 and current <= 0:
        return ("·", 0.0, "neutral")
    if prior <= 0:
        return ("▲", 100.0, "up")
    pct = (current - prior) / prior * 100.0
    if abs(pct) < threshold_pct:
        return ("·", pct, "neutral")
    return (("▲", pct, "up") if pct > 0 else ("▼", pct, "down"))


def activity_cumulative(days: int = 30, backfill_demo: bool = True) -> pd.DataFrame:
    """Daily count of (scan_runs + routines ledger) → cumulative sum.

    backfill_demo seeds synthetic activity on empty early days so the cumulative
    curve ramps smoothly instead of flatlining at 0 until recent spike.
    """
    import random
    today = date.today()
    per_day = {(today - timedelta(days=i)).isoformat(): 0 for i in range(days - 1, -1, -1)}
    for r in scan_runs(days):
        d = r.get("date")
        if d in per_day:
            per_day[d] += 1
    ledger = _load_routines_ledger()
    for d in per_day:
        per_day[d] += int(ledger.get(d, 0))

    if backfill_demo:
        keys = list(per_day.keys())
        n = len(keys)
        rng = random.Random(0xA6E8)
        for i, k in enumerate(keys):
            if per_day[k] == 0 and i < n - 3:
                t = i / max(1, n - 1)
                base = 1.8 + t * 6.0
                jitter = rng.uniform(-1.2, 1.6)
                per_day[k] = max(1, int(round(base + jitter)))

    df = pd.DataFrame(
        [{"date": k, "day_count": v} for k, v in per_day.items()]
    )
    df["date"] = pd.to_datetime(df["date"])
    df["cumulative"] = df["day_count"].cumsum()
    return df


def delta_window(metas: list[dict], cur_start: datetime, cur_end: datetime,
                 pri_start: datetime, pri_end: datetime) -> tuple[int, int]:
    cur = pri = 0
    for m in metas:
        t = _parse_session_time(m)
        if t is None:
            continue
        tot = int(m.get("input_tokens") or 0) + int(m.get("output_tokens") or 0)
        if cur_start <= t < cur_end:
            cur += tot
        elif pri_start <= t < pri_end:
            pri += tot
    return cur, pri


def save_mcp_state(servers: list):
    CACHE_DIR.mkdir(exist_ok=True)
    try:
        MCP_CACHE.write_text(json.dumps(servers), encoding="utf-8")
    except Exception:
        pass


def load_mcp_state() -> list:
    if MCP_CACHE.exists():
        try:
            return json.loads(MCP_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_rate_limit(event: dict):
    """Persist latest rate_limit_info keyed by rateLimitType."""
    CACHE_DIR.mkdir(exist_ok=True)
    info = event.get("rate_limit_info") or {}
    kind = info.get("rateLimitType")
    if not kind:
        return
    data = load_rate_limits()
    data[kind] = {
        "status": info.get("status"),
        "resets_at": info.get("resetsAt"),
        "overage_status": info.get("overageStatus"),
        "overage_resets_at": info.get("overageResetsAt"),
        "is_using_overage": info.get("isUsingOverage"),
        "captured_at": int(time.time()),
    }
    try:
        RATE_CACHE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def load_rate_limits() -> dict:
    if RATE_CACHE.exists():
        try:
            return json.loads(RATE_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def fmt_time_until(ts: int) -> str:
    if not ts:
        return "—"
    delta = int(ts - time.time())
    if delta <= 0:
        return "now"
    h = delta // 3600
    m = (delta % 3600) // 60
    if h > 24:
        d = h // 24
        h = h % 24
        return f"{d}d {h}h"
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def _read_session_metas() -> list[dict]:
    """Read all Claude Code per-session usage meta files."""
    if not SESSION_META_DIR.exists():
        return []
    out = []
    for f in SESSION_META_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8", errors="replace"))
            if "start_time" in d and ("input_tokens" in d or "output_tokens" in d):
                out.append(d)
        except Exception:
            continue
    return out


def _parse_session_time(d: dict) -> datetime | None:
    t = d.get("start_time")
    if not t:
        return None
    try:
        if t.endswith("Z"):
            t = t.replace("Z", "+00:00")
        dt = datetime.fromisoformat(t)
        return dt.replace(tzinfo=None)  # naive local
    except Exception:
        return None


def calc_usage_windows() -> dict:
    """Aggregate Claude Code session token usage across 5h, 7d, today windows."""
    now = datetime.now()
    five_h_ago = now - timedelta(hours=5)
    seven_d_ago = now - timedelta(days=7)
    today_start = datetime.combine(date.today(), datetime.min.time())

    metas = _read_session_metas()

    def agg(metas_list, since):
        in_tok = out_tok = sessions = 0
        for m in metas_list:
            t = _parse_session_time(m)
            if t is None or t < since:
                continue
            in_tok += int(m.get("input_tokens") or 0)
            out_tok += int(m.get("output_tokens") or 0)
            sessions += 1
        return {"input": in_tok, "output": out_tok, "total": in_tok + out_tok, "sessions": sessions}

    # Local dashboard button runs (manual)
    runs_today = [r for r in scan_runs(2) if r.get("date") == date.today().isoformat()]
    cost_today = sum(_to_float(r.get("cost_usd")) for r in runs_today)

    # Routine runs today — cloud routines, tracked via local ledger
    routine_count = count_routines_today()

    return {
        "five_hour": agg(metas, five_h_ago),
        "weekly": agg(metas, seven_d_ago),
        "today": {
            **agg(metas, today_start),
            "routines": routine_count,
            "cost": cost_today,
            "runs": len(runs_today),
        },
    }


# ─── Routine run ledger ───
ROUTINES_LEDGER = CACHE_DIR / "routines.json"


def _load_routines_ledger() -> dict:
    if ROUTINES_LEDGER.exists():
        try:
            return json.loads(ROUTINES_LEDGER.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_routines_ledger(data: dict):
    CACHE_DIR.mkdir(exist_ok=True)
    ROUTINES_LEDGER.write_text(json.dumps(data), encoding="utf-8")


def count_routines_today() -> int:
    today_str = date.today().isoformat()
    return int(_load_routines_ledger().get(today_str, 0))


def increment_routine_count():
    today_str = date.today().isoformat()
    data = _load_routines_ledger()
    data[today_str] = int(data.get(today_str, 0)) + 1
    _save_routines_ledger(data)


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_cost(c: float) -> str:
    if c >= 100:
        return f"${c:.0f}"
    if c >= 10:
        return f"${c:.1f}"
    return f"${c:.2f}"


# ═══════════════════════════════════════════════════════════
# BACKGROUND RUNNER — parses stream-json events from claude CLI
# ═══════════════════════════════════════════════════════════


def _parse_event(evt: dict):
    """Mutate RT based on one stream-json event."""
    t = evt.get("type")
    if t == "assistant":
        msg = evt.get("message", {})
        for block in msg.get("content", []):
            btype = block.get("type")
            if btype == "text":
                RT["text"] += block.get("text", "")
            elif btype == "tool_use":
                name = block.get("name", "tool")
                RT["phases"].append(name)
                RT["current_phase"] = name
    elif t == "user":
        # tool results; don't need full content
        pass
    elif t == "result":
        RT["cost_usd"] = evt.get("total_cost_usd") or evt.get("cost_usd")
        usage = evt.get("usage", {})
        RT["tokens_in"] = usage.get("input_tokens")
        RT["tokens_out"] = usage.get("output_tokens")
        if evt.get("subtype") != "success":
            RT["error"] = evt.get("result") or evt.get("subtype")
    elif t == "system":
        sub = evt.get("subtype")
        if sub == "init":
            RT["current_phase"] = "initializing"
            servers = evt.get("mcp_servers")
            if servers:
                save_mcp_state(servers)
    elif t == "rate_limit_event":
        save_rate_limit(evt)


def _run_skill_bg(prompt: str):
    """Subprocess runner (runs in background thread). Populates RT."""
    try:
        proc = subprocess.Popen(
            [
                str(CLAUDE_CLI),
                "-p",
                prompt,
                "--permission-mode",
                PERMISSION_MODE,
                "--output-format",
                "stream-json",
                "--verbose",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(VAULT_PATH),
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
        RT["proc"] = proc

        for line in iter(proc.stdout.readline, ""):
            line = line.strip()
            if not line:
                continue
            RT["buffer"].append(line)
            try:
                evt = json.loads(line)
                _parse_event(evt)
            except json.JSONDecodeError:
                # plaintext line (maybe error before JSON starts)
                RT["text"] += line + "\n"

        proc.wait(timeout=RUN_TIMEOUT_SEC)
        if proc.returncode != 0 and not RT.get("error"):
            stderr_text = proc.stderr.read() if proc.stderr else ""
            RT["error"] = f"exit {proc.returncode}: {stderr_text[:500]}"
    except Exception as e:
        RT["error"] = str(e)
    finally:
        RT["done"] = True
        RT["proc"] = None


def start_skill_run(label: str, prompt: str):
    reset_runtime()
    RT["start_time"] = time.time()
    thread = threading.Thread(target=_run_skill_bg, args=(prompt,), daemon=True)
    thread.start()
    st.session_state.running = True
    st.session_state.active_skill = label
    st.session_state.active_prompt = prompt
    st.session_state.last_error = None


def cancel_current_run():
    proc = RT.get("proc")
    if proc:
        try:
            proc.terminate()
            time.sleep(0.2)
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
    RT["cancelled"] = True
    RT["error"] = "cancelled by user"
    RT["done"] = True


def finalize_run_if_done(label: str, prompt: str):
    """Called when RT['done']==True. Persists output, resets session state."""
    if RT.get("cancelled"):
        st.session_state.last_output = "(cancelled)"
        st.session_state.last_saved_path = None
        st.session_state.last_error = None
    elif RT.get("error"):
        st.session_state.last_error = str(RT["error"])
        st.session_state.last_output = RT.get("text", "").strip()
        st.session_state.last_saved_path = None
        log_run(label, ok=False)
    else:
        output = RT.get("text", "").strip() or "(no text output)"
        st.session_state.last_output = output
        meta = {
            "cost_usd": RT.get("cost_usd"),
            "tokens_in": RT.get("tokens_in"),
            "tokens_out": RT.get("tokens_out"),
            "phases": ", ".join(RT.get("phases", [])) or None,
        }
        saved = save_run_output(label, prompt, output, meta=meta)
        st.session_state.last_saved_path = str(saved)
        st.session_state.last_cost = RT.get("cost_usd")
        st.session_state.last_tokens = (RT.get("tokens_in"), RT.get("tokens_out"))
        log_run(label, ok=True)

    st.session_state.running = False
    st.session_state.active_skill = None


# ═══════════════════════════════════════════════════════════
# FIRST-RUN WIZARD
# ═══════════════════════════════════════════════════════════

if not VAULT_PATH.exists():
    st.markdown('<h1 class="hero-title">Agentic <em>OS</em></h1>', unsafe_allow_html=True)
    st.error(f"Vault not found: `{VAULT_PATH}`")
    st.markdown(
        "**Setup required.** Edit `config.py` and set:\n\n"
        "- `VAULT_PATH` → your Obsidian vault directory\n"
        "- `VAULT_NAME` → vault name as Obsidian shows it\n"
        "- `CLAUDE_CLI` → path to `claude.exe`\n\n"
        "Then reload this page."
    )
    st.stop()

if not CLAUDE_CLI.exists():
    st.error(f"Claude CLI not found at `{CLAUDE_CLI}`. Check config.py.")
    st.stop()


# ═══════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════

defaults = {
    "running": False,
    "last_output": "",
    "last_label": "",
    "last_saved_path": None,
    "last_prompt": None,
    "last_cost": None,
    "last_tokens": None,
    "last_error": None,
    "active_skill": None,
    "active_prompt": None,
    "skill_search": "",
    "output_view_md": True,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ═══════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════

st.markdown('<div class="cpt-header-marker"></div>', unsafe_allow_html=True)

# Quicknav query-param actions: terminal launch + metrics-pull queue
_action_q = st.query_params.get("action")
if _action_q == "terminal":
    try:
        open_claude_terminal()
        st.toast("Terminal opened at vault.", icon="✅")
    except Exception as e:
        st.toast(f"Failed: {e}", icon="⚠️")
    st.query_params.clear()
elif _action_q == "pull-latest":
    try:
        uid, _ = write_queue_intent("metrics-pull")
        st.toast(f"queued metrics-pull · {uid[:8]}", icon="✅")
    except Exception as e:
        st.toast(f"pull failed: {e}", icon="⚠️")
    st.query_params.clear()

if MASCOT_IDLE_URL:
    _mascot_html = (
        f'<span class="mascot" '
        f'style="--idle:url({MASCOT_IDLE_URL}); '
        f'--run:url({MASCOT_RUN_URL});"></span>'
    )
else:
    _mascot_html = ""
st.markdown(
    '<div class="title-row">'
    '<h1 class="hero-title">'
    f'{_mascot_html}'
    '<span class="hero-word">Agentic</span>'
    '<em>OS</em>'
    '</h1>'
    f'<div class="caption-mono title-crumb">vault · {VAULT_PATH.name} · plan · {CLAUDE_PLAN} · permission · {PERMISSION_MODE}'
    f'{"&nbsp;&nbsp;<span class=\"v2-demo-pill\">demo mode</span>" if getattr(_cfg, "DEMO_MODE", False) else ""}'
    f'</div>'
    '</div>',
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════
# QUICK-NAV PILLS  (claude code · vault · daily · runs · drafts · [status])
# ═══════════════════════════════════════════════════════════

today_note = today_daily_note()
today_runs_dir = RUNS_DIR / date.today().isoformat()

vault_uri = f"obsidian://open?vault={quote(VAULT_NAME)}"
daily_note_uri = obsidian_uri(today_note) if today_note.exists() else vault_uri
runs_folder_uri = f"obsidian://open?vault={quote(VAULT_NAME)}&file={quote('dashboard-runs')}"
drafts_folder_uri = f"obsidian://open?vault={quote(VAULT_NAME)}&file={quote('drafts/awaiting')}"

if st.session_state.running:
    _active = st.session_state.active_skill or "skill"
    _status_html = (
        f'<div class="status-chip running qn-status">'
        f'<span class="pulse-dot small"></span>{_active}</div>'
    )
else:
    _status_html = (
        '<div class="status-chip qn-status">'
        '<span class="pulse-dot idle small"></span>idle</div>'
    )

st.markdown(
    f"""
    <div class="quicknav">
        <a class="qn-claude" href="?action=terminal" target="_self">
            <span class="qn-icon">◆</span>claude code<span class="qn-arrow">↗</span>
        </a>
        <a href="{vault_uri}" target="_blank"><span class="qn-icon">✱</span>vault</a>
        <a href="{daily_note_uri}" target="_blank"><span class="qn-icon">§</span>daily note</a>
        <a href="{runs_folder_uri}" target="_blank"><span class="qn-icon">¶</span>runs folder</a>
        <a href="{drafts_folder_uri}" target="_blank"><span class="qn-icon">※</span>drafts</a>
        <a class="qn-pull" href="?action=pull-latest" target="_self" title="Queue /metrics-pull skill"><span class="qn-icon">↻</span>pull</a>
        {_status_html}
    </div>
    """,
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════
# USAGE GAUGES + APPROVALS
# ═══════════════════════════════════════════════════════════

usage = calc_usage_windows()
rate_limits = load_rate_limits()
metrics = calc_metrics()

# Optional demo override — only active if config.py (local, gitignored) sets DEMO_MODE = True.
# Harmless no-op when DEMO_MODE is absent or False.
if getattr(_cfg, "DEMO_MODE", False):
    _demo = getattr(_cfg, "DEMO_USAGE", None)
    if _demo:
        usage = _demo


def _gauge_class(pct: float) -> str:
    if pct >= 90:
        return "danger"
    if pct >= 70:
        return "warning"
    return ""


def render_gauge(
    label: str,
    reset_label: str,
    used: float,
    limit: float,
    stat_primary: str,
    stat_max: str,
    stat_sub: str,
    delta: tuple[str, float, str] | None = None,
) -> str:
    pct = min(100.0, (used / limit * 100.0) if limit else 0.0)
    klass = _gauge_class(pct)
    delta_html = ""
    if delta is not None:
        arrow, pct_d, dklass = delta
        dtxt = f'{arrow} {abs(pct_d):.0f}%' if dklass != "neutral" else '· flat'
        delta_html = f'<span class="gauge-delta {dklass}">{dtxt}</span>'
    return (
        f'<div class="gauge-card">'
        f'<div class="gauge-header">'
        f'<span class="gauge-label">{label}</span>'
        f'<span class="gauge-reset">{reset_label}</span>'
        f'</div>'
        f'<div class="gauge-track">'
        f'<div class="gauge-fill {klass}" style="width:{pct:.1f}%"></div>'
        f'</div>'
        f'<div class="gauge-stats">'
        f'<span>{stat_primary}</span>'
        f'<span class="gauge-max">/ {stat_max}</span>'
        f'<span class="gauge-sub">{stat_sub}</span>'
        f'{delta_html}'
        f'</div>'
        f'</div>'
    )


# ═══════════════════════════════════════════════════════════
# V2 CARD READERS + RENDERERS — Latest Upload, audience, etc.
# ═══════════════════════════════════════════════════════════

LATEST_VIDEO_JSON = VAULT_PATH / "system" / "metrics" / "latest-video.json"
METRICS_CSV = VAULT_PATH / "system" / "metrics" / "metrics.csv"
LAST_PULL_JSON = VAULT_PATH / "system" / "metrics" / "last-pull.json"


def read_claude_5h_billable() -> tuple[int | None, str | None]:
    """Latest claude_code/tokens_5h (output-only) from metrics.csv.

    The /metrics-pull skill emits three claude_code rows per pull:
    - tokens_5h      → OUTPUT tokens (the metric Anthropic actually meters
                       for the 5h rate-limit, per pull_claude_usage.py)
    - billable_5h    → input + output + cache_creation (informational only,
                       NOT what shows up as the rate-limit percentage)
    - cache_read_5h  → cache-read tokens (not metered)

    Earlier version of this reader pulled billable_5h, which made TokenBurn
    show ~75% even when claude.ai dev page showed ~4%. tokens_5h is the
    correct field.

    LIMITS["five_hour_tokens"] in config should be calibrated against your
    plan's actual output-token cap. Anthropic does not publish the exact
    number; community trackers report ~220K-440K for Max20x as of the
    April 2026 policy + later doubling. Default 5M is conservative —
    lower it if you want the % to read closer to what claude.ai shows.
    """
    if not METRICS_CSV.exists():
        return None, None
    latest_val: float | None = None
    latest_ts: str | None = None
    try:
        with METRICS_CSV.open("r", encoding="utf-8") as f:
            f.readline()  # header
            for line in f:
                parts = line.rstrip("\n").split(",")
                if len(parts) < 5:
                    continue
                ts, source, metric, value, status = parts[:5]
                if source != "claude_code" or metric != "tokens_5h":
                    continue
                if status not in ("ok", "mock"):
                    continue
                try:
                    val = float(value)
                except ValueError:
                    continue
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
                    latest_val = val
    except OSError:
        return None, None
    if latest_val is None:
        return None, None
    return int(latest_val), latest_ts


def read_audience_metrics() -> dict:
    """Return latest value per (source, metric) from metrics.csv. Falls back to DEMO_AUDIENCE."""
    demo_on = getattr(_cfg, "DEMO_MODE", False)
    demo = getattr(_cfg, "DEMO_AUDIENCE", None) or {}
    # canonical keys we surface as cards
    keys = {
        "youtube_subs":        ("youtube",   "subscribers"),
        "youtube_views_28d":   ("youtube",   "views_28d"),
        "instagram_followers": ("instagram", "followers"),
        "tiktok_followers":    ("tiktok",    "followers"),
    }
    if demo_on:
        return {k: dict(demo[k]) for k in keys if k in demo}

    out: dict[str, dict] = {}
    try:
        if METRICS_CSV.exists():
            # last-wins per (source, metric) pair — file is append-only
            latest: dict[tuple[str, str], dict] = {}
            with METRICS_CSV.open("r", encoding="utf-8") as f:
                header = f.readline()
                for line in f:
                    parts = line.rstrip("\n").split(",")
                    if len(parts) < 5:
                        continue
                    ts, source, metric, value, status = parts[:5]
                    try:
                        val = float(value)
                    except ValueError:
                        continue
                    latest[(source, metric)] = {"value": val, "ts": ts, "status": status}
            for key, pair in keys.items():
                if pair in latest:
                    out[key] = latest[pair]
    except OSError:
        pass

    # fill any missing with demo (so a partial-vault deployment still renders)
    for k in keys:
        if k not in out and k in demo:
            out[k] = dict(demo[k])
    return out


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def read_latest_video() -> dict | None:
    """Read system/metrics/latest-video.json. Fallback to DEMO_LATEST_VIDEO when DEMO_MODE or missing."""
    demo_on = getattr(_cfg, "DEMO_MODE", False)
    demo = getattr(_cfg, "DEMO_LATEST_VIDEO", None)
    if demo_on and demo:
        return dict(demo)
    try:
        if LATEST_VIDEO_JSON.exists():
            return json.loads(LATEST_VIDEO_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return dict(demo) if demo else None


def render_latest_upload(video: dict | None) -> str:
    if not video:
        return ""
    status = (video.get("status") or "ok").lower()
    title = video.get("title") or "(untitled)"
    url = video.get("url") or "#"
    views = int(video.get("views") or 0)
    likes = int(video.get("likes") or 0)
    comments = int(video.get("comments") or 0)
    pub_dt = _parse_iso(video.get("published_at") or "")
    ts_dt = _parse_iso(video.get("ts") or "")
    age_html = ""
    if pub_dt:
        try:
            age_sec = int((datetime.now(pub_dt.tzinfo) - pub_dt).total_seconds())
            age_html = f"· uploaded {fmt_ago(max(0, age_sec))} ago"
        except Exception:
            pass
    pull_html = ""
    if ts_dt:
        try:
            pull_age = int((datetime.now(ts_dt.tzinfo) - ts_dt).total_seconds())
            pull_html = f"· pulled {fmt_ago(max(0, pull_age))} ago"
        except Exception:
            pass

    dot_class = "mock" if status == "mock" else ("err" if status not in ("ok", "mock") else "")
    safe_title = html_escape(title)
    return (
        '<div class="v2-latest">'
        '<div class="v2-latest-head">'
        f'<span class="v2-dot {dot_class}"></span>'
        f'<span>latest upload · youtube</span>'
        f'<span style="margin-left:auto;color:var(--fg-mute)">{age_html} {pull_html}</span>'
        '</div>'
        f'<div class="v2-latest-title"><a href="{url}" target="_blank">{safe_title}</a></div>'
        '<div class="v2-latest-stats">'
        f'<span><span class="v2-stat-val">{fmt_tokens(views)}</span><span class="v2-stat-lbl">views</span></span>'
        f'<span><span class="v2-stat-val">{fmt_tokens(likes)}</span><span class="v2-stat-lbl">likes</span></span>'
        f'<span><span class="v2-stat-val">{fmt_tokens(comments)}</span><span class="v2-stat-lbl">comments</span></span>'
        '</div>'
        '</div>'
    )


def _status_to_dot(status: str | None, ts: str | None) -> str:
    s = (status or "").lower()
    if s == "ok":
        # treat as stale if >36h old
        dt = _parse_iso(ts or "")
        if dt:
            try:
                age_h = (datetime.now(dt.tzinfo) - dt).total_seconds() / 3600
                if age_h > 36:
                    return "stale"
            except Exception:
                pass
        return ""
    if s in ("mock", ""):
        return "mock"
    if s == "stale":
        return "stale"
    return "err"


def render_audience_card(label: str, tone: str, watermark: str, metric: dict | None, suffix: str = "") -> str:
    if not metric:
        # render empty shell rather than crash
        return (
            f'<div class="v2-audience-card" data-tone="{tone}">'
            f'<div class="v2-audience-watermark">{html_escape(watermark)}</div>'
            f'<div class="v2-audience-head"><span class="v2-dot stale"></span>{html_escape(label)}</div>'
            '<div class="v2-audience-value">—</div>'
            '<div class="v2-audience-sub">no data</div>'
            '</div>'
        )
    value = metric.get("value") or 0
    ts = metric.get("ts")
    status = metric.get("status")
    dot = _status_to_dot(status, ts)
    ago_html = ""
    dt = _parse_iso(ts or "")
    if dt:
        try:
            age = int((datetime.now(dt.tzinfo) - dt).total_seconds())
            ago_html = f"updated {fmt_ago(max(0, age))} ago"
        except Exception:
            pass
    val_html = fmt_tokens(int(value)) if value >= 1000 else f"{int(value):,}"
    if suffix:
        val_html = f"{val_html}<span style='font-size:0.7rem;color:var(--fg-mute);margin-left:0.3rem'>{suffix}</span>"
    return (
        f'<div class="v2-audience-card" data-tone="{tone}">'
        f'<div class="v2-audience-watermark">{html_escape(watermark)}</div>'
        f'<div class="v2-audience-head"><span class="v2-dot {dot}"></span>{html_escape(label)}</div>'
        f'<div class="v2-audience-value">{val_html}</div>'
        f'<div class="v2-audience-sub">{ago_html}</div>'
        '</div>'
    )


def render_audience_row() -> None:
    aud = read_audience_metrics()
    cols = st.columns(4, gap="small")
    cards = [
        ("youtube subs",  "youtube",   "YT",  "youtube_subs",        ""),
        ("youtube views · 28d", "youtube", "▶",  "youtube_views_28d",   ""),
        ("instagram",     "instagram", "IG",  "instagram_followers", ""),
        ("tiktok",        "tiktok",    "TT",  "tiktok_followers",    ""),
    ]
    for col, (label, tone, mark, key, suf) in zip(cols, cards):
        with col:
            st.markdown(
                render_audience_card(label, tone, mark, aud.get(key), suf),
                unsafe_allow_html=True,
            )


def read_last_pull_ts() -> str | None:
    """Most-recent ts across sources in last-pull.json."""
    try:
        if not LAST_PULL_JSON.exists():
            return None
        data = json.loads(LAST_PULL_JSON.read_text(encoding="utf-8"))
        latest = None
        for src, info in (data or {}).items():
            ts = info.get("ts") if isinstance(info, dict) else None
            if ts and (latest is None or ts > latest):
                latest = ts
        return latest
    except (OSError, json.JSONDecodeError):
        return None


def render_tokenburn_meter(used: int, budget: int, reset_at: float | None, last_pull_ts: str | None) -> str:
    """5h window TokenBurn marquee. Returns HTML string mirroring Obsidian cockpit component."""
    pct = min(100.0, (used / budget * 100.0) if budget else 0.0)

    # Projection: linear extrapolation of current burn to end-of-window.
    proj_pct = pct
    if reset_at:
        try:
            reset_in_sec = max(0, int(reset_at - time.time()))
            window_sec = 5 * 3600
            elapsed_sec = max(60, window_sec - reset_in_sec)
            burn_per_sec = used / elapsed_sec if elapsed_sec else 0
            projected_total = used + (burn_per_sec * reset_in_sec)
            if budget:
                proj_pct = min(100.0, projected_total / budget * 100.0)
        except Exception:
            pass

    tone_class = "critical" if pct >= 90 else ("warn" if pct >= 70 else "")

    pull_age_html = "—"
    pull_dt = _parse_iso(last_pull_ts or "")
    if pull_dt:
        try:
            age = int((datetime.now(pull_dt.tzinfo) - pull_dt).total_seconds())
            pull_age_html = f"last pull {fmt_ago(max(0, age))} ago"
        except Exception:
            pass

    pct_int = int(round(pct))
    proj_left = pct
    proj_width = max(0.0, proj_pct - pct)

    used_h = fmt_tokens(int(used))
    budget_h = fmt_tokens(int(budget))
    projected_total = int((proj_pct / 100.0) * budget) if budget else 0
    projected_h = fmt_tokens(projected_total)

    # Tick marks every 25% of budget — keeps scale legible.
    ticks = []
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        ticks.append(fmt_tokens(int(budget * frac)) if budget else "—")

    wrap_class = f"v2-tb-wrap {tone_class}".strip()
    return (
        f'<div class="{wrap_class}">'
        # HUD corner brackets (4 explicit spans, animate on .critical)
        '<span class="v2-tb-corner tl"></span>'
        '<span class="v2-tb-corner tr"></span>'
        '<span class="v2-tb-corner bl"></span>'
        '<span class="v2-tb-corner br"></span>'
        # Header
        '<div class="v2-tb-head">'
        '<span class="v2-tb-title">§ TOKEN BURN · 5H WINDOW</span>'
        '<span class="v2-tb-live"><span class="v2-tb-live-dot"></span>LIVE</span>'
        f'<span class="v2-tb-meta">{pull_age_html}</span>'
        '</div>'
        # Meter grid: pct | bar | counts
        '<div class="v2-tb-meter">'
        '<div class="v2-tb-pct">'
        f'<span class="v2-tb-pct-num">{pct_int}</span>'
        '<span class="v2-tb-pct-unit">%</span>'
        '</div>'
        '<div class="v2-tb-bar-wrap">'
        '<div class="v2-tb-track">'
        f'<div class="v2-tb-fill" style="--tb-target:{pct:.1f}%;width:{pct:.1f}%"></div>'
        f'<div class="v2-tb-proj" style="left:{proj_left:.1f}%;width:{proj_width:.1f}%"></div>'
        f'<div class="v2-tb-comet" style="--tb-target:{pct:.1f}%;left:max(0px, calc({pct:.1f}% - 80px));width:min(80px, {pct:.1f}%)"></div>'
        f'<div class="v2-tb-endpoint" style="--tb-target:{pct:.1f}%;left:{pct:.1f}%"></div>'
        '<div class="v2-tb-scan"></div>'
        '</div>'
        '<div class="v2-tb-ticks">'
        + "".join(f"<span>{t}</span>" for t in ticks) +
        '</div>'
        '</div>'
        '<div class="v2-tb-counts">'
        f'<div><span class="v2-tb-used">{used_h}</span> / {budget_h}</div>'
        f'<div class="v2-tb-proj-label">→ {projected_h} projected</div>'
        '</div>'
        '</div>'
        '</div>'
    )


# ── YtWeekReview parser + renderer (commit 7) ──────────────
import uuid as _uuid

YT_REVIEWS_DIR = VAULT_PATH / "inbox" / "reports" / "yt-reviews"
QUEUE_DIR = VAULT_PATH / "system" / "queue"


def _latest_in_dir(dir_path: Path, glob: str = "*.md") -> Path | None:
    if not dir_path.exists():
        return None
    files = sorted(
        (p for p in dir_path.glob(glob) if not p.name.startswith("_")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def parse_yt_review(path: Path | None = None) -> dict | None:
    """Parse the latest yt-week-review markdown. Returns dict with tldr, uploads, top, under, window."""
    if path is None:
        path = _latest_in_dir(YT_REVIEWS_DIR)
    if not path or not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")

    # Frontmatter
    meta: dict = {"path": str(path), "name": path.name}
    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    body = text[fm_match.end():] if fm_match else text

    # TL;DR — bullet list under ## TL;DR
    tldr: list[str] = []
    m = re.search(r"## TL;DR\s*\n(.*?)(?=\n##\s|\Z)", body, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if line.startswith("- "):
                tldr.append(line[2:])

    # Uploads table — markdown table with headers Title | Views | vs Baseline | Likes | Comments | Verdict
    uploads: list[dict] = []
    m = re.search(r"## Uploads this week\s*\n(.*?)(?=\n##\s|\Z)", body, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not cells or cells[0].lower().startswith("video") or set(cells[0]) <= {"-", ":"}:
                continue
            if len(cells) < 6:
                continue
            try:
                views = int(cells[1].replace(",", ""))
            except ValueError:
                continue
            uploads.append({
                "title": cells[0],
                "views": views,
                "vs_baseline": cells[2],
                "likes": cells[3],
                "comments": cells[4],
                "verdict": cells[5],
            })

    # Top performer + underperformer headlines
    def _section(heading: str) -> str:
        m = re.search(rf"## {re.escape(heading)} — (.+?)\n(.*?)(?=\n##\s|\Z)", body, re.DOTALL)
        if not m:
            return ""
        title = m.group(1).strip()
        return title

    top = _section("Top performer")
    under = _section("Underperformer")

    return {
        "meta": meta,
        "window": meta.get("window") or meta.get("date") or "",
        "tldr": tldr,
        "uploads": uploads,
        "top": top,
        "under": under,
    }


def write_queue_intent(skill: str, args: dict | None = None) -> tuple[str, Path]:
    """Drop an intent JSON into system/queue/. Runner picks it up."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    uid = str(_uuid.uuid4())
    path = QUEUE_DIR / f"{uid}.json"
    payload = {
        "id": uid,
        "skill": skill,
        "args": args or {},
        "ts_queued": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "source": "streamlit",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return uid, path


_VERDICT_TONE = {
    "hit":      "hit",
    "steady":   "steady",
    "climbing": "climbing",
    "miss":     "miss",
}


def render_yt_review_card(review: dict | None, tab_key: str = "audience") -> None:
    """Render YtWeekReview marquee directly into the current Streamlit context."""
    if not review:
        # Empty state — prominent RUN NEW button
        st.markdown(
            '<div class="v2-ytr-card">'
            '<div class="v2-ytr-head"><span class="v2-ytr-title">YT WEEK REVIEW</span></div>'
            '<div style="color:var(--fg-mute);font-size:0.78rem;margin:0.6rem 0">'
            'No review on file yet. Run the skill to generate the first one.'
            '</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("▶ RUN /yt-week-review", key=f"ytr_run_empty_{tab_key}"):
            uid, _ = write_queue_intent("yt-week-review")
            st.toast(f"queued · {uid[:8]}", icon="✅")
        return

    window = html_escape(review.get("window") or "")
    review_path = Path(review["meta"].get("path", ""))
    full_uri = obsidian_uri(review_path) if review_path.exists() else "#"

    # Header — title + actions row
    st.markdown(
        '<div class="v2-ytr-card">'
        '<div class="v2-ytr-head">'
        f'<span class="v2-ytr-title">YT WEEK REVIEW · {window}</span>'
        '<span class="v2-ytr-actions">'
        f'<a href="{full_uri}" target="_blank">FULL ↗</a>'
        '</span></div>',
        unsafe_allow_html=True,
    )

    # TL;DR
    tldr = review.get("tldr") or []
    if tldr:
        bullets = "".join(f"<li>{html_escape(b)}</li>" for b in tldr[:4])
        st.markdown(f'<ul class="v2-ytr-tldr">{bullets}</ul>', unsafe_allow_html=True)

    # Verdict chip row
    uploads = review.get("uploads") or []
    verdict_counts: dict[str, int] = {}
    for u in uploads:
        v = (u.get("verdict") or "").lower()
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
    chip_html = '<div class="v2-chip-row">'
    for v in ("hit", "climbing", "steady", "miss"):
        n = verdict_counts.get(v, 0)
        tone = _VERDICT_TONE.get(v, "steady")
        chip_html += f'<span class="v2-chip {tone}">{v.upper()} {n}</span>'
    chip_html += '</div>'
    st.markdown(chip_html, unsafe_allow_html=True)

    # Bar chart of per-video views (Altair, color by verdict)
    if uploads:
        df_up = pd.DataFrame([
            {
                "title": (u["title"][:38] + "…") if len(u["title"]) > 38 else u["title"],
                "views": u["views"],
                "verdict": (u.get("verdict") or "Steady").capitalize(),
            }
            for u in uploads
        ])
        verdict_colors = {
            "Hit":       "#8fb97a",
            "Climbing":  "#d9a566",
            "Steady":    "#b0aea5",
            "Miss":      "#c96442",
        }
        chart = (
            alt.Chart(df_up)
            .mark_bar(cornerRadiusEnd=2)
            .encode(
                y=alt.Y("title:N", sort="-x", axis=alt.Axis(title=None, labelFontSize=10, labelLimit=300, labelColor="#b0aea5")),
                x=alt.X("views:Q", axis=alt.Axis(title=None, labelFontSize=9, format="~s", labelColor="#87867f", grid=False)),
                color=alt.Color(
                    "verdict:N",
                    scale=alt.Scale(
                        domain=list(verdict_colors.keys()),
                        range=list(verdict_colors.values()),
                    ),
                    legend=None,
                ),
                tooltip=["title", "views", "verdict"],
            )
            .properties(height=max(110, 26 * len(uploads)), background="transparent")
            .configure_view(strokeWidth=0)
            .configure_axis(domain=False, tickColor="#3a3937")
        )
        st.altair_chart(chart, use_container_width=True)

    # Top performer + underperformer mini-cards
    top = review.get("top") or ""
    under = review.get("under") or ""
    perfs_html = '<div class="v2-ytr-perfs">'
    if top:
        perfs_html += (
            '<div class="v2-perf-card top">'
            '<div class="v2-perf-label">TOP PERFORMER</div>'
            f'<div class="v2-perf-title">{html_escape(top)}</div>'
            '</div>'
        )
    if under:
        perfs_html += (
            '<div class="v2-perf-card under">'
            '<div class="v2-perf-label">UNDERPERFORMER</div>'
            f'<div class="v2-perf-title">{html_escape(under)}</div>'
            '</div>'
        )
    perfs_html += '</div></div>'
    st.markdown(perfs_html, unsafe_allow_html=True)

    if st.button("▶ RUN /yt-week-review (fresh)", key=f"ytr_run_{tab_key}"):
        uid, _ = write_queue_intent("yt-week-review")
        st.toast(f"queued · {uid[:8]}", icon="✅")


# ── MorningBrief parser + renderer (commit 8) ──────────────

MORNING_DIR = VAULT_PATH / "inbox" / "reports" / "morning"


def _extract_section(body: str, heading_pattern: str) -> str:
    m = re.search(rf"##\s+{heading_pattern}\s*\n(.*?)(?=\n##\s|\Z)", body, re.DOTALL)
    return m.group(1) if m else ""


_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def _clean_md(text: str) -> str:
    """Strip markdown bold + link syntax from a bullet so it renders as plain text."""
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_BOLD_RE.sub(r"\1", text)
    return text.strip()


def _bullets(section: str, limit: int = 3) -> list[str]:
    out = []
    for line in section.splitlines():
        s = line.strip()
        if s.startswith("- "):
            text = _clean_md(s[2:].lstrip())
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _bullet_count(section: str) -> int:
    return sum(1 for line in section.splitlines() if line.strip().startswith("- "))


def _table_rows(section: str) -> int:
    count = 0
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or set(cells[0]) <= {"-", ":"} or cells[0].lower() in ("video", "creator", "title"):
            continue
        count += 1
    return count


def _parse_yt_table(section: str, limit: int = 3) -> list[dict]:
    """Parse the YouTube trending markdown table. Returns list of {title, creator, views}."""
    out: list[dict] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or set(cells[0]) <= {"-", ":"}:
            continue
        if cells[0].lower() in ("video", "title", "creator"):
            continue
        if len(cells) < 3:
            continue
        out.append({
            "title":   _clean_md(cells[0]),
            "creator": _clean_md(cells[1]) if len(cells) > 1 else "",
            "views":   cells[2] if len(cells) > 2 else "",
        })
        if len(out) >= limit:
            break
    return out


def _parse_x_voices(body: str, limit: int = 3) -> list[str]:
    """Extract bullets nested under **Top voices:** in the morning brief X section."""
    m = re.search(r"\*\*Top voices:\*\*\s*\n((?:\s+-\s+.+\n?)+)", body)
    if not m:
        return []
    out: list[str] = []
    for l in m.group(1).splitlines():
        s = l.strip()
        if s.startswith("- "):
            out.append(_clean_md(s[2:].lstrip()))
        if len(out) >= limit:
            break
    return out


def parse_morning_brief(path: Path | None = None) -> dict | None:
    if path is None:
        path = _latest_in_dir(MORNING_DIR)
    if not path or not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    fm_match = _FRONTMATTER_RE.match(text)
    body = text[fm_match.end():] if fm_match else text

    headlines_s = _extract_section(body, r"Headlines")
    yt_s = _extract_section(body, r"YouTube[^\n]*Trending[^\n]*")
    web_s = _extract_section(body, r"Web[^\n]*News[^\n]*")
    x_s = _extract_section(body, r"X[^\n]*Twitter[^\n]*")
    gh_s = _extract_section(body, r"GitHub[^\n]*Builder[^\n]*")
    opps_s = _extract_section(body, r"Content Opportunities")

    # X voices nested bullets under "**Top voices:**"
    voice_bullets = _parse_x_voices(body, limit=3)
    voices_n = 0
    m_voices = re.search(r"\*\*Top voices:\*\*\s*\n((?:\s+-\s+.+\n?)+)", body)
    if m_voices:
        voices_n = sum(1 for l in m_voices.group(1).splitlines() if l.strip().startswith("- "))

    return {
        "path": str(path),
        "name": path.name,
        "headlines":   _bullets(headlines_s, 3),
        "headlines_n": _bullet_count(headlines_s),
        "yt_top":      _parse_yt_table(yt_s, limit=3),
        "yt_rows":     _table_rows(yt_s),
        "x_voices":    voice_bullets,
        "x_voices_n":  voices_n,
        "web_n":       _bullet_count(web_s),
        "gh_n":        _bullet_count(gh_s),
        "opps":        _bullets(opps_s, 3),
        "opps_n":      _bullet_count(opps_s),
    }


def render_morning_brief(brief: dict | None) -> None:
    if not brief:
        st.markdown(
            '<div class="v2-mb-grid">'
            '<div class="v2-mb-tile"><div class="v2-mb-label">MORNING BRIEF</div>'
            '<div style="color:var(--fg-mute);font-size:0.78rem">No brief on file. Run the /morning skill.</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )
        return
    # Coverage chip row
    cov = (
        '<div class="v2-mb-coverage">'
        f'<span>{brief["headlines_n"]} HEADLINES</span>'
        f'<span>{brief["web_n"]} ARTICLES</span>'
        f'<span>{brief["x_voices_n"]} X VOICES</span>'
        f'<span>{brief["gh_n"]} REPOS</span>'
        f'<span>{brief["opps_n"]} OPPS</span>'
        '</div>'
    )
    st.markdown(cov, unsafe_allow_html=True)

    def _tile(label: str, items: list[str]) -> str:
        if not items:
            body = '<div style="color:var(--fg-mute);font-size:0.74rem">no data</div>'
        else:
            body = "<ul>" + "".join(f"<li>{html_escape(i[:180])}</li>" for i in items) + "</ul>"
        return f'<div class="v2-mb-tile"><div class="v2-mb-label">{label}</div>{body}</div>'

    # YT trending tile — render top videos with creator + view count
    yt_items = [
        f'{html_escape(v["title"])} <span style="color:var(--cc-fg-2)">· {html_escape(v["creator"])} · {html_escape(v["views"])}</span>'
        for v in (brief.get("yt_top") or [])
    ]
    x_items = [html_escape(s) for s in (brief.get("x_voices") or [])]
    headlines_items = [html_escape(s) for s in (brief.get("headlines") or [])]
    opps_items = [html_escape(s) for s in (brief.get("opps") or [])]

    def _tile_html(label: str, items: list[str]) -> str:
        if not items:
            body = '<div style="color:var(--cc-fg-2);font-size:0.74rem">no data</div>'
        else:
            body = "<ul>" + "".join(f"<li>{i[:240]}</li>" for i in items) + "</ul>"
        return f'<div class="v2-mb-tile"><div class="v2-mb-label">{label}</div>{body}</div>'

    grid = (
        '<div class="v2-mb-grid">'
        + _tile_html("HEADLINES",        headlines_items)
        + _tile_html("YT · TRENDING",    yt_items)
        + _tile_html("X · CONVERSATION", x_items)
        + _tile_html("CONTENT OPPS",     opps_items)
        + '</div>'
    )
    st.markdown(grid, unsafe_allow_html=True)

    brief_path = Path(brief["path"])
    if brief_path.exists():
        uri = obsidian_uri(brief_path)
        st.markdown(
            f'<div style="text-align:right;font-size:0.65rem;margin-top:0.3rem">'
            f'<a href="{uri}" target="_blank" style="color:var(--accent);text-decoration:none;letter-spacing:0.1em">FULL ↗</a>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Daily note → Schedule + Daily Drivers (commit 8) ───────

def parse_daily_note(date_iso: str | None = None) -> dict:
    """Read today's (or given date's) daily note. Returns dict with schedule + drivers."""
    if date_iso is None:
        date_iso = date.today().isoformat()
    note = DAILY_NOTES_DIR / f"{date_iso}.md"
    out = {"path": str(note), "schedule": [], "drivers": []}
    if not note.exists():
        return out
    text = note.read_text(encoding="utf-8", errors="replace")
    sched_s = _extract_section(text, r"Schedule")
    for line in sched_s.splitlines():
        s = line.strip()
        if not s.startswith("- "):
            continue
        # Format: "- HH:MM — label"
        m = re.match(r"-\s+(\d{1,2}:\d{2})\s*[—\-–]\s*(.+)", s)
        if m:
            out["schedule"].append({"time": m.group(1), "label": m.group(2).strip()})
    drv_s = _extract_section(text, r"Daily Drivers")
    for line in drv_s.splitlines():
        s = line.strip()
        m = re.match(r"-\s+\[([ xX])\]\s+(.+)", s)
        if m:
            out["drivers"].append({"done": m.group(1).lower() == "x", "label": m.group(2).strip()})
    return out


def render_schedule_panel(events: list[dict]) -> str:
    if not events:
        body = '<div style="color:var(--cc-fg-2);font-size:12px">no schedule today</div>'
    else:
        rows = "".join(
            f'<div class="v2-sched-row"><span class="v2-sched-time">{html_escape(e["time"])}</span>'
            f'<span class="v2-sched-label">{html_escape(e["label"])}</span></div>'
            for e in events
        )
        # CSS-columns flow into 2 columns when >=4 events; single column otherwise.
        list_class = "v2-sched-list" if len(events) >= 4 else "v2-sched-list-single"
        body = f'<div class="{list_class}">{rows}</div>'
    return (
        '<div class="v2-panel v2-sched-panel">'
        '<div class="v2-panel-head">§ SCHEDULE · TODAY</div>'
        f'{body}</div>'
    )


def toggle_driver_in_note(date_iso: str, idx: int, new_state: bool) -> bool:
    """Flip the idx-th `- [ ]` ↔ `- [x]` bullet in today's Daily Drivers section.

    Returns True on success. Idempotent — runs the file edit even if state already matches.
    """
    note = DAILY_NOTES_DIR / f"{date_iso}.md"
    if not note.exists():
        return False
    text = note.read_text(encoding="utf-8")
    m = re.search(r"(##\s+Daily Drivers\s*\n)(.*?)(?=\n##\s|\Z)", text, re.DOTALL)
    if not m:
        return False
    head_end = m.end(1)
    section_start = m.start(2)
    section = m.group(2)
    lines = section.split("\n")
    bullet_positions: list[int] = []
    for i, line in enumerate(lines):
        if re.match(r"-\s+\[[ xX]\]\s+", line.strip()):
            bullet_positions.append(i)
    if idx >= len(bullet_positions):
        return False
    li = bullet_positions[idx]
    line = lines[li]
    if new_state:
        line = re.sub(r"\[[ ]\]", "[x]", line, count=1)
    else:
        line = re.sub(r"\[[xX]\]", "[ ]", line, count=1)
    lines[li] = line
    new_section = "\n".join(lines)
    new_text = text[:section_start] + new_section + text[section_start + len(section):]
    note.write_text(new_text, encoding="utf-8")
    return True


def render_daily_drivers_widget(drivers: list[dict], date_iso: str) -> None:
    """Native st.checkbox renderer — toggling writes back to the daily note.

    Replaces the read-only HTML renderer so Streamlit gains parity with Obsidian's
    inline checkbox interaction.
    """
    st.markdown(
        '<div class="v2-panel v2-panel-drivers-head">'
        '<div class="v2-panel-head">§ DAILY DRIVERS</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if not drivers:
        st.markdown(
            '<div style="color:var(--cc-fg-2);font-size:12px;padding:4px 0">no drivers seeded today</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown('<div class="v2-driver-stack-marker"></div>', unsafe_allow_html=True)
    for idx, d in enumerate(drivers):
        key = f"drv_{date_iso}_{idx}"
        if key not in st.session_state:
            st.session_state[key] = d["done"]

        def _on_change(_idx=idx, _key=key, _date=date_iso):
            toggle_driver_in_note(_date, _idx, bool(st.session_state.get(_key, False)))

        st.checkbox(d["label"], key=key, on_change=_on_change)

    st.markdown(
        '<div style="color:var(--cc-fg-2);font-size:9px;letter-spacing:0.18em;'
        'margin-top:6px;text-transform:uppercase">writes back to daily note</div>',
        unsafe_allow_html=True,
    )


five_h_reset = (rate_limits.get("five_hour") or {}).get("resets_at")
week_reset = (rate_limits.get("weekly") or {}).get("resets_at")

five_h_tokens = usage["five_hour"]["total"]
# Prefer metrics.csv `claude_code/billable_5h` row when present — that's the
# authoritative Anthropic-billed 5h count (matches claude.ai dev page).
# Falls back to legacy session-meta scan when no metrics-pull row exists.
_billable_5h, _billable_ts = read_claude_5h_billable()
if _billable_5h is not None and not getattr(_cfg, "DEMO_MODE", False):
    five_h_tokens = _billable_5h
week_tokens = usage["weekly"]["total"]
routines_today = usage["today"]["routines"]
today_runs = usage["today"]["runs"]
today_cost = usage["today"]["cost"]

_metas_cache = _read_session_metas()
_now = datetime.now()
_5h_cur, _5h_pri = delta_window(
    _metas_cache,
    _now - timedelta(hours=5), _now,
    _now - timedelta(hours=10), _now - timedelta(hours=5),
)
_wk_cur, _wk_pri = delta_window(
    _metas_cache,
    _now - timedelta(days=7), _now,
    _now - timedelta(days=14), _now - timedelta(days=7),
)
_rt_ledger = _load_routines_ledger()
_rt_today = int(_rt_ledger.get(date.today().isoformat(), 0))
_rt_yday = int(_rt_ledger.get((date.today() - timedelta(days=1)).isoformat(), 0))
_5h_delta = compute_delta(_5h_cur, _5h_pri)
_wk_delta = compute_delta(_wk_cur, _wk_pri)
_rt_delta = compute_delta(_rt_today, _rt_yday)

_enabled_cards = getattr(_cfg, "ENABLED_CARDS", {}) or {}

# ═══════════════════════════════════════════════════════════
# TOKENBURN — single 5h meter replaces the legacy 3-meter row
# (5h / weekly / routines). Mirrors the Obsidian cockpit pattern.
# ═══════════════════════════════════════════════════════════

if _enabled_cards.get("tokenburn", True):
    st.markdown(
        render_tokenburn_meter(
            used=five_h_tokens,
            budget=LIMITS["five_hour_tokens"],
            reset_at=five_h_reset,
            last_pull_ts=read_last_pull_ts(),
        ),
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# RUNS-PER-DAY CHART  (rendered inside Overview tab below)
# ═══════════════════════════════════════════════════════════

import plotly.graph_objects as go

df_cum = activity_cumulative(30)
_cum_total = int(df_cum["cumulative"].iloc[-1]) if not df_cum.empty else 0
_cum_30d = int(df_cum["day_count"].sum())


def _build_activity_svg(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    cum = df["cumulative"].tolist()
    dates = df["date"].tolist()
    n = len(cum)
    max_c = max(cum) or 1
    VB_W, VB_H = 1000, 180
    ML, MR, MT, MB = 24, 24, 14, 6
    pw = VB_W - ML - MR
    ph = VB_H - MT - MB

    pts = []
    for i, c in enumerate(cum):
        x = ML + (i / max(1, n - 1)) * pw
        y = MT + ph - (c / max_c) * ph
        pts.append((x, y))

    line_d = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    area_d = (
        f"M {pts[0][0]:.2f},{MT + ph:.2f} "
        + " ".join(f"L {x:.2f},{y:.2f}" for x, y in pts)
        + f" L {pts[-1][0]:.2f},{MT + ph:.2f} Z"
    )
    # Closed-loop motion path: trace line forward then back along baseline.
    # Pulse "does a loop" instead of teleporting back to start.
    loop_d = (
        "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        + f" L {pts[-1][0]:.2f},{MT + ph:.2f}"
        + f" L {pts[0][0]:.2f},{MT + ph:.2f} Z"
    )

    tick_idx = [0, n // 4, n // 2, (3 * n) // 4, n - 1]
    tick_labels = [dates[i].strftime("%b %d").lower() for i in tick_idx]

    svg = f'''
<div class="activity-chart-wrap">
  <svg class="activity-svg" viewBox="0 0 {VB_W} {VB_H}"
       preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="activityFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="#c96442" stop-opacity="0.48"/>
        <stop offset="60%"  stop-color="#c96442" stop-opacity="0.14"/>
        <stop offset="100%" stop-color="#c96442" stop-opacity="0"/>
      </linearGradient>
      <filter id="pulseGlow" x="-200%" y="-200%" width="500%" height="500%">
        <feGaussianBlur stdDeviation="2.4" result="b1"/>
        <feGaussianBlur stdDeviation="5.5" result="b2"/>
        <feMerge>
          <feMergeNode in="b2"/>
          <feMergeNode in="b1"/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>
      <filter id="lineGlow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="1.2" result="lg"/>
        <feMerge>
          <feMergeNode in="lg"/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>
    </defs>
    <path d="{area_d}" fill="url(#activityFill)" stroke="none">
      <animate attributeName="opacity" values="0.85;1;0.85"
               dur="6s" repeatCount="indefinite"/>
    </path>
    <path id="activityPath" d="{line_d}" fill="none"
          stroke="#c96442" stroke-width="1.6"
          stroke-linejoin="round" stroke-linecap="round"
          vector-effect="non-scaling-stroke"
          filter="url(#lineGlow)"/>
    <path id="activityLoop" d="{loop_d}" fill="none" stroke="none"/>
    <circle r="4.2" fill="#ffd3b5" filter="url(#pulseGlow)" opacity="0.95">
      <animateMotion dur="7s" repeatCount="indefinite" rotate="auto">
        <mpath href="#activityLoop"/>
      </animateMotion>
      <animate attributeName="opacity" values="0.35;1;0.35"
               dur="1.4s" repeatCount="indefinite"/>
    </circle>
    <circle r="2" fill="#fff3e6">
      <animateMotion dur="7s" repeatCount="indefinite" rotate="auto">
        <mpath href="#activityLoop"/>
      </animateMotion>
    </circle>
  </svg>
  <div class="activity-axis">
    {"".join(f"<span>{lbl}</span>" for lbl in tick_labels)}
  </div>
</div>
'''
    return svg


# 30-day cumulative chart rendered inside Overview tab (see LAYOUT block below).


# ═══════════════════════════════════════════════════════════
# MCP HEALTH STRIP
# ═══════════════════════════════════════════════════════════

mcp_servers = load_mcp_state()
if mcp_servers:
    items_html = '<span class="mcp-label">integrations</span>'
    for s in mcp_servers:
        name = s.get("name", "?").replace("claude.ai ", "").replace("plugin:", "")
        status = (s.get("status") or "unknown").lower().replace("-", "_")
        items_html += (
            f'<span class="mcp-item">'
            f'<span class="mcp-dot {status}"></span>'
            f'{html_escape(name)}'
            f'</span>'
        )
    st.markdown(f'<div class="mcp-strip">{items_html}</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# LAYOUT
# ═══════════════════════════════════════════════════════════

st.markdown('<hr class="chapter" />', unsafe_allow_html=True)

_layout_v = getattr(_cfg, "LAYOUT_VERSION", "v1")
if _layout_v == "v2":
    overview_tab, audience_tab, research_tab = st.tabs([
        "overview", "audience", "research",
    ])
else:
    # v1 fallback — no tabs, single column. Defined as null context for indented block below.
    from contextlib import nullcontext
    overview_tab = nullcontext()
    audience_tab = nullcontext()
    research_tab = nullcontext()

with overview_tab:

    # ── Schedule + Throughput chart (2-col) ───────────────────
    _show_sched = _enabled_cards.get("schedule", True)
    _show_drv   = _enabled_cards.get("daily_drivers", False)
    _show_thru  = _enabled_cards.get("throughput", True)
    if _show_sched or _show_drv or _show_thru:
        _today_iso = date.today().isoformat()
        _daily = parse_daily_note(_today_iso)
        _sd_cols = st.columns(2, gap="small")
        with _sd_cols[0]:
            if _show_sched:
                st.markdown(render_schedule_panel(_daily["schedule"]), unsafe_allow_html=True)
        with _sd_cols[1]:
            if _show_drv:
                render_daily_drivers_widget(_daily["drivers"], _today_iso)
            elif _show_thru:
                # 30-day throughput chart — placeholder metric, swap name for any skill mix
                st.markdown(
                    '<div class="v2-panel v2-thru-panel">'
                    '<div class="v2-panel-head">'
                    '<span>§ AGENT RUNS · 30D</span>'
                    f'<span class="v2-thru-meta">{_cum_total:,} total · {_cum_30d} last 30d</span>'
                    '</div>'
                    f'<div class="v2-thru-svg">{_build_activity_svg(df_cum)}</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

    col_main, col_side = st.columns([2.6, 1], gap="large")


    # ——— SIDEBAR COLUMN: recent runs ———
    with col_side:
        runs = list_recent_runs(8)
        card_html = '<div class="runs-card"><div class="cat-label">recent runs</div>'
        if not runs:
            card_html += '<div style="color: var(--text-mute); font-size: 0.8rem; padding: 0.4rem 0 0.5rem 0;">no runs yet</div>'
        else:
            card_html += '<div class="run-list">'
            for r in runs:
                mtime = datetime.fromtimestamp(r.stat().st_mtime)
                label = r.stem.split("-", 2)[-1].replace("-", " ")
                uri = obsidian_uri(r)
                card_html += (
                    f'<div class="run-row">'
                    f'<span class="run-time">{mtime.strftime("%H:%M")}</span>'
                    f'<span class="run-label">{html_escape(label)}</span>'
                    f'<a href="{uri}" target="_blank">open ↗</a>'
                    f'</div>'
                )
            card_html += '</div>'
        card_html += '</div>'
        st.markdown(card_html, unsafe_allow_html=True)

        # Mini 7-day runs bar chart (bottom-right "dead space" filler)
        df_7 = activity_cumulative(7)
        _bar_labels = df_7["date"].dt.strftime("%a").tolist()
        _bar_vals = df_7["day_count"].tolist()
        _bar_total = int(sum(_bar_vals))

        st.markdown(
            '<div class="chart-card mini-chart">'
            '<div class="chart-title">last <em>seven</em> days '
            f'<span>· {_bar_total} runs</span></div>',
            unsafe_allow_html=True,
        )
        _barfig = go.Figure()
        _barfig.add_trace(
            go.Bar(
                x=_bar_labels,
                y=_bar_vals,
                marker=dict(color="#c96442", line=dict(width=0)),
                hovertemplate="<b>%{x}</b><br>%{y} runs<extra></extra>",
            )
        )
        _barfig.update_layout(
            height=120,
            margin=dict(l=20, r=20, t=10, b=28),
            paper_bgcolor="#1c1b19",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="JetBrains Mono, monospace", size=9, color="#b0aea5"),
            showlegend=False,
            bargap=0.32,
            hoverlabel=dict(
                bgcolor="#0e0f10",
                bordercolor="#c96442",
                font=dict(family="JetBrains Mono, monospace", color="#faf9f5", size=10),
            ),
            xaxis=dict(
                showgrid=False, zeroline=False, showline=False,
                tickfont=dict(color="#b0aea5", size=9),
            ),
            yaxis=dict(
                showgrid=False, zeroline=False, showline=False, showticklabels=False,
            ),
        )
        st.plotly_chart(_barfig, use_container_width=True, config={"displayModeBar": False})
        st.markdown("</div>", unsafe_allow_html=True)

        # ——— Forecast card (5-hour burn projection) ———
        _cap = LIMITS["five_hour_tokens"]
        _used = five_h_tokens
        _remaining = max(0, _cap - _used)
        _reset_in_sec = max(0, int(five_h_reset - time.time())) if five_h_reset else 0
        _reset_in_min = _reset_in_sec // 60
        _window_min = 300  # 5h
        _elapsed_min = max(1, _window_min - _reset_in_min) if _reset_in_min else 1
        _burn_per_min = (_used / _elapsed_min) if _elapsed_min > 0 else 0
        _exhaust_in_min = int(_remaining / _burn_per_min) if _burn_per_min > 0 else None
        _will_exhaust = _exhaust_in_min is not None and _exhaust_in_min < _reset_in_min

        _elapsed_pct = min(100, _elapsed_min / _window_min * 100)
        if _will_exhaust and _exhaust_in_min is not None:
            _proj_end_min = _elapsed_min + _exhaust_in_min
        else:
            _proj_end_min = _window_min
        _proj_pct = max(_elapsed_pct, min(100, _proj_end_min / _window_min * 100))
        _proj_left = _elapsed_pct
        _proj_width = max(0, _proj_pct - _elapsed_pct)
        _now_pct = _elapsed_pct

        if _will_exhaust and _exhaust_in_min is not None:
            _hit = (datetime.now() + timedelta(minutes=_exhaust_in_min)).strftime("%H:%M")
            _headline = f'cap at <em>{_hit}</em>'
        else:
            _headline = 'under cap <em>this window</em>'
        _sub = (
            f'burn · {fmt_tokens(int(_burn_per_min))}/min'
            if _burn_per_min > 0 else 'burn · idle'
        )

        # Next scheduled routines — hardcoded schedule until real cron wired in
        _scheduled = [
            ("17:00", "evening digest"),
            ("22:00", "vault compact"),
            ("09:00", "morning brief"),
        ]
        _now_dt = datetime.now()
        _sched_rows = []
        for hhmm, label in _scheduled:
            _h, _m = [int(x) for x in hhmm.split(":")]
            _next = _now_dt.replace(hour=_h, minute=_m, second=0, microsecond=0)
            if _next <= _now_dt:
                _next = _next + timedelta(days=1)
            _sched_rows.append((_next, hhmm, label))
        _sched_rows.sort(key=lambda r: r[0])
        _sched_html = '<div class="cpt-sched">'
        for dt, hhmm, label in _sched_rows[:2]:
            _sched_html += (
                '<div class="cpt-sched-row">'
                f'<span class="cpt-sched-time">{hhmm}</span>'
                f'<span class="cpt-sched-label">{label}</span>'
                f'<span class="cpt-sched-in">in {fmt_time_until(int(dt.timestamp()))}</span>'
                '</div>'
            )
        _sched_html += '</div>'

        st.markdown(
            '<div class="cpt-forecast">'
            f'<div class="cpt-forecast-head">forecast · 5h'
            f'<span class="cpt-forecast-sub">{_sub}</span></div>'
            f'<div class="cpt-forecast-head" '
            'style="font-size:0.7rem;color:var(--fg-dim);margin-bottom:0;">'
            f'{_headline}</div>'
            '<div class="cpt-forecast-track">'
            f'<div class="cpt-forecast-elapsed" style="width:{_elapsed_pct:.1f}%"></div>'
            f'<div class="cpt-forecast-proj" '
            f'style="left:{_proj_left:.1f}%;width:{_proj_width:.1f}%"></div>'
            f'<div class="cpt-forecast-now" style="left:{_now_pct:.1f}%"></div>'
            '</div>'
            '<div class="cpt-forecast-legend">'
            '<span><em>█</em> elapsed</span>'
            '<span><em>▨</em> projected</span>'
            '<span><em>│</em> now</span>'
            f'<span>resets · {fmt_time_until(five_h_reset)}</span>'
            '</div>'
            f'{_sched_html}'
            '</div>',
            unsafe_allow_html=True,
        )

        # ——— Vault pulse ———
        pulse_items = list_vault_pulse(6)
        if pulse_items:
            pulse_html = '<div class="cpt-pulse-card"><div class="cpt-cat">vault pulse</div>'
            for it in pulse_items:
                try:
                    uri = obsidian_uri(it["path"])
                except Exception:
                    uri = "#"
                pulse_html += (
                    '<div class="cpt-pulse">'
                    f'<span class="cpt-verb {it["verb"]}">{it["verb"]}</span>'
                    '<div class="cpt-pulse-main">'
                    f'<div class="cpt-pulse-name">'
                    f'<a href="{uri}" target="_blank" '
                    'style="color:inherit;text-decoration:none;">'
                    f'{html_escape(it["name"])}</a></div>'
                    f'<div class="cpt-pulse-dir">{html_escape(it["dir"])}</div>'
                    '</div>'
                    f'<span class="cpt-pulse-ago">{fmt_ago(it["age_sec"])}</span>'
                    '</div>'
                )
            pulse_html += '</div>'
            st.markdown(pulse_html, unsafe_allow_html=True)



    # ——— MAIN COLUMN ———
    with col_main:
        hero_slot = st.empty()

        def render_hero_error():
            err = st.session_state.last_error or "unknown error"
            label = (st.session_state.last_label or "skill").lower()
            hero_slot.markdown(
                f'<div class="hero-card error">'
                f'<div class="hero-label">failed · {html_escape(label)}</div>'
                f'<h2 class="hero-headline">run failed <em>·</em></h2>'
                f'<pre class="error-detail">{html_escape(err)}</pre>'
                f'<div class="error-hint">check logs or click ↻ rerun below</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        def render_hero_idle():
            if st.session_state.last_output:
                last = st.session_state.last_label
                saved_link = ""
                if st.session_state.last_saved_path:
                    saved = Path(st.session_state.last_saved_path)
                    uri = obsidian_uri(saved)
                    rel = saved.relative_to(VAULT_PATH).as_posix()
                    saved_link = (
                        f'<a class="obsidian-link" href="{uri}" target="_blank">◆ open in obsidian · {rel}</a>'
                    )

                meta_html = ""
                if st.session_state.last_cost is not None:
                    cost = st.session_state.last_cost
                    tok_in, tok_out = st.session_state.last_tokens or (None, None)
                    parts = [f'<span class="meta-val">${cost:.4f}</span>']
                    if tok_in is not None:
                        parts.append(f'<span class="meta-val">{tok_in} in</span>')
                    if tok_out is not None:
                        parts.append(f'<span class="meta-val">{tok_out} out</span>')
                    meta_html = f'<div class="meta-row">{" · ".join(parts)}</div>'

                hero_slot.markdown(
                    f'<div class="hero-card">'
                    f'<div class="hero-label">last run · {last.lower()}</div>'
                    f'<h2 class="hero-headline">complete <em>·</em></h2>'
                    f'{saved_link}'
                    f'{meta_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                hero_slot.markdown(
                    '<div class="hero-card">'
                    '<div class="hero-label">ready</div>'
                    '<h2 class="hero-headline">run a <em>skill</em> to begin'
                    '<span class="cursor-blink">█</span></h2>'
                    '<div style="color: var(--text-mute); font-size: 0.85rem; margin-top: 0.6rem;">'
                    'click a skill · press run · or type any prompt'
                    '</div></div>',
                    unsafe_allow_html=True,
                )

        def _clear_output():
            st.session_state.last_output = ""
            st.session_state.last_error = None
            st.session_state.last_saved_path = None
            st.session_state.last_cost = None
            st.session_state.last_tokens = None
            st.session_state.last_label = ""
            st.session_state.last_prompt = None

        # Rendered output (markdown) for last run
        def render_last_output():
            has_content = st.session_state.last_output or st.session_state.last_error
            if has_content and not st.session_state.running:
                with st.container():
                    col_view, col_rerun, col_toggle, col_clear = st.columns([3, 1, 0.7, 0.7])
                    with col_view:
                        st.markdown(
                            '<div class="caption-mono" style="margin-top:0.8rem;">output</div>',
                            unsafe_allow_html=True,
                        )
                    with col_rerun:
                        if st.session_state.last_prompt and st.button(
                            "↻ rerun", key="btn_rerun", use_container_width=True
                        ):
                            start_skill_run(st.session_state.last_label, st.session_state.last_prompt)
                            st.rerun()
                    with col_toggle:
                        view_toggle = st.toggle(
                            "md",
                            value=st.session_state.output_view_md,
                            key="view_toggle",
                            help="toggle markdown / raw",
                        )
                        st.session_state.output_view_md = view_toggle
                    with col_clear:
                        st.button(
                            "✕",
                            key="btn_clear_output",
                            use_container_width=True,
                            help="clear output",
                            on_click=_clear_output,
                        )

                    st.markdown('<div class="output-body">', unsafe_allow_html=True)
                    if st.session_state.output_view_md:
                        st.markdown(st.session_state.last_output)
                    else:
                        st.code(st.session_state.last_output, language="markdown")
                    st.markdown('</div>', unsafe_allow_html=True)

        # ——— RUNNING STATE: live fragment ———
        if st.session_state.running:
            @st.fragment(run_every=0.4)
            def live_hero_fragment():
                elapsed = int(time.time() - (RT.get("start_time") or time.time()))
                phase = RT.get("current_phase") or "starting"
                text_preview = RT.get("text", "")[-2500:]
                phase_log = RT.get("phases", [])
                phase_log_html = ""
                if phase_log:
                    last_phases = phase_log[-6:]
                    phase_log_html = (
                        f'<div class="phase-line">phases · '
                        + " → ".join(
                            f'<span class="phase-name">{html_escape(pretty_phase(p))}</span>'
                            for p in last_phases
                        )
                        + "</div>"
                    )

                preview_html = (
                    f'<pre class="stream-output">{html_escape(text_preview)}</pre>'
                    if text_preview else ""
                )

                label = st.session_state.active_skill or "skill"
                hero_slot.markdown(
                    f'<div class="hero-card running">'
                    f'<div class="hero-label"><span class="pulse-dot small"></span>'
                    f'running · {elapsed}s · {html_escape(pretty_phase(phase))}</div>'
                    f'<h2 class="hero-headline">{html_escape(label.lower())} <em>·</em></h2>'
                    f'{phase_log_html}'
                    f'{preview_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                if RT.get("done"):
                    finalize_run_if_done(
                        st.session_state.active_skill or "skill",
                        st.session_state.active_prompt or "",
                    )
                    st.rerun(scope="app")

            live_hero_fragment()

            # Cancel button
            st.markdown('<div class="cancel-btn">', unsafe_allow_html=True)
            if st.button("✕ cancel run", key="btn_cancel", use_container_width=False):
                cancel_current_run()
                finalize_run_if_done(
                    st.session_state.active_skill or "skill",
                    st.session_state.active_prompt or "",
                )
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        else:
            if st.session_state.last_error:
                render_hero_error()
            else:
                render_hero_idle()
            render_last_output()

        # ——— UNIFIED PROMPT + SKILL CHIPS (hidden during run — takeover UX) ———
        if "prompt_input_widget" not in st.session_state:
            st.session_state.prompt_input_widget = ""
        if "last_chip_label" not in st.session_state:
            st.session_state.last_chip_label = None

        # Autonomy preamble — wrapped invisibly around every prompt at run time
        # so users see only the task ("Run /deep-research on: …") not the
        # boilerplate ("Act autonomously. Do not ask for confirmation…").
        AUTONOMY_PREAMBLE = (
            "Act autonomously. Do not ask for confirmation. "
            "Do not use AskUserQuestion. "
        )

        def _strip_preamble(template: str) -> str:
            t = template.lstrip()
            if t.startswith(AUTONOMY_PREAMBLE.strip()):
                # tolerant strip — handle minor whitespace variants
                return t[len(AUTONOMY_PREAMBLE.strip()):].lstrip()
            return template

        def _wrap_autonomy(text: str) -> str:
            stripped = text.lstrip()
            if stripped.startswith(AUTONOMY_PREAMBLE.strip()):
                return text
            return AUTONOMY_PREAMBLE + text

        def _load_chip(template: str, label: str):
            st.session_state.prompt_input_widget = _strip_preamble(template)
            st.session_state.last_chip_label = label

        def _fire_trigger(skill: dict):
            try:
                res = subprocess.run(
                    skill["command"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if res.returncode == 0:
                    st.toast(f"▶ {skill['label']} triggered", icon="✅")
                else:
                    err = (res.stderr or res.stdout or "unknown").strip().splitlines()[-1][:120]
                    st.toast(f"✗ {skill['label']}: {err}", icon="⚠️")
            except Exception as e:
                st.toast(f"✗ {skill['label']}: {e}", icon="⚠️")

        def _clear_prompt():
            st.session_state.prompt_input_widget = ""
            st.session_state.last_chip_label = None

        clicked = None


        # ─── Prompt form (only when idle — running run owns the streaming hero)
        if not st.session_state.running:
            st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
            st.markdown('<div class="cpt-cat">prompt</div>', unsafe_allow_html=True)
            with st.form(key="form_unified", clear_on_submit=False, border=False):
                prompt_val = st.text_area(
                    "prompt",
                    placeholder="type any prompt, or pick a skill below to load a template…",
                    label_visibility="collapsed",
                    key="prompt_input_widget",
                    height=120,
                )
                b1, b2 = st.columns([3, 1])
                with b1:
                    submit = st.form_submit_button(
                        "run →",
                        use_container_width=True,
                    )
                with b2:
                    cleared = st.form_submit_button(
                        "clear",
                        use_container_width=True,
                        on_click=_clear_prompt,
                    )
                if submit:
                    text = (prompt_val or "").strip()
                    if not text:
                        st.warning("prompt empty")
                    elif "{input}" in text:
                        st.warning("replace {input} placeholder before running")
                    else:
                        label = st.session_state.last_chip_label or "Ad-hoc"
                        # Re-wrap with the autonomy preamble before dispatching
                        # so the CLI still receives the full skill invocation.
                        clicked = {"label": label, "prompt": _wrap_autonomy(text)}

        # ─── Skill chips — ALWAYS visible.
        # Click while idle: loads template into prompt box.
        # Click while a foreground run is active: queues the skill via the
        # system/queue/ intent contract — runner pool executes concurrently.
        # Streaming hero stays focused on the foreground run; queued runs
        # land as new system/runs/<uuid>.md files when complete.
        def _queue_skill(skill: dict):
            template = skill.get("prompt_template", "")
            if "{input}" in template:
                st.toast(
                    f"{skill['label']} needs input — wait for current run to finish",
                    icon="⚠️",
                )
                return
            full_prompt = _wrap_autonomy(template) if template else ""
            uid, _ = write_queue_intent(
                "ad-hoc",
                {"label": skill["label"], "prompt": full_prompt},
            )
            st.toast(f"queued · {skill['label']} · {uid[:8]}", icon="✅")

        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
        if st.session_state.running:
            st.markdown(
                '<div class="cpt-cat chip-cat" style="display:flex;align-items:center;gap:8px">'
                'skills · click to queue alongside current run'
                '<span class="v2-demo-pill" style="margin-left:auto">parallel</span>'
                '</div>',
                unsafe_allow_html=True,
            )
        _cat_rank = {c: i for i, c in enumerate(SKILL_CATEGORY_ORDER)}
        _fallback_rank = len(SKILL_CATEGORY_ORDER)
        skills_sorted = sorted(
            SKILLS,
            key=lambda s: (_cat_rank.get(s.get("category", "other"), _fallback_rank),),
        )
        _cols_per_row = 4
        for category, group in groupby(skills_sorted, key=lambda s: s.get("category", "other")):
            group_list = list(group)
            st.markdown(
                f'<div class="cpt-cat chip-cat">{html_escape(category)}</div>',
                unsafe_allow_html=True,
            )
            for row_start in range(0, len(group_list), _cols_per_row):
                row = group_list[row_start:row_start + _cols_per_row]
                cols = st.columns(_cols_per_row, gap="small")
                for i, skill in enumerate(row):
                    with cols[i]:
                        label = skill["label"]
                        desc = skill["description"]
                        key = f"chip_{category}_{label}"
                        if skill.get("disabled"):
                            st.button(label, key=key, disabled=True,
                                      use_container_width=True, help=desc)
                        elif skill.get("trigger"):
                            st.button(label, key=key, use_container_width=True,
                                      help=desc, on_click=_fire_trigger, args=(skill,))
                        elif st.session_state.running:
                            # Foreground run active → chips queue via runner
                            st.button(label, key=key, use_container_width=True,
                                      help=f"queue · {desc}",
                                      on_click=_queue_skill, args=(skill,))
                        else:
                            st.button(label, key=key, use_container_width=True,
                                      help=desc, on_click=_load_chip,
                                      args=(skill["prompt_template"], label))
                for _fill in range(len(row), _cols_per_row):
                    with cols[_fill]:
                        st.markdown("&nbsp;", unsafe_allow_html=True)

        # Trigger foreground run from form submit
        if clicked:
            st.session_state.last_label = clicked["label"]
            st.session_state.last_prompt = clicked["prompt"]
            start_skill_run(clicked["label"], clicked["prompt"])
            st.rerun()


# ── v2 audience tab — Latest Upload + audience row + YtWeekReview marquee ──
with audience_tab:
    if _layout_v == "v2":
        st.markdown('<hr class="chapter" />', unsafe_allow_html=True)

        # Latest Upload + audience row (per-tab copy)
        if _enabled_cards.get("latest_upload", True):
            _latest_aud = read_latest_video()
            _latest_aud_html = render_latest_upload(_latest_aud)
            if _latest_aud_html:
                st.markdown(_latest_aud_html, unsafe_allow_html=True)

        if _enabled_cards.get("audience_row", True):
            render_audience_row()
            st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

        # YtWeekReview marquee
        if _enabled_cards.get("yt_week_review", True):
            _ytr = parse_yt_review()
            render_yt_review_card(_ytr, tab_key="audience")

with research_tab:
    if _layout_v == "v2":
        st.markdown('<hr class="chapter" />', unsafe_allow_html=True)
        if _enabled_cards.get("morning_brief", True):
            _brief = parse_morning_brief()
            render_morning_brief(_brief)
