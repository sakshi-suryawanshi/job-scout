# Job Scout — UI Testing Guide

**App runs at:** `http://localhost:8501`

**Recommended test order:**
1. Profile → paste resume + analyze
2. Companies → fetch YC companies
3. Signals → run Serper dorking (Hidden Gems + Distress Signals) → import
4. Search → scrape HN + Remotive → score with Gemini
5. Apply → generate tailored resume for a top job → download

---

## Dashboard (Home)
- View live counts: companies tracked, new jobs, recommended jobs
- Confirm DB connection is shown as green

---

## Search (`/Search`)

**Scrape Jobs tab:**
- Set title keywords, skills, exclude keywords, max YOE
- Toggle Remote only / Global remote
- Pick sources: Greenhouse, Lever, Ashby (ATS) + RemoteOK, Remotive, WeWorkRemotely, HN Who's Hiring, HN Job Stories, Himalayas (job boards)
- Hit **Start Scraping** → watch progress bar + per-source breakdown results

**Browse Jobs tab:**
- Filter by: Status (New/Saved/Applied/Rejected), Source board, Remote only, title text search
- Sort by: Score, Desperation score, Newest, Recommended
- Open each job expander → Save / Mark Applied / Skip it

**Score Jobs tab:**
- Set scoring criteria (title keywords, skills, max YOE)
- Toggle **Gemini AI scoring** (requires GEMINI_API_KEY)
- Hit **Score All Unscored Jobs** → see scored count, avg score, distribution breakdown

**Stats tab:**
- Jobs by source, new/saved/applied/remote counts

---

## Companies (`/Companies`)

**Browse & Edit tab:**
- Filter companies by status, source, name
- Select a company → Activate/Deactivate or Delete it
- Edit full details (name, career URL, ATS type, funding stage, headcount, regions, remote-first)

**Add Single tab:**
- Manually add a company with all fields

**Bulk Upload tab:**
- Download CSV template → fill it → upload → import many companies at once

**Auto-Discovery section (bottom):**
- Fetch YC companies by batch (W24, S23, etc.) → imports into DB

---

## Signals (`/Signals`)

**Serper Dorking tab** (requires SERPER_API_KEY):
- Select categories: ATS Boards, Job Boards, Career Pages, Distress Signals, Funding Signals, Hidden Gems, GitHub Signals, Regional Gems
- Set max queries + results per query (budget monitor shown — free tier: 2,500/month)
- Hit **Run Serper Discovery** → see companies table → import to DB

**Signal Dashboard tab:**
- View unprocessed signals grouped by type (distress, funding, hidden gem)
- Mark all as processed

**Query Builder tab:**
- Load preset templates (seed startups, Africa remote, desperate founders on HN, recently funded, Japan gems)
- Write your own custom Google dork query → test it live → see extracted company name + career URL

---

## Apply (`/Apply`)

**Apply Queue tab:**
- Filter by min match score, sort by Match / Desperation / Combined
- Expand any job → **Generate Tailored Resume** button (uses Gemini)
- Download tailored resume as `.txt` or `.html` (open in browser → Print → Save as PDF)
- Select jobs → **Open in Browser** (batch of 20 tabs) → **Mark as Applied**

**Follow-Ups tab:**
- See jobs due for follow-up → Snooze 3 days / Got Response / Interview / Rejected

**Progress tab:**
- Progress bar toward 1000 job goal
- Daily application breakdown, response rate, interview funnel

---

## Profile (`/Profile`)

**Resume tab:**
- Paste your full resume → Save
- Hit **Analyze with AI** → Gemini extracts skills, experience years, preferred roles, strengths

**Preferences tab:**
- Set target roles, skills, YOE, remote preference, company size preference
