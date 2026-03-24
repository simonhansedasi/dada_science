"""
Winter to Spring Transition: January through March
====================================================
Generates ~69 days of synthetic toddler behavior data (Jan 1 – Mar 10, 2026),
covering the winter-to-spring transition including a parenting behavior shift
(TV time replaced by books, starting Feb 16) and the DST "spring forward"
event (Mar 8, 2026).

Tracks nap latency (minutes to fall asleep), books read, TV minutes, outdoor
play, and available daylight. Uses STL decomposition and rolling averages to
reveal how the parenting shift and DST jointly affect nap latency trends.
All data is simulated/synthetic.
"""

import pandas as pd
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
from statsmodels.tsa.seasonal import STL


def generate_data(start="2026-01-01", end="2026-03-10"):

    dates = pd.date_range(start, end)

    parenting_shift = pd.Timestamp("2026-02-16")
    dst_shift = pd.Timestamp("2026-03-08")

    # Daylight increases linearly from 9h to 12h across the period
    daylight = np.linspace(9 * 60, 12 * 60, len(dates))

    outdoor = []
    nap_duration = []
    nap_latency = []
    books = []
    tv = []
    rain = []

    for d in dates:

        # Weather
        rainy = np.random.rand() < 0.65
        rain.append(rainy)

        if rainy:
            outdoor_play = np.random.normal(30, 4)
        else:
            outdoor_play = np.random.normal(45, 5)
        outdoor.append(max(outdoor_play, 0))

        # Nap duration stable throughout
        nap_duration.append(np.random.normal(125, 8))

        # Parenting shift: TV decreases, books increase from Feb 16 onward
        if d < parenting_shift:
            tv_minutes = np.random.normal(65, 8)
            books_read = np.random.poisson(2)
        else:
            days_since_shift = (d - parenting_shift).days
            tv_minutes = 35 - days_since_shift * 0.5 + np.random.normal(0, 3)
            books_read = 5 + int(days_since_shift * 0.1) + np.random.poisson(1)

        tv.append(max(tv_minutes, 0))
        books.append(books_read)

        # Nap latency spikes after DST (spring forward)
        if d < dst_shift:
            latency = 10 + np.random.normal(0, 0.7)
        else:
            days_since_dst = (d - dst_shift).days
            latency = 18 + days_since_dst * 0.25 + np.random.normal(0, 0.4)
        nap_latency.append(latency)

    df = pd.DataFrame({
        "date": dates,
        "daylight_min": daylight,
        "outdoor_play_min": outdoor,
        "nap_duration_min": nap_duration,
        "nap_latency_min": nap_latency,
        "books_read": books,
        "tv_minutes": tv,
        "rain": rain
    })

    # DST: clock springs forward, so daylight effectively jumps +60 min
    df.loc[df["date"] >= dst_shift, "daylight_min"] += 60

    return df


np.random.seed(4364564)
df = generate_data()

# Normalize variables for comparison plotting
normalized = df.copy()
cols = [
    "daylight_min",
    "outdoor_play_min",
    "nap_latency_min",
    "books_read",
    "tv_minutes"
]
for c in cols:
    normalized[c + "_norm"] = (df[c] - df[c].min()) / (df[c].max() - df[c].min())

# STL decomposition on outdoor play
res_outdoor = STL(normalized["outdoor_play_min_norm"], period=7).fit()

# Rolling 7-day averages for smoother trend lines
latency_trend = normalized["nap_latency_min_norm"].rolling(7).mean()
books_trend = normalized["books_read_norm"].rolling(7).mean()
tv_trend = normalized["tv_minutes_norm"].rolling(7).mean()

# --- Plot 1: Primary trend chart (rolling averages + STL outdoor) ---
plt.figure(figsize=(8, 5))

plt.plot(df["date"], latency_trend, label="Nap Latency", linewidth=4)
plt.plot(df["date"], books_trend, label="Books Read", linewidth=4)
plt.plot(df["date"], tv_trend, label="TV Minutes", linewidth=4)
plt.plot(df["date"], res_outdoor.trend, label="Outdoor Play")
plt.plot(df["date"], normalized["daylight_min_norm"], label="Daylight", linestyle="--")

plt.axvline(pd.Timestamp("2026-02-16"), color="red", linestyle=":",
            label="Parenting Shift")
plt.axvline(pd.Timestamp("2026-03-08"), color="black", linestyle="--",
            label="DST")

months = pd.date_range(df.date.min(), df.date.max(), freq="MS")
plt.xticks(months, [d.strftime("%b %Y") for d in months], rotation=45)

plt.title("Normalized Daily Behavior")
plt.xlabel("Date")
plt.ylabel("Normalized Value")
plt.legend()
plt.tight_layout()
plt.savefig('DST_spring.png')
plt.show()

# --- Plot 2: STL-decomposed trend comparison ---
res_latency = STL(normalized["nap_latency_min_norm"], period=7).fit()
res_books = STL(normalized["books_read_norm"], period=7).fit()
res_tv = STL(normalized["tv_minutes_norm"], period=7).fit()
daylight = normalized["daylight_min_norm"]

plt.figure(figsize=(12, 7))

plt.plot(df["date"], res_latency.trend, label="Nap Latency", linewidth=4)
plt.plot(df["date"], res_books.trend, label="Books Read")
plt.plot(df["date"], res_tv.trend, label="TV Minutes")
plt.plot(df["date"], res_outdoor.trend, label="Outdoor Play")
plt.plot(df["date"], daylight, label="Daylight", linestyle="--")

plt.axvline(
    pd.Timestamp("2026-02-16"),
    linestyle=":", color="red", alpha=0.7,
    label="Parenting Shift (Books > TV)"
)
plt.axvline(
    pd.Timestamp("2026-03-08"),
    linestyle="--", color="black", alpha=0.6,
    label="DST Start"
)

months = pd.date_range(df.date.min(), df.date.max(), freq="MS")
plt.xticks(months, [d.strftime("%b %Y") for d in months], rotation=45)

plt.title("Toddler Behavior Trends: Winter -> Spring Transition")
plt.xlabel("Date")
plt.ylabel("Normalized Value")
plt.legend()
plt.tight_layout()
plt.show()
