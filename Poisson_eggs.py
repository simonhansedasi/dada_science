"""
Poisson Eggs: Easter Egg Hunt Analysis
=======================================
Records Easter egg finds across five egg colors (red, yellow, green, purple, pink)
and two shape types (circle, square) for both a random process baseline and a
toddler's actual retrieval pattern.

Applies chi-square tests, entropy analysis, KL divergence, sparsity metrics,
and Poisson distribution fits to show that the toddler is significantly more
selective (and less random) than chance would predict.
All data is simulated/synthetic.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import seaborn as sns
from scipy.stats import chi2_contingency, entropy, poisson

# --- Easter egg find data ---
eggs = {}

eggs["green_random"] = pd.DataFrame(
    [[0, 0, 0, 1, 0],
     [0, 0, 0, 0, 0]],
    columns=["red", "yellow", "green", 'purple', 'pink'],
    index=["circle", "square"]
)
eggs["purple_random"] = pd.DataFrame(
    [[1, 2, 1, 0, 0],
     [0, 0, 2, 0, 0]],
    columns=["red", "yellow", "green", 'purple', 'pink'],
    index=["circle", "square"]
)
eggs["pink_random"] = pd.DataFrame(
    [[0, 1, 0, 0, 1],
     [1, 1, 0, 0, 2]],
    columns=["red", "yellow", "green", 'purple', 'pink'],
    index=["circle", "square"]
)
eggs["red_random"] = pd.DataFrame(
    [[1, 1, 0, 0, 1],
     [1, 0, 1, 0, 0]],
    columns=["red", "yellow", "green", 'purple', 'pink'],
    index=["circle", "square"]
)
eggs["yellow_random"] = pd.DataFrame(
    [[1, 0, 1, 0, 0],
     [0, 2, 0, 0, 1]],
    columns=["red", "yellow", "green", 'purple', 'pink'],
    index=["circle", "square"]
)
eggs["green_toddler"] = pd.DataFrame(
    [[0, 0, 0, 0, 0],
     [1, 0, 0, 1, 0]],
    columns=["red", "yellow", "green", 'purple', 'pink'],
    index=["circle", "square"]
)
eggs["purple_toddler"] = pd.DataFrame(
    [[2, 0, 0, 0, 0],
     [0, 0, 0, 0, 0]],
    columns=["red", "yellow", "green", 'purple', 'pink'],
    index=["circle", "square"]
)
eggs["pink_toddler"] = pd.DataFrame(
    [[0, 0, 0, 0, 0],
     [0, 0, 1, 0, 0]],
    columns=["red", "yellow", "green", 'purple', 'pink'],
    index=["circle", "square"]
)
eggs["red_toddler"] = pd.DataFrame(
    [[0, 0, 0, 0, 0],
     [0, 1, 1, 0, 0]],
    columns=["red", "yellow", "green", 'purple', 'pink'],
    index=["circle", "square"]
)
eggs["yellow_toddler"] = pd.DataFrame(
    [[0, 0, 0, 0, 0],
     [0, 0, 0, 0, 0]],
    columns=["red", "yellow", "green", 'purple', 'pink'],
    index=["circle", "square"]
)

# --- Build long-format DataFrame ---
records = []
for egg_name, mat in eggs.items():
    source = "random" if "random" in egg_name else "toddler"
    for color in mat.index:
        for shape in mat.columns:
            count = mat.loc[color, shape]
            records.append({
                "egg": egg_name,
                "source": source,
                "color": color,
                "shape": shape,
                "count": count
            })

df = pd.DataFrame(records)

# --- Chi-square tests (with smoothing) ---
def chi_test(sub):
    table = sub.pivot_table(
        index="color", columns="shape",
        values="count", aggfunc="sum", fill_value=0
    )
    table = table + 1e-6  # Laplace smoothing
    chi2, p, _, _ = chi2_contingency(table)
    return p

print("Random p:", chi_test(df[df.source == "random"]))
print("Toddler p:", chi_test(df[df.source == "toddler"]))

# --- Entropy per egg ---
def matrix_entropy(mat):
    vals = mat.values.flatten()
    probs = vals / vals.sum() if vals.sum() > 0 else vals
    return entropy(probs)

entropy_results = {egg: matrix_entropy(mat) for egg, mat in eggs.items()}

# --- Aggregated heatmap: toddler finds ---
agg = df.groupby(["source", "color", "shape"])["count"].sum().reset_index()

plt.figure(figsize=(6, 5))
sns.heatmap(
    agg[agg.source == "toddler"].pivot("color", "shape", "count"),
    annot=True, cmap="coolwarm"
)
plt.title("Toddler Egg Finds by Color and Shape")
plt.show()

# --- Summary stats by source ---
egg_counts = df.groupby(["source", "egg"])["count"].sum().reset_index()
print(egg_counts.groupby("source")["count"].agg(["mean", "var"]))

# --- KL divergence: toddler vs random ---
def get_dist(sub):
    vals = sub.groupby(["color", "shape"])["count"].sum()
    probs = vals / vals.sum()
    return probs

epsilon = 1e-6
p_random = get_dist(df[df.source == "random"]) + epsilon
p_toddler = get_dist(df[df.source == "toddler"]) + epsilon
p_random = p_random / p_random.sum()
p_toddler = p_toddler.reindex(p_random.index, fill_value=0) + epsilon
p_toddler = p_toddler / p_toddler.sum()

kl = entropy(p_toddler, p_random)
print(f"KL divergence (toddler || random): {kl:.4f}")

# --- Sparsity analysis ---
df["is_zero"] = df["count"] == 0
sparsity_by_source = df.groupby("source")["is_zero"].mean()
print("Sparsity by source:")
print(sparsity_by_source)

support = df[df["count"] > 0].groupby("source").size()
total_possible = df.groupby(["color", "shape"]).ngroups
support_ratio = support / total_possible
print("Support ratio by source:")
print(support_ratio)

# --- Poisson fit plots ---
rand_counts = egg_counts[egg_counts.source == "random"]["count"]
tod_counts = egg_counts[egg_counts.source == "toddler"]["count"]

def plot_poisson_fit(counts, title):
    lam = counts.mean()
    x = np.arange(0, counts.max() + 2)
    plt.figure()
    plt.hist(counts, bins=x, alpha=0.7, label="Observed")
    expected = poisson.pmf(x, lam) * len(counts)
    plt.plot(x, expected, 'o-', label="Poisson fit")
    plt.title(f"{title}\nlambda={lam:.2f}")
    plt.xlabel("Count per egg")
    plt.ylabel("Frequency")
    plt.legend()
    plt.show()

plot_poisson_fit(rand_counts, "Random Process")
plot_poisson_fit(tod_counts, "Toddler Process")

# --- Side-by-side heatmaps: random vs toddler ---
def get_matrix(source):
    sub = df[df.source == source]
    return sub.pivot_table(
        index="color", columns="shape", values="count",
        aggfunc="sum", fill_value=0
    )

mat_random = get_matrix("random")
mat_toddler = get_matrix("toddler")

colors = sorted(set(mat_random.index).union(mat_toddler.index))
shapes = sorted(set(mat_random.columns).union(mat_toddler.columns))
mat_random = mat_random.reindex(index=colors, columns=shapes, fill_value=0)
mat_toddler = mat_toddler.reindex(index=colors, columns=shapes, fill_value=0)

fig, axes = plt.subplots(2, 1, figsize=(10, 6))
plt.subplots_adjust(right=0.85)

im1 = axes[0].imshow(mat_random.values, cmap='coolwarm')
im2 = axes[1].imshow(mat_toddler.values, cmap='coolwarm')

for ax, mat, title in zip(
    axes,
    [mat_random, mat_toddler],
    ["Random Distribution", "Toddler Distribution"]
):
    ax.set_title(title, fontsize=14)
    ax.set_xticks(range(len(shapes)))
    ax.set_yticks(range(len(colors)))
    ax.set_xticklabels(shapes, fontsize=14, rotation=20)
    ax.set_yticklabels(colors, fontsize=14)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, mat.values[i, j], ha="center", va="center")

cbar_ax = fig.add_axes([0.88, 0.15, 0.03, 0.7])
norm = mpl.colors.Normalize(vmin=0, vmax=1)
sm = mpl.cm.ScalarMappable(cmap=im1.cmap, norm=norm)
sm.set_array([])
cbar = fig.colorbar(sm, cax=cbar_ax)
cbar.set_label("Relative Intensity (Low -> High)", fontsize=16)
cbar.set_ticks([0, 1])
cbar.set_ticklabels(["Low", "High"])
cbar.ax.tick_params(labelsize=14)

plt.tight_layout()
plt.savefig('poisson_eggs.png')
plt.show()

# --- Support size bar chart ---
used = df[df["count"] > 0].groupby("source").size()
total = df.groupby(["color", "shape"]).ngroups
support_ratio = used / total

plt.figure()
plt.bar(support_ratio.index, support_ratio.values)
plt.title("Support Size (Used Combinations)")
plt.ylabel("Proportion of Possible Combos")
plt.show()
