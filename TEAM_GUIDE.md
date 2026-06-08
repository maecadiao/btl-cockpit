# BTL Agentic OS Dashboard — Team Guide

**Your AI-powered command center for Be The Light Decor.**
No coding knowledge needed. If you can use a website, you can use this.

---

## How to open it

Go to this link in any browser (Chrome, Safari, Edge — your phone works too):

**👉 https://btl-os-dashboard.streamlit.app**

Bookmark it. That's the only link you'll ever need.

---

## What is this dashboard?

Think of it as the BTL team's home base — one screen where you can see what's happening across sales, operations, finances, and social media, and where you can kick off AI-powered tasks with a single click.

The AI behind it is Claude (made by Anthropic — the same company that makes Claude.ai). When you click a skill button, Claude runs a task on your behalf and delivers a result: a written summary, a drafted email, a report, etc.

> 🟡 **Right now the dashboard is in Demo Mode.** This means the numbers you see are sample data, not your real business data. Everything still looks and works correctly — it's just not connected to live QuickBooks, GHL, or Jobber yet. That connection is coming soon.

---

## The screen layout

When you open the dashboard you'll see:

```
┌─────────────────────────────────────────────────────┐
│  BE THE LIGHT DECOR — AGENTIC OS        [status]    │
├─────────────────────────────────────────────────────┤
│  INBOX DIGEST  CREW BRIEF  KPI DIGEST  ...  (buttons)│
├──────────────────────────────────────────────────────┤
│  overview │ ghl │ jobber │ social │ quickbooks  (tabs)│
├──────────────────────────────────────────────────────┤
│                                                      │
│           Tab content shows here                     │
│                                                      │
└──────────────────────────────────────────────────────┘
```

Three layers, top to bottom:
1. **The header** — title + status indicator
2. **The quick action buttons** — your 5 most-used AI tasks
3. **The tabs** — different views of the business

---

## The status indicator (top right)

You'll see a small pill that says either **idle** or a skill name.

| What it shows | What it means |
|---|---|
| 🔘 **idle** | The system is on and ready. Nothing is running right now. |
| 🟡 **Pipeline Review** *(or any skill name)* | Claude is actively working on that task. Wait for it to finish. |

**idle is good.** It's like a car at a red light — engine's running, ready to go.

---

## The quick action buttons

These 5 buttons are your most-used daily tasks. Click one and Claude starts working immediately.

### INBOX DIGEST
> Scans your business inbox and gives you a plain-English summary of what needs attention — new leads, client questions, follow-ups. Instead of reading 30 emails, you get a 1-page briefing.

### CREW BRIEF
> Pulls today's jobs from Jobber and generates a morning briefing for your crew — who goes where, what they're installing, any notes. Great to run every morning before the team heads out.

### KPI DIGEST
> Generates a weekly scorecard of your key numbers — revenue, leads, jobs, invoices — with color-coded status (🟢 on track, 🟡 watch this, 🔴 needs attention). Good for Monday morning reviews.

### BILLING DIGEST
> Pulls your open invoices from QuickBooks and summarizes who owes what, how overdue each invoice is, and what to follow up on first. Saves Mae an hour of digging.

### PIPELINE REVIEW
> Gives you a full rundown of your GHL sales pipeline — active leads, where they are in the process, who hasn't been followed up with, and what your projected close looks like.

---

## The tabs

### OVERVIEW tab
Your daily home base. Shows:
- **Schedule** — today's jobs and events pulled from your calendar
- **Activity Feed** — a log of what the AI has done recently (which skills ran, when, and the result)
- **Agent Runs Chart** — a 30-day bar chart showing how many AI tasks have been run

This is the tab to check first thing in the morning.

---

### GHL tab
*GHL = GoHighLevel, your CRM / lead tracking system.*

Shows your sales pipeline at a glance:
- **Active Leads** — contacts currently in your pipeline
- **New Leads (7 days)** — fresh inquiries this week
- **Pipeline Value** — estimated total revenue if all open deals close

> 🟡 Currently showing demo numbers. Live GHL data connects once the runner is active.

---

### JOBBER tab
*Jobber is your field operations and job scheduling software.*

Shows your job workload:
- **Jobs Today** — what's on the schedule today
- **Jobs This Week** — total confirmed jobs this week
- **Crew Utilization** — how much of your available crew time is booked

> 🟡 Currently showing demo numbers. Live Jobber data connects once the runner is active.

---

### SOCIAL tab
Shows your social media audience numbers:
- **Facebook** — follower count and average likes per post
- **Instagram** — follower count and average reach per post

This is where you can track whether your social content is growing the audience over time.

> 🟡 Currently showing demo numbers. Live social data connects once the runner is active.

---

### QUICKBOOKS tab
*QuickBooks is your accounting software.*

Shows your financial snapshot:
- **Revenue MTD** — how much you've billed this month
- **Open Invoices** — how many invoices are waiting to be paid
- **Net Profit MTD** — revenue minus expenses for the month
- **AR Balance** — total money owed to BTL across all clients

> 🟡 Currently showing demo numbers. Live QuickBooks data connects once the runner is active.

---

## All 20 skill buttons (on the Overview tab)

In addition to the 5 quick buttons at the top, you'll find all 20 BTL skills organized by department in the Overview tab. Here's what each one does:

### 📣 Marketing
| Button | What it does | Needs input? |
|---|---|---|
| **Caption Writer** | Writes a social media caption for a photo or project | Yes — describe the post |
| **Content Ideas** | Brainstorms content ideas for Facebook and Instagram | No |
| **Ad Performance** | Summarizes how your recent ads are performing | No |
| **Inbox Digest** | Summarizes inbox messages needing attention | No |
| **Inbox Reply Draft** | Drafts a reply to a specific message | Yes — paste or describe the message |

### 💰 Sales
| Button | What it does | Needs input? |
|---|---|---|
| **Pipeline Review** | Full GHL pipeline status and next actions | No |
| **Quote Follow-up** | Writes a follow-up email for a sent quote | Yes — client name + job + days since quote |
| **Lead Qualifier** | Scores and qualifies an inbound lead | Yes — paste lead info |
| **Write Proposal** | Generates a professional project proposal | Yes — property type, scope, location |
| **Sales Call Prep** | Pre-call briefing for a consultation | Yes — client name + situation |

### 🗂️ Admin
| Button | What it does | Needs input? |
|---|---|---|
| **Job Posting** | Writes a job listing for a BTL role | Yes — role title |
| **Onboarding Doc** | Creates an onboarding guide for a new hire | Yes — role being onboarded |
| **Write SOP** | Writes a standard operating procedure | Yes — process name |
| **Lead Nurture Email** | Writes a nurture email for a cold/warm lead | Yes — lead name + context |
| **Billing Digest** | Summarizes open invoices from QuickBooks | No |
| **Meeting Notes** | Turns raw notes into a structured summary | Yes — paste your notes |

### 🏗️ Production
| Button | What it does | Needs input? |
|---|---|---|
| **Crew Brief** | Daily crew briefing — jobs, locations, assignments | No |

### 📊 Executive
| Button | What it does | Needs input? |
|---|---|---|
| **P&L Narrative** | Plain-English analysis of your profit & loss | No |
| **KPI Digest** | Weekly KPI scorecard with traffic-light status | No |
| **Revenue Growth** | Multi-period revenue trends + opportunities + risks | No |

---

## What happens when you click a skill button

1. **You click the button** (e.g. "Pipeline Review")
2. The status indicator in the top right changes from **idle** → **Pipeline Review**
3. Claude starts reading your data and writing the output
4. When it's done, the result appears on screen — usually a written report, summary, or draft
5. The status goes back to **idle**

Some skills have an **input box** that appears when you click them. Just type what it asks for (e.g. a client name, or paste some notes) and hit Enter to run it.

---

## What Demo Mode means

You'll see a small **demo mode** pill near the top of the page. This means:

✅ The dashboard loads and looks exactly as it will with real data  
✅ All buttons and tabs work  
✅ The layout, colors, and structure are final  
❌ The numbers (revenue, leads, jobs, followers) are sample placeholders  
❌ Skill buttons won't actually execute yet (they need the API key to be set up)

Demo mode will be turned off by Mae once the Anthropic API key is configured and the data connections are live. After that, every number you see is real.

---

## Quick reference card

| I want to… | Do this |
|---|---|
| See today's schedule | Click **OVERVIEW** tab |
| Check the sales pipeline | Click **GHL** tab or hit **PIPELINE REVIEW** button |
| See who's working today | Click **JOBBER** tab or hit **CREW BRIEF** button |
| Check unpaid invoices | Click **QUICKBOOKS** tab or hit **BILLING DIGEST** button |
| Write a social caption | Find **Caption Writer** in the Overview skills grid |
| Draft a quote follow-up | Find **Quote Follow-up** in the Overview skills grid |
| Check social media growth | Click **SOCIAL** tab |
| See all AI tasks that ran | Check the **Activity Feed** on the OVERVIEW tab |

---

## Questions?

Contact **Mae Cadiao** for anything related to the dashboard.

The dashboard lives at: **https://btl-os-dashboard.streamlit.app**
