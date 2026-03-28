# Project Context — dada_science

Use this file to resume work in a new session.
Hand it to Claude at the start: "Here's the context file for dada_science."

---

## What this is

Multi-component research infrastructure applying rigorous statistical methods to toddler behavior data. Three sub-projects: (1) analytical studies, (2) a real-time logging app (Dada Tracker) running on a Raspberry Pi, and (3) a library book recommender.

All study datasets are fully synthetic (seeded NumPy). Tracker data lives on the Pi in a `.gitignored` database — no real data is committed to this repo.

---

## Sub-projects

> Personal tracker (Simon's health/habit logging) has moved to **OmaElu/personal_tracker/**.

### 1. Statistical Studies (scripts at repo root)

| Script | Method | Key result |
|---|---|---|
| `potty_training.py` | Scatter + boxplot | TuP by location/book/incentive |
| `snack_sugar_content.py` | Two-way ANOVA + Tukey HSD | Time-of-day explains 76.9% of variance |
| `nap_timeseries.py` | STL decomposition | DST + daylight drive nap collapse |
| `missed_nap_lag.py` | ARIMAX | Berry season as natural experiment |
| `Poisson_eggs.py` | KL divergence | Easter egg selectivity vs. random baseline |
| `winter_spring_transition.py` | Behavioral transition tracking | TV → books shift, DST spring-forward effect |

Run any: `python <script>.py` — outputs PNG visualizations.

---

### 2. Dada Tracker (Raspberry Pi deployment)

```
tracker/
├── app.py           — Flask entry point
├── models.py        — 7-table SQLite schema
├── templates/       — Jinja2 mobile-first UI
└── analysis.py      — TrackerDB helper for laptop analysis
```

**Tracks:** sleep/naps, food & drink, activities (including dedicated screen time timer), meltdowns (severity + trigger), potty, mood, bath.

**Infrastructure:** systemd service on Pi (HST timezone), Tailscale VPN for remote access.

**Recent additions (2026-03-28):**
- Nap timing recommendation banner — weighted rolling average of historical wake windows; cold-start default 5h; 3pm cutoff; ±30min window
- Screen time start/stop toggle on home screen — stored as activity with description "Screen Time"
- Time pickers on all edit forms (datetime-local for event_time fields, time for HH:MM fields)
- Edit form for wake/dressed/bed times (`/edit/daily/<date>`)

**Local access:** `http://192.168.88.9:5000`

**Pull data to laptop:**
```python
from tracker.analysis import TrackerDB
db = TrackerDB()
db.sync()   # scp from Pi
sleep_df    = db.sleep()
meltdown_df = db.meltdowns()
db.daily_summary('2025-03-25')
```

---

### 3. Library Book Recommender

```
library_recommender/
├── catalog_scraper.py   — scrapes Sno-Isle catalog (~165k books, ~45 min)
├── library              — CLI entry point (Click)
└── ...
```

**Run:**
```bash
python catalog_scraper.py          # first-time scrape
./library recommend                # 5 best + 2 experimental + 3 hidden gems
./library rate                     # rate returned books
./library hold 42 --branch 18      # place a hold via BiblioCommons
./library export-ratings           # sync ratings to JSON
```

Multi-user — separate rating histories per parent. TF-IDF + cosine similarity for recommendations.

---

## Stack

Python, Flask, SQLite, pandas, NumPy, statsmodels (ANOVA/STL/ARIMAX), scikit-learn (TF-IDF), matplotlib, seaborn, Click, Rich, Requests, Raspberry Pi, Tailscale

---

## Status

Ongoing. Tracker is live on the Pi. Studies and recommender are periodically updated.
[Update with current state when resuming.]

---

## Personal tracker integration

`rejection_matrix` uses the personal tracker DB at:
`../OmaElu/personal_tracker/personal.db`
(categories: "Job Search", "LinkedIn")
