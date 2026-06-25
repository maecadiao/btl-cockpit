---
name: metrics-pull
description: "Pull all Be The Light Decor dashboard metrics. Refreshes QBO, GHL, Jobber, Facebook, Instagram, TikTok, GMB, and social comments. Appends rows to system/metrics/metrics.csv + updates last-pull.json. Trigger: 'pull metrics', '/metrics-pull', 'refresh dashboard data'."
---

Runs all pull_*.py scripts in parallel via scripts/run_all.ps1.
Each script writes its own status (ok / error) to last-pull.json.
CSV is append-only — never rewritten.

Sources:
- pull_qbo.py           — QuickBooks Online (AR, revenue MTD/YTD, open invoices)
- pull_ghl.py           — GoHighLevel (leads, pipeline, inbox, stale leads)
- pull_jobber.py        — Jobber (jobs today, this week, scheduled total)
- pull_facebook.py      — Facebook Page (followers, posts, likes)
- pull_instagram.py     — Instagram Business (followers, posts, likes)
- pull_tiktok.py        — TikTok (followers, posts, likes — manual or Display API)
- pull_gmb.py           — Google My Business (rating, review count)
- pull_social_comments.py — Aggregate FB+IG comments → social-comments.json
