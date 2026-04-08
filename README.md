# Dada Science

Rigorous statistical analysis of toddler behavior — plus a real-time data logging app on Raspberry Pi and a library book recommender.

> *noun* **dada scientist** /ˈdɑːdɑː ˈsaɪəntɪst/ — a data scientist hired, ostensibly against their better judgement, to raise a toddler. Applies rigorous statistical methods to questions that would embarrass a peer reviewer but are of urgent operational importance at 6:45 AM.

A collection of analytical studies on toddler behavior — sleep, snacks, potty training, Easter eggs — conducted with the same seriousness one would bring to modeling commodity futures. The repo also includes a real-time data logging app (Dada Tracker) running on a Raspberry Pi and a library book recommendation engine. All study data is **simulated/synthetic**. No actual toddlers were mined for data without consent, or denied their Cocopuff incentive in the name of science.

---

## Studies

| Script | Description | Method |
|--------|-------------|--------|
| `potty_training.py` | Time Until Potty (TuP) by location, book reading, and incentive type | Simulated week of events; scatter + boxplot visualizations |
| `snack_sugar_content.py` | Tantrum duration drivers across 1,000 synthetic snack records | Two-way ANOVA + Tukey HSD; time-of-day explains 76.9% of variance |
| `nap_timeseries.py` | 141-day Jul–Nov time series: daylight + DST end drive nap collapse | STL decomposition (trend, seasonal, residual) |
| `missed_nap_lag.py` | 130-day lagged analysis of missed naps vs. overnight sleep quality | ARIMAX with "berry season" as natural experiment |
| `Poisson_eggs.py` | Easter egg selectivity vs. random baseline | Poisson fits, KL divergence, sparsity metrics |
| `winter_spring_transition.py` | Jan–Mar parenting shift (TV → books) + DST spring-forward effect | Behavioral transition tracking, nap latency analysis |

Run any study directly: `python potty_training.py` — each outputs PNG visualizations.

---

## Dada Tracker

A mobile-first Flask app running on a Raspberry Pi that logs toddler events in real time.

**Tracks**: sleep/naps, food & drink, activities, meltdowns (severity + trigger), potty, mood.

**Stack**: Flask, SQLite (7-table schema), Jinja2 templates, systemd on Pi, Tailscale VPN for remote access.

```bash
cd tracker
python app.py   # http://192.168.88.9:5000 (local) or Tailscale IP
```

Pull data to a laptop for notebook analysis:

```python
from tracker.analysis import TrackerDB
db = TrackerDB()
db.sync()                          # scp from Pi
sleep_df    = db.sleep()
meltdown_df = db.meltdowns()
db.daily_summary('2025-03-25')
```

See `tracker/README.md` for full schema and systemd management.

---

## Library Recommender

A CLI tool that scrapes the Sno-Isle library catalog into SQLite, learns taste from user ratings (1–5), and recommends books via TF-IDF + cosine similarity.

**Stack**: Python, Click, Rich, scikit-learn, Requests, SQLite, BiblioCommons API.

```bash
cd library_recommender
python catalog_scraper.py          # Scrape catalog (~165k books, ~45 min)
./library recommend                # 5 best matches + 2 experimental + 3 hidden gems
./library rate                     # Rate returned books
./library hold 42 --branch 18      # Place a hold via BiblioCommons
./library export-ratings           # Sync ratings to JSON for cross-machine use
```

Multi-user capable — separate rating histories per parent. See `library_recommender/README.md`.

---

## Tech

Python, Flask, SQLite, pandas, NumPy, matplotlib, seaborn, statsmodels (ANOVA/STL/ARIMAX), scikit-learn (TF-IDF), Click, Rich, Requests, Raspberry Pi, Tailscale

---

## Data

All study datasets are fully synthetic, generated with seeded NumPy for reproducibility. Tracker data lives on the Pi in a `.gitignored` database — no real data is committed to this repo.
