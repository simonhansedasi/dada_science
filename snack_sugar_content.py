"""
Snack Sugar Content and Tantrum Duration
=========================================
Generates 1,000 synthetic snack records for a toddler, modeling the
relationship between snack type (Goldfish / Apple / Carrots), time of day
(Morning / Afternoon / Evening), and tantrum duration in seconds.

Key finding: two-way ANOVA shows time of day accounts for ~76.9% of variance
in tantrum duration (eta-squared), dwarfing the effect of sugar content alone.
Tukey HSD post-hoc tests identify which snack-time combinations differ.
All data is simulated/synthetic.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import statsmodels.api as sm
from statsmodels.formula.api import ols
from statsmodels.stats.multicomp import pairwise_tukeyhsd


def generate_tantrum_data_stochastic(n=1000, seed=4353):
    np.random.seed(seed)

    # Snacks and sugar content
    snack = np.random.choice(['Goldfish', 'Apple', 'Carrots'], size=n)
    sugar = np.where(snack == 'Goldfish', 10, np.where(snack == 'Apple', 5, 2))

    # Time of day
    time_of_day = np.random.choice(['Morning', 'Afternoon', 'Evening'], size=n)

    # Base probability of tantrum by time of day
    p_base = {'Morning': 0.09, 'Afternoon': 0.25, 'Evening': 0.7}
    p_tant = np.array([p_base[t] for t in time_of_day])

    # Sugar amplifies probability in afternoon and evening
    sugar_effect_prob = (np.where(time_of_day == 'Afternoon', sugar * 0.15, 0) +
                         np.where(time_of_day == 'Evening', sugar * 0.3, 0))

    # Stochastic noise
    prob_noise = np.random.normal(0, 0.05, n)
    p_tant = np.clip(p_tant + sugar_effect_prob + prob_noise, 0, 1)

    # Sample tantrum occurrence
    tantrum_occurs = np.random.binomial(1, p_tant, n)

    # Duration if tantrum occurs
    base_duration = 5
    duration_effect = sugar_effect_prob * 2
    alpha = 2  # scaling factor for probability effect on duration
    uncontrollable_noise = np.random.normal(0, 0.5, n)
    t_tant = tantrum_occurs * np.clip(
        base_duration + duration_effect + alpha * p_tant + uncontrollable_noise, 0, None
    )

    df = pd.DataFrame({
        'snack_type': snack,
        'sugar_content': sugar,
        'time_of_day': time_of_day,
        'p_tant': p_tant,
        't_tant': t_tant
    })
    return df


df = generate_tantrum_data_stochastic()

# Split by snack type
apple = df[df['snack_type'] == 'Apple'].copy()
fish = df[df['snack_type'] == 'Goldfish'].copy()
carrots = df[df['snack_type'] == 'Carrots'].copy()

# --- Plot 1: Tantrum duration histogram by sugar content ---
plt.figure(figsize=(10, 8))
plt.hist(fish['t_tant'], alpha=0.5, label='High - Goldfish')
plt.hist(apple['t_tant'], alpha=0.5, label='Medium - Apple')
plt.hist(carrots['t_tant'], alpha=0.5, label='Low - Carrot')
plt.xlabel('Tantrum Duration (s)', fontsize=18)
plt.xticks(size=16)
plt.ylabel('Frequency', fontsize=18)
plt.yticks(size=16)
plt.title('Tantrum Duration Histogram\nVaried by Sugar Content', fontsize=20)
legend = plt.legend(title='Sugar Content', fontsize=15)
legend.get_title().set_fontsize(15)
plt.savefig('sugar_hist.png')
plt.show()

# Hmm... appears to be higher dimensionality than just sugar content

# --- Two-way ANOVA: snack type * time of day ---
model = ols('t_tant ~ C(snack_type) * C(time_of_day)', data=df).fit()
df_anova = sm.stats.anova_lm(model, typ=2)
print(df_anova)

# --- Tukey HSD post-hoc ---
tukey = pairwise_tukeyhsd(
    endog=df['t_tant'],
    groups=df['snack_type'] + "_" + df['time_of_day'],
    alpha=0.05
)
print(tukey.summary())

# --- Tukey HSD heatmap (no-difference pairs) ---
group_names = tukey.groupsunique
n_groups = len(group_names)
diff_matrix = np.zeros((n_groups, n_groups))
i_indices, j_indices = tukey._multicomp.pairindices
for idx in range(len(i_indices)):
    i = i_indices[idx]
    j = j_indices[idx]
    pval = tukey.pvalues[idx]
    diff_matrix[i, j] = 0 if pval < 0.05 else 1  # 1 = no difference
    diff_matrix[j, i] = diff_matrix[i, j]

diff_df = pd.DataFrame(diff_matrix, index=group_names, columns=group_names)
plt.figure(figsize=(6, 5))
sns.heatmap(diff_df, annot=True, cmap='Greens', cbar=False, linewidths=0.5)
plt.title('No-Difference Tukey HSD Heatmap\n0 = No Significant Difference')
plt.show()

# --- Pairs with no significant difference ---
no_diff_pairs = []
for idx in range(len(i_indices)):
    i = i_indices[idx]
    j = j_indices[idx]
    pval = tukey.pvalues[idx]
    if pval > 0.05:
        pair = f"{group_names[i]} <-> {group_names[j]}"
        no_diff_pairs.append(pair)

print("Pairs with NO significant difference:")
for pair in no_diff_pairs:
    print("*", pair)

# --- Plot 2: Interaction plot (time of day x snack type) ---
plt.figure(figsize=(10, 8))
sns.pointplot(
    data=df, x='time_of_day', y='t_tant', hue='snack_type',
    hue_order=['Goldfish', 'Apple', 'Carrots'],
    order=['Morning', 'Afternoon', 'Evening'],
    dodge=True, markers='o', capsize=0.1, errwidth=1.5
)
plt.title("Tantrum Duration Factor Interactions\nTime of Snack & Snack Type", fontsize=20)
plt.ylabel('Tantrum Duration (s)', fontsize=18)
plt.xticks(size=16)
plt.xlabel('Time of Day', fontsize=18)
plt.yticks(size=16)
legend = plt.legend(title='Snack Type', fontsize=15)
legend.get_title().set_fontsize(15)
plt.savefig('effect_chart.png')
plt.show()

# --- Effect sizes (eta-squared) ---
ss_total = df_anova['sum_sq'].sum()
df_anova['eta_sq'] = df_anova['sum_sq'] / ss_total
print(df_anova[['sum_sq', 'eta_sq']])
