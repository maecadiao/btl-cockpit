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
    --card-tone-youtube:    rgba(255, 51, 51, 0.10);
    --card-tone-youtube-bd: rgba(255, 51, 51, 0.32);
    --card-tone-instagram:    rgba(225, 48, 108, 0.10);
    --card-tone-instagram-bd: rgba(225, 48, 108, 0.32);
    --card-tone-tiktok:    rgba(0, 240, 255, 0.08);
    --card-tone-tiktok-bd: rgba(0, 240, 255, 0.30);
    --card-tone-claude:    rgba(201, 100, 66, 0.10);
    --card-tone-claude-bd: rgba(201, 100, 66, 0.36);
}

/* ── Latest Upload card ───────────────────────────────────── */
.v2-latest {
    position: relative;
    background: var(--bg-card);
    border: 1px solid var(--ring-soft);
    border-radius: 4px;
    padding: 0.95rem 1.1rem 0.9rem 1.4rem;
    margin: 0.5rem 0 1rem 0;
    overflow: hidden;
}
.v2-latest::before {
    content: "";
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
    background: linear-gradient(180deg, var(--accent) 0%, rgba(201,100,66,0.18) 100%);
}
.v2-latest::after {
    content: "▶";
    position: absolute;
    right: 1.0rem;
    bottom: 0.45rem;
    font-size: 3.2rem;
    line-height: 1;
    color: var(--accent);
    opacity: 0.06;
    pointer-events: none;
    font-family: 'JetBrains Mono', monospace;
}
.v2-latest-head {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--fg-dim);
    margin-bottom: 0.35rem;
}
.v2-latest-head .v2-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--good);
    box-shadow: 0 0 6px var(--good);
}
.v2-latest-head .v2-dot.mock { background: var(--warn); box-shadow: 0 0 6px var(--warn); }
.v2-latest-head .v2-dot.err  { background: var(--danger); box-shadow: 0 0 6px var(--danger); }
.v2-latest-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.05rem;
    color: var(--fg);
    line-height: 1.25;
    margin: 0.05rem 0 0.4rem 0;
    font-weight: 500;
    max-width: 78%;
}
.v2-latest-title a { color: inherit; text-decoration: none; border-bottom: 1px dotted transparent; }
.v2-latest-title a:hover { border-bottom-color: var(--accent); color: var(--accent); }
.v2-latest-stats {
    display: flex;
    gap: 1.4rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: var(--fg-dim);
}
.v2-latest-stats .v2-stat-val { color: var(--fg); font-weight: 500; }
.v2-latest-stats .v2-stat-lbl { color: var(--fg-mute); margin-left: 0.3rem; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; }

/* ── Audience metric cards ───────────────────────────────── */
.v2-audience-card {
    position: relative;
    background: var(--bg-card);
    border: 1px solid var(--ring-soft);
    border-radius: 4px;
    padding: 0.85rem 1rem 0.85rem 1rem;
    overflow: hidden;
    min-height: 92px;
}
.v2-audience-card[data-tone="youtube"]   { background: linear-gradient(135deg, var(--card-tone-youtube) 0%, var(--bg-card) 70%); border-color: var(--card-tone-youtube-bd); }
.v2-audience-card[data-tone="instagram"] { background: linear-gradient(135deg, var(--card-tone-instagram) 0%, var(--bg-card) 70%); border-color: var(--card-tone-instagram-bd); }
.v2-audience-card[data-tone="tiktok"]    { background: linear-gradient(135deg, var(--card-tone-tiktok) 0%, var(--bg-card) 70%); border-color: var(--card-tone-tiktok-bd); }
.v2-audience-card[data-tone="claude"]    { background: linear-gradient(135deg, var(--card-tone-claude) 0%, var(--bg-card) 70%); border-color: var(--card-tone-claude-bd); }
.v2-audience-watermark {
    position: absolute;
    right: -8px;
    bottom: -18px;
    font-size: 3.6rem;
    line-height: 1;
    opacity: 0.08;
    pointer-events: none;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
}
.v2-audience-head {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--fg-dim);
    margin-bottom: 0.4rem;
}
.v2-audience-head .v2-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--good);
    box-shadow: 0 0 5px var(--good);
}
.v2-audience-head .v2-dot.mock { background: var(--warn); box-shadow: 0 0 5px var(--warn); }
.v2-audience-head .v2-dot.err  { background: var(--danger); box-shadow: 0 0 5px var(--danger); }
.v2-audience-head .v2-dot.stale { background: var(--fg-mute); box-shadow: none; }
.v2-audience-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.7rem;
    line-height: 1;
    color: var(--fg);
    font-weight: 600;
    margin: 0.2rem 0 0.3rem 0;
}
.v2-audience-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: var(--fg-mute);
    letter-spacing: 0.02em;
}

/* ── TokenBurn marquee (commit 6) ─────────────────────────── */
.v2-tb-wrap {
    position: relative;
    background: var(--bg-card);
    border: 1px solid var(--ring-soft);
    border-radius: 4px;
    padding: 1.1rem 1.3rem 1.2rem 1.3rem;
    margin: 0.5rem 0 1rem 0;
    overflow: hidden;
}
.v2-tb-wrap::before,
.v2-tb-wrap::after,
.v2-tb-wrap > .v2-hud-bl,
.v2-tb-wrap > .v2-hud-br {
    content: "";
    position: absolute;
    width: 14px; height: 14px;
    border: 1.5px solid var(--accent);
    opacity: 0.7;
}
.v2-tb-wrap::before { top: 6px; left: 6px;   border-right: none; border-bottom: none; }
.v2-tb-wrap::after  { top: 6px; right: 6px;  border-left: none;  border-bottom: none; }
.v2-tb-wrap > .v2-hud-bl { bottom: 6px; left: 6px;  border-right: none; border-top: none; }
.v2-tb-wrap > .v2-hud-br { bottom: 6px; right: 6px; border-left: none;  border-top: none; }
.v2-tb-head {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--fg-dim);
    margin-bottom: 0.2rem;
}
.v2-tb-head .v2-live {
    color: var(--accent);
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
}
.v2-tb-head .v2-live::before {
    content: "●";
    color: var(--accent);
    animation: v2-blink 1.6s infinite;
}
@keyframes v2-blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
.v2-tb-pct {
    font-family: 'JetBrains Mono', monospace;
    font-size: 3.6rem;
    line-height: 1;
    font-weight: 600;
    color: var(--fg);
    margin: 0.3rem 0 0.4rem 0;
    letter-spacing: -0.02em;
}
.v2-tb-pct em { font-style: normal; color: var(--accent); font-size: 1.6rem; vertical-align: super; margin-left: 0.15rem; }
.v2-tb-track {
    position: relative;
    height: 18px;
    background:
        repeating-linear-gradient(
            45deg,
            rgba(176, 174, 165, 0.05) 0,
            rgba(176, 174, 165, 0.05) 4px,
            rgba(0,0,0,0) 4px,
            rgba(0,0,0,0) 8px
        ),
        rgba(20, 21, 22, 0.6);
    border: 1px solid var(--ring-soft);
    border-radius: 2px;
    overflow: hidden;
    margin-top: 0.3rem;
}
.v2-tb-fill {
    position: absolute;
    left: 0; top: 0; bottom: 0;
    background: linear-gradient(90deg, var(--accent) 0%, #e8825c 100%);
    transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}
.v2-tb-fill.warn { background: linear-gradient(90deg, #d97757 0%, var(--warn) 100%); }
.v2-tb-fill.danger { background: linear-gradient(90deg, var(--warn) 0%, var(--danger) 100%); }
.v2-tb-proj {
    position: absolute;
    top: 0; bottom: 0;
    background: repeating-linear-gradient(
        45deg,
        rgba(201,100,66,0.22) 0,
        rgba(201,100,66,0.22) 4px,
        rgba(0,0,0,0) 4px,
        rgba(0,0,0,0) 8px
    );
}
.v2-tb-scan {
    position: absolute;
    top: 0; bottom: 0;
    width: 30px;
    background: linear-gradient(90deg,
        rgba(255, 211, 181, 0) 0%,
        rgba(255, 211, 181, 0.45) 50%,
        rgba(255, 211, 181, 0) 100%);
    animation: v2-scan 4s linear infinite;
    pointer-events: none;
}
@keyframes v2-scan {
    0%   { left: -30px; }
    100% { left: 100%; }
}
.v2-tb-comet {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 16px; height: 16px;
    background: radial-gradient(circle, #ffd3b5 0%, rgba(255,211,181,0) 70%);
    mix-blend-mode: screen;
    animation: v2-breath 1.6s ease-in-out infinite;
    pointer-events: none;
}
@keyframes v2-breath {
    0%,100% { opacity: 0.5; transform: translate(-50%, -50%) scale(1); }
    50%     { opacity: 1.0; transform: translate(-50%, -50%) scale(1.4); }
}
.v2-tb-ticks {
    display: flex;
    justify-content: space-between;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    color: var(--fg-mute);
    margin-top: 0.3rem;
    letter-spacing: 0.05em;
}
.v2-tb-footer {
    display: flex;
    justify-content: space-between;
    margin-top: 0.5rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--fg-dim);
}
.v2-tb-footer .v2-tb-counts em { font-style: normal; color: var(--fg); }
.v2-tb-footer .v2-tb-proj-label { color: var(--accent); }

/* ── YtWeekReview card (commit 7) ─────────────────────────── */
.v2-ytr-card {
    background: var(--bg-card);
    border: 1px solid var(--ring-soft);
    border-radius: 4px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0 1rem 0;
}
.v2-ytr-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 0.5rem;
}
.v2-ytr-head .v2-ytr-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--fg-dim);
}
.v2-ytr-head .v2-ytr-actions {
    display: flex;
    gap: 0.6rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
}
.v2-ytr-head .v2-ytr-actions a {
    color: var(--accent);
    text-decoration: none;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.v2-ytr-head .v2-ytr-actions a:hover { text-decoration: underline; }
.v2-ytr-tldr {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: var(--fg-dim);
    line-height: 1.45;
    margin: 0.3rem 0 0.6rem 0;
    padding-left: 1rem;
}
.v2-ytr-tldr li { margin: 0.15rem 0; }
.v2-chip-row {
    display: flex; gap: 0.4rem;
    margin: 0.4rem 0;
    flex-wrap: wrap;
}
.v2-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.22rem 0.55rem;
    border: 1px solid var(--ring-soft);
    border-radius: 99px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--fg-dim);
    background: var(--bg-elev);
}
.v2-chip.hit       { color: var(--good); border-color: rgba(143,185,122,0.4); }
.v2-chip.steady    { color: var(--fg-dim); }
.v2-chip.climbing  { color: var(--warn); border-color: rgba(217,165,102,0.4); }
.v2-chip.miss      { color: var(--accent); border-color: rgba(201,100,66,0.4); }
.v2-ytr-perfs {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.6rem;
    margin-top: 0.5rem;
}
.v2-perf-card {
    border: 1px solid var(--ring-soft);
    border-radius: 4px;
    padding: 0.55rem 0.7rem;
    background: var(--bg-elev);
}
.v2-perf-card.top { border-left: 3px solid var(--good); }
.v2-perf-card.under { border-left: 3px solid var(--accent); }
.v2-perf-card .v2-perf-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.55rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--fg-mute);
}
.v2-perf-card .v2-perf-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: var(--fg);
    margin: 0.15rem 0;
    line-height: 1.3;
}

/* ── MorningBrief 2x2 grid (commit 8) ─────────────────────── */
.v2-mb-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.7rem;
    margin: 0.5rem 0 0.8rem 0;
}
.v2-mb-tile {
    background: var(--bg-card);
    border: 1px solid var(--ring-soft);
    border-radius: 4px;
    padding: 0.7rem 0.9rem;
    min-height: 130px;
}
.v2-mb-tile .v2-mb-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--fg-dim);
    margin-bottom: 0.4rem;
}
.v2-mb-tile ul {
    margin: 0;
    padding-left: 1rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.74rem;
    color: var(--fg);
    line-height: 1.45;
}
.v2-mb-tile li { margin: 0.15rem 0; }
.v2-mb-coverage {
    display: flex;
    gap: 0.6rem;
    flex-wrap: wrap;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    color: var(--fg-mute);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.5rem;
}
.v2-mb-coverage span { padding: 0.15rem 0.5rem; border: 1px solid var(--ring-soft); border-radius: 99px; }

/* ── Schedule + Daily Drivers ─────────────────────────────── */
.v2-panel {
    background: var(--bg-card);
    border: 1px solid var(--ring-soft);
    border-radius: 4px;
    padding: 0.8rem 1rem;
}
.v2-panel-head {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--fg-dim);
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.v2-sched-row {
    display: grid;
    grid-template-columns: 60px 1fr;
    gap: 0.6rem;
    align-items: center;
    padding: 0.32rem 0;
    border-bottom: 1px dashed var(--ring-soft);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
}
.v2-sched-row:last-child { border-bottom: none; }
.v2-sched-row .v2-sched-time { color: var(--accent); font-weight: 500; }
.v2-sched-row .v2-sched-label { color: var(--fg); }
.v2-driver-row {
    display: grid;
    grid-template-columns: 18px 1fr;
    gap: 0.6rem;
    align-items: center;
    padding: 0.32rem 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: var(--fg);
}
.v2-driver-row .v2-driver-box {
    width: 14px; height: 14px;
    border: 1px solid var(--ring-mid);
    border-radius: 2px;
    display: inline-block;
    text-align: center;
    line-height: 12px;
    font-size: 0.7rem;
    color: var(--accent);
}
.v2-driver-row.done .v2-driver-box { background: var(--accent); color: var(--bg); border-color: var(--accent); }
.v2-driver-row.done .v2-driver-label { color: var(--fg-mute); text-decoration: line-through; }
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

# Terminal launch via query-param (claude code pill in quicknav)
_action_q = st.query_params.get("action")
if _action_q == "terminal":
    try:
        open_claude_terminal()
        st.toast("Terminal opened at vault.", icon="✅")
    except Exception as e:
        st.toast(f"Failed: {e}", icon="⚠️")
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
    f'<div class="caption-mono title-crumb">vault · {VAULT_PATH.name} · plan · {CLAUDE_PLAN} · permission · {PERMISSION_MODE}</div>'
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
import config as _cfg
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


five_h_reset = (rate_limits.get("five_hour") or {}).get("resets_at")
week_reset = (rate_limits.get("weekly") or {}).get("resets_at")

five_h_tokens = usage["five_hour"]["total"]
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

m1, m2, m3 = st.columns(3, gap="small")
with m1:
    st.markdown(
        render_gauge(
            "5-hour window",
            f"resets · {fmt_time_until(five_h_reset)}",
            five_h_tokens,
            LIMITS["five_hour_tokens"],
            fmt_tokens(five_h_tokens),
            fmt_tokens(LIMITS["five_hour_tokens"]),
            f"· {usage['five_hour']['sessions']} sessions",
            delta=_5h_delta,
        ),
        unsafe_allow_html=True,
    )
with m2:
    st.markdown(
        render_gauge(
            "weekly window",
            f"resets · {fmt_time_until(week_reset)}",
            week_tokens,
            LIMITS["weekly_tokens"],
            fmt_tokens(week_tokens),
            fmt_tokens(LIMITS["weekly_tokens"]),
            f"· {usage['weekly']['sessions']} sessions",
            delta=_wk_delta,
        ),
        unsafe_allow_html=True,
    )
with m3:
    st.markdown(
        render_gauge(
            f"routines · {CLAUDE_PLAN}",
            "resets · midnight",
            routines_today,
            LIMITS["daily_routine_runs"],
            str(routines_today),
            str(LIMITS["daily_routine_runs"]),
            f"{fmt_cost(today_cost)} today",
            delta=_rt_delta,
        ),
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# LATEST UPLOAD CARD (v2)
# ═══════════════════════════════════════════════════════════

_enabled_cards = getattr(_cfg, "ENABLED_CARDS", {}) or {}
if _enabled_cards.get("latest_upload", True):
    _latest = read_latest_video()
    _latest_html = render_latest_upload(_latest)
    if _latest_html:
        st.markdown(_latest_html, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# RUNS-PER-DAY CHART
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


st.markdown(
    '<div class="chart-card parchment">'
    '<div class="chart-title">agentic OS · cumulative activity · 30d '
    f'<span>· {_cum_total:,} total · {_cum_30d} last 30d</span></div>'
    + _build_activity_svg(df_cum)
    + '</div>',
    unsafe_allow_html=True,
)


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

    def _load_chip(template: str, label: str):
        st.session_state.prompt_input_widget = template
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
                st.toast(f"▶ {skill['label']} triggered", icon="✓")
            else:
                err = (res.stderr or res.stdout or "unknown").strip().splitlines()[-1][:120]
                st.toast(f"✗ {skill['label']}: {err}", icon="⚠")
        except Exception as e:
            st.toast(f"✗ {skill['label']}: {e}", icon="⚠")

    def _clear_prompt():
        st.session_state.prompt_input_widget = ""
        st.session_state.last_chip_label = None

    clicked = None


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
                    clicked = {"label": label, "prompt": text}

        # Skill chips — st.button grid (no page reload, WebSocket rerun)
        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
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
            # Chunk into rows of _cols_per_row
            for row_start in range(0, len(group_list), _cols_per_row):
                row = group_list[row_start:row_start + _cols_per_row]
                cols = st.columns(_cols_per_row, gap="small")
                for i, skill in enumerate(row):
                    with cols[i]:
                        label = skill["label"]
                        desc = skill["description"]
                        key = f"chip_{category}_{label}"
                        if skill.get("disabled"):
                            st.button(
                                label,
                                key=key,
                                disabled=True,
                                use_container_width=True,
                                help=desc,
                            )
                        elif skill.get("trigger"):
                            st.button(
                                label,
                                key=key,
                                use_container_width=True,
                                help=desc,
                                on_click=_fire_trigger,
                                args=(skill,),
                            )
                        else:
                            st.button(
                                label,
                                key=key,
                                use_container_width=True,
                                help=desc,
                                on_click=_load_chip,
                                args=(skill["prompt_template"], label),
                            )
                # Fill remaining columns with empty placeholders to keep grid aligned
                for _fill in range(len(row), _cols_per_row):
                    with cols[_fill]:
                        st.markdown("&nbsp;", unsafe_allow_html=True)

        # Trigger run
        if clicked:
            st.session_state.last_label = clicked["label"]
            st.session_state.last_prompt = clicked["prompt"]
            start_skill_run(clicked["label"], clicked["prompt"])
            st.rerun()
