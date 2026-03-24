"""
Nap Timeseries Analysis: July through November
===============================================
Generates 141 days of synthetic toddler activity data (Jul 1 – Nov 18, 2025),
covering daylight hours, outdoor/indoor play, nap duration, meltdown counts,
and interaction requests.

Uses STL (Seasonal-Trend decomposition using LOESS) with period=7 to extract
weekly cycles and long-run trends. Highlights the effect of the November
Daylight Saving Time end on sleep and activity patterns.
All data is simulated/synthetic.
"""

import pandas as pd
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
from statsmodels.tsa.seasonal import STL


def generate_toddler_data(start_date="2025-07-01", end_date="2025-11-18"):

    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    np.random.seed(24353)

    # DST shift
    dst_shift = dt.datetime(2025, 11, 2)

    # Daylight: deterministic linear decrease from 15h (July) to 9.5h (Nov)
    dl_start = 15 * 60
    dl_end = 9.5 * 60
    daylight_min = np.linspace(dl_start, dl_end, len(dates))

    # Apply DST shift
    dst_index = np.where(dates == dst_shift)[0][0]
    daylight_min[dst_index:] -= 60

    outdoor_play = []
    indoor_play = []
    meltdowns = []
    interaction_reqs = []
    nap_duration = []
    wake_times = []
    bed_times = []
    field_trip = []
    field_location = []

    for i, d in enumerate(dates):

        dl_min = daylight_min[i]
        is_after_dst = d >= dst_shift

        # Outdoor play proportional to daylight
        base_outdoor = np.random.normal(dl_min * 1.75, 20)
        if is_after_dst:
            base_outdoor *= np.random.uniform(0.25, 0.75)
        base_outdoor = max(base_outdoor, 0)
        outdoor_play.append(base_outdoor)

        # Indoor play compensates
        indoor_base = np.random.normal(20, 10) + max(0, (600 - dl_min))
        if is_after_dst:
            indoor_base *= np.random.uniform(0.07, 1.25)
        indoor_play.append(indoor_base)

        # Nap duration declines into November
        nap_base = np.random.normal(130, 10)
        if d.month == 11:
            nap_base -= np.random.uniform(80, 10)
        if is_after_dst:
            nap_base -= np.random.uniform(15, 5)
        nap_duration.append(max(nap_base, 0))

        # Meltdowns increase as outdoor play declines
        meltdown_rate = 1 + max(0, (90 - base_outdoor) / 30)
        if is_after_dst:
            meltdown_rate *= np.random.uniform(1.2, 1.4)
        meltdowns.append(max(0, int(np.random.poisson(meltdown_rate))))

        # Interaction requests rise with indoor play
        interaction_rate = 5 + indoor_base / 25
        if is_after_dst:
            interaction_rate *= 1.15
        interaction_reqs.append(int(np.random.poisson(interaction_rate)))

        # Sleep schedule
        wake_shift = -20 if is_after_dst else 0
        bed_shift = -30 if is_after_dst else 0

        wake_times.append(
            (dt.datetime(2025, 1, 1, 7, 0) +
             dt.timedelta(minutes=np.random.normal(wake_shift, 20))).time()
        )
        bed_times.append(
            (dt.datetime(2025, 1, 1, 20, 0) +
             dt.timedelta(minutes=np.random.normal(bed_shift, 30))).time()
        )

        # Field trips
        trip = np.random.rand() < 3 / 7
        field_trip.append(trip)
        if trip:
            field_location.append(
                np.random.choice(["Museum", "Grocery", "Library", "Park", "Aquarium"])
            )
        else:
            field_location.append(None)

    df = pd.DataFrame({
        "date": dates,
        "daylight_min": daylight_min,
        "outdoor_play_min": outdoor_play,
        "indoor_play_min": indoor_play,
        "meltdown_count": meltdowns,
        "interaction_requests": interaction_reqs,
        "nap_duration_min": nap_duration,
        "wake_time": wake_times,
        "bed_time": bed_times,
        "field_trip": field_trip,
        "field_location": field_location,
    })

    return df


# Generate dataset
df = generate_toddler_data()

# Normalize variables
normalized = df.copy()
cols_to_norm = [
    "outdoor_play_min",
    "indoor_play_min",
    "meltdown_count",
    "interaction_requests",
    "nap_duration_min",
    "daylight_min",
]
for col in cols_to_norm:
    min_val = df[col].min()
    max_val = df[col].max()
    normalized[col + "_norm"] = (df[col] - min_val) / (max_val - min_val)

# STL decompositions
res_nap = STL(normalized["nap_duration_min_norm"], period=7).fit()
res_in = STL(normalized["indoor_play_min_norm"], period=7).fit()
res_out = STL(normalized["outdoor_play_min_norm"], period=7).fit()
res_melt = STL(normalized["meltdown_count_norm"], period=7).fit()
res_int = STL(normalized["interaction_requests_norm"], period=7).fit()
res_day = normalized["daylight_min_norm"]

# --- Plot individual STL decompositions ---
for res in [res_in, res_out, res_melt, res_int]:
    plt.figure(figsize=(10, 8))
    res.plot()
    plt.show()

# --- Plot: Normalized daily activity trends ---
plt.plot(normalized["date"], res_nap.trend, label="Nap Duration (m)", linewidth=5)
plt.plot(normalized["date"], res_out.trend, label="Outdoor Play Duration (m)")
plt.plot(normalized["date"], res_in.trend, label="Indoor Play Duration (m)")
plt.plot(normalized["date"], res_day, label="Available Daylight (m)")
plt.plot(normalized["date"], res_int.trend, label="Interaction Requests")

months = pd.date_range(normalized["date"].min(), df["date"].max(), freq="MS")
plt.xticks(months, [d.strftime("%b %Y") for d in months], rotation=45)

dst_date = pd.to_datetime("2025-11-02")
plt.axvline(dst_date, color="black", linestyle="--", label="Daylight Savings Ends", alpha=0.5)

plt.title("Normalized Daily Activity Trends")
plt.xlabel("Date")
plt.ylabel("Normalized Value")
plt.legend()
plt.tight_layout()
plt.savefig("trend_analysis.png")
plt.show()

# --- Plot: Nap STL decomposition ---
fig = res_nap.plot()
axes = fig.axes
axes[0].set_title("Observed Nap Duration")
axes[1].set_title("Trend in Nap Duration")
axes[2].set_title("Nap Duration Seasonality")
axes[3].set_title("Residuals")
plt.tight_layout()
plt.savefig("nap_decomp.png")
plt.show()
