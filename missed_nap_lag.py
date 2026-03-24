"""
Missed Nap Lag Analysis: May through September
===============================================
Generates 130 days of synthetic toddler sleep data (May 15 – Sep 22, 2025).
Models the lagged relationship between missed daytime naps and overnight
sleep quality, using STL decomposition to isolate disruption signals from
the baseline weekly sleep cycle.

Highlights "Berry Season" (Jul–Aug) as a period of zero missed naps, and
uses ACF/PACF and ARIMA with exogenous inputs to model residual disruptions.
All data is simulated/synthetic.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.tsa.seasonal import STL
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.stats.diagnostic import acorr_ljungbox

np.random.seed(91827365)

days = 130
base_nap = 2       # hours
base_night_sleep = 10.0  # hours

df = pd.DataFrame({
    "day": pd.date_range("2025-05-15", periods=days)
})

# Default probability: 10% missed nap
df["miss_prob"] = 0.10

# Override probabilities during berry season (zero missed naps)
berry_mask = (df["day"] >= "2025-07-01") & (df["day"] <= "2025-08-31")
df.loc[berry_mask, "miss_prob"] = 0.00

# Generate nap durations (in minutes)
df["nap_duration"] = df.apply(
    lambda row: base_nap if np.random.rand() > row["miss_prob"] else 0,
    axis=1
)
df['nap_duration'] = df['nap_duration'] * np.random.normal(1, 0.05, size=days) * 60

# Generate overnight sleep with rebound effect
df['overnight_sleep'] = base_night_sleep * np.random.normal(1, 0.01, size=days)
for i in range(days):
    if df.loc[i, 'nap_duration'] < 1:  # missed nap — rebound in overnight sleep
        rebound = np.random.uniform(0.5, 1.0)
        df.loc[i, 'overnight_sleep'] += rebound
df['overnight_sleep'] = df['overnight_sleep'] * 60

# STL residual = overnight_sleep - expected baseline
df['sleep_residual'] = df['overnight_sleep'] - base_night_sleep

# Normalize columns
cols = ['nap_duration', 'overnight_sleep']
for col in cols:
    df[col + '_norm'] = (df[col] - df[col].min()) / (df[col].max() - df[col].min())

df['nap_norm'] = df['nap_duration_norm']
df['sleep_norm'] = df['overnight_sleep_norm']

# Identify missed nap days
missed = df[df['nap_duration'] < 0.05]

# --- Plot 1: Nap vs overnight sleep (raw normalized series) ---
plt.figure(figsize=(12, 5))
plt.plot(df['day'], df['nap_norm'], label='Nap Duration (0-1)', marker='o')
plt.plot(df['day'], df['sleep_norm'], label='Overnight Sleep (0-1)')
plt.title("Raw Time Series: Nap vs Overnight Sleep")
plt.xlabel("Day")
plt.ylabel("Normalized Value (0-1)")
plt.grid(True)
plt.legend()
plt.show()

# --- STL decomposition of overnight sleep ---
stl = STL(df['sleep_norm'], period=7, robust=True).fit()
df['sleep_trend'] = stl.trend
df['sleep_seasonal'] = stl.seasonal
df['sleep_resid'] = stl.resid

# --- Plot 2: STL decomposition subplots ---
fig, ax = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

ax[0].plot(df['day'], df['nap_norm'])
ax[0].set_title("Nap Duration (0-1)", fontsize=18)
ax[0].set_ylabel("Nap", fontsize=16)
ax[0].tick_params(axis='both', labelsize=14)

ax[1].plot(df['day'], df['sleep_norm'])
ax[1].set_title("Overnight Sleep (0-1)", fontsize=18)
ax[1].set_ylabel("Sleep", fontsize=16)
ax[1].tick_params(axis='both', labelsize=14)

ax[2].plot(df['day'], df['sleep_resid'])
ax[2].set_title("STL Remainder (Disruptions)", fontsize=18)
ax[2].set_ylabel("Residuals", fontsize=16)
ax[2].tick_params(axis='both', labelsize=14)

# Mark missed nap days with red vertical lines
for d in missed['day']:
    for i in range(3):
        ax[i].axvline(d, color='red', linestyle='--', alpha=0.8)

plt.tight_layout()
plt.savefig("missed_nap_stl.png", dpi=300)
plt.xticks(fontsize=18, rotation=45)
plt.show()

# --- Lag-1 scatter: yesterday's nap vs tonight's sleep disruption ---
df['lag_nap'] = df['nap_norm'].shift(1)
plt.figure(figsize=(6, 5))
plt.scatter(df['lag_nap'], df['sleep_resid'])
plt.title("Lag-1: Yesterday's Nap vs Tonight's Sleep Disruption")
plt.xlabel("Lagged Nap (0-1)")
plt.ylabel("Remainder (Disruption)")
plt.grid(True)
plt.show()
print(df[['lag_nap', 'sleep_resid']].corr())

# --- ACF / PACF of residuals ---
plot_acf(df['sleep_resid'], lags=20)
plt.title("ACF of Residuals")
plt.show()

plot_pacf(df['sleep_resid'], lags=20)
plt.show()

# --- ARIMA(1,0,1) on residuals ---
stl2 = STL(df['sleep_norm'], period=7).fit()
df['residual'] = stl2.resid

model_base = ARIMA(df['residual'], order=(1, 0, 1))
result_base = model_base.fit()
print(result_base.summary())

# Ljung-Box test
print(acorr_ljungbox(result_base.resid, lags=[10], return_df=True))

# ARIMAX with missed nap as exogenous variable
df['missed_nap'] = (df['nap_duration'] < 0.05).astype(int)
model_exog = ARIMA(df['residual'], order=(1, 0, 1), exog=df['missed_nap'])
result_exog = model_exog.fit()
print(result_exog.summary())

# --- Plot 3: Berry Season highlight ---
plt.figure(figsize=(12, 5))
plt.plot(df['day'], df['nap_norm'], label='Nap (0-1)', marker='o')
plt.axvspan('2025-07-01', '2025-08-31', color='purple', alpha=0.1, label='Berry Season')
plt.scatter(missed['day'], [0] * len(missed), color='red', label='Missed Naps', zorder=5)
plt.title("Nap Stability During Berry Season (Coincidence?)")
plt.xlabel("Day")
plt.ylabel("Normalized Nap")
plt.legend()
plt.grid(True)
plt.show()

# --- Plot 4: Full annotated time series ---
plt.figure(figsize=(20, 10))
plt.plot(df['day'], df['nap_norm'], label='Nap (0-1)', marker='o')
plt.plot(df['day'], df['sleep_norm'], label='Sleep (0-1)')
plt.axvspan('2025-07-01', '2025-08-31', color='purple', alpha=0.1, label='Berry Season')

first = True
for d in missed['day']:
    if first:
        plt.axvline(d, color='red', linestyle='--', alpha=0.7, label='Missed Nap')
        first = False
    else:
        plt.axvline(d, color='red', linestyle='--', alpha=0.7)

plt.title("Normalized Toddler Nap and Sleep Durations", fontsize=20)
plt.xlabel("Day", fontsize=16)
plt.ylabel("Normalized Value", fontsize=16)
plt.grid(True)
plt.xticks(size=16, rotation=45)
plt.yticks(size=16)
plt.legend(fontsize=16)
plt.savefig('missed_naps.png')
plt.show()
