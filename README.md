# Dada Science

> *noun* **dada scientist** /ˈdɑːdɑː ˈsaɪəntɪst/ — a data scientist hired, ostensibly against their better judgement, to raise a toddler. Applies rigorous statistical methods to questions that would embarrass a peer reviewer but are of urgent operational importance at 6:45 AM.

This repo is a collection of analytical studies on toddler behavior — sleep, snacks, potty training, Easter eggs — conducted with the same seriousness one would bring to, say, modeling commodity futures. All data is **simulated/synthetic**. No actual toddlers were harmed, mined for data without consent, or denied their Cocopuff incentive in the name of science.

---

## Studies

| Script | Description |
|--------|-------------|
| `potty_training.py` | Simulates one week of potty training events, modeling Time Until Potty (TuP) by location, book-reading behavior, and daily incentive type (Cocopuff / Yoggie / M&M). |
| `snack_sugar_content.py` | 1,000 snack records across three snack types; two-way ANOVA reveals time of day (not sugar) accounts for 76.9% of tantrum duration variance. |
| `nap_timeseries.py` | 141-day Jul–Nov time series with STL decomposition showing how declining daylight and DST end (Nov 2) drive nap collapse and meltdown rise. |
| `missed_nap_lag.py` | 130-day May–Sep lagged analysis of missed naps and overnight sleep quality; ARIMAX model with "berry season" as a natural experiment in nap compliance. |
| `Poisson_eggs.py` | Easter egg hunt data compared against a random baseline using Poisson fits, KL divergence, and sparsity metrics — demonstrating the toddler is far more selective than chance. |
| `winter_spring_transition.py` | Jan–Mar winter-to-spring transition tracking a parenting behavior shift (TV → books) and DST spring-forward effect on nap latency. |

---

## Library Recommender

The `library_recommender/` subdirectory contains a standalone tool for recommending toddler books. See its own [README](library_recommender/README.md) for details.

---

## Data

All datasets in this repository are **fully synthetic**, generated via NumPy random seeds for reproducibility. Any resemblance to an actual toddler's sleep schedule, snack preferences, or potty habits is statistically unlikely — though, given the sample size of one, not impossible.
