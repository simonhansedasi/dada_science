"""
Potty Training Analytics
========================
Simulates one week of potty training events for a toddler (Mon–Fri).
Tracks Time Until Potty (TuP in seconds), location (Upstairs/Downstairs),
book reading behavior, and incentive type (Cocopuff, Yoggie, M&M).

Produces scatter and boxplot visualizations exploring how location and
book reading affect TuP, and how incentives are distributed by location.
All data is simulated/synthetic.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

np.random.seed(91284783)

days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
incentives = ['Cocopuff', 'Yoggie', 'M&M']
data = []

for n, day in enumerate(days):
    # Determine number of pee and poop events
    if day == 'Mon':
        num_pee = int(np.floor(np.random.normal(16, 2)))
        num_poo = 0
    elif day == 'Tue':
        num_pee = int(np.floor(np.random.normal(12, 3)))
        num_poo = 0
    else:
        num_pee = int(np.floor(np.random.normal(8, 2)))
        num_poo = 1

    # Split pee into morning and afternoon
    morn_pee = int(np.floor((num_pee / 2) + (num_pee % 2)))
    aft_pee = int(np.floor(num_pee / 2))

    # Function for probabilistic incentive selection per day
    def choose_incentive(day):
        rand_vals = np.random.rand(len(incentives))
        if day in ['Mon', 'Tue']:
            rand_vals[0] += 0.6
        elif day == 'Wed':
            rand_vals[1] += 0.6
        else:  # Thu, Fri
            rand_vals[2] += 0.6
        prob_vector = rand_vals / rand_vals.sum()
        return incentives[np.argmax(prob_vector)]

    # Generate pee events
    for i in range(morn_pee + aft_pee):
        # ToD split morning/afternoon
        tod = np.random.randint(7, 12) + np.random.randint(0, 60) / 60 if i < morn_pee else np.random.randint(12, 21) + np.random.randint(0, 60) / 60
        tup = max(5, int(np.random.normal(35, 40)))
        outcome = '#1'
        # Randomized location per event
        if day == 'Mon':
            loc = 'Upstairs'
        else:
            loc = np.random.choice(['Upstairs', 'Downstairs'], p=[0.65, 0.35])

        # Adjust TuP for downstairs
        if loc == 'Downstairs':
            tup += np.random.randint(46, 90)  # slightly longer

        # Probabilistic book reading based on time and location noise
        base_prob = 0.05 + max(0, (tup - 40) / 5) * 0.02
        if loc == 'Downstairs':
            base_prob += 0.1  # more likely to read books downstairs
        base_prob = min(base_prob, 0.95)
        book = np.random.choice(['Y', 'N'], p=[base_prob, 1 - base_prob])

        # If book is read, slightly increase TuP
        if book == 'Y':
            tup += np.random.randint(60, 120)

        incentive = choose_incentive(day)

        data.append({'day': day, 'ToD': tod, 'TuP': tup, 'outcome': outcome,
                     'location': loc, 'book': book, 'incentive': incentive})

    # Generate poop events (only 10am - 12pm)
    for i in range(num_poo):
        tod = np.random.randint(10, 12) + np.random.randint(0, 60) / 60  # restricted to 10-12
        tup = max(10, int(np.random.normal(60, 10)))
        outcome = '#2'
        loc = np.random.choice(['Upstairs', 'Downstairs'], p=[0.55, 0.45])

        if loc == 'Downstairs':
            tup += np.random.randint(2, 6)

        prob_book = 0.5 + max(0, (tup - 60) / 5) * 0.02
        if loc == 'Downstairs':
            prob_book += 0.1
        prob_book = min(prob_book, 0.95)
        book = np.random.choice(['Y', 'N'], p=[prob_book, 1 - prob_book])

        if book == 'Y':
            tup += np.random.randint(1, 4)

        incentive = choose_incentive(day)
        data.append({'day': day, 'ToD': tod, 'TuP': tup, 'outcome': outcome,
                     'location': loc, 'book': book, 'incentive': incentive})

df = pd.DataFrame(data)

# Sort by day and time of day
day_order = {'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4}
df['day_num'] = df['day'].map(day_order)
df = df.sort_values(by=['day_num', 'ToD']).drop(columns='day_num').reset_index(drop=True)

# --- Plot 1: TuP vs Time of Day scatter colored by location ---
colors = df['location'].map({'Upstairs': 'blue', 'Downstairs': 'red'})
plt.figure(figsize=(12, 8))
plt.scatter(df['ToD'], df['TuP'], c=colors, s=80)
plt.xlabel('Time of Day (hour)', fontsize=16)
plt.xticks(fontsize=16)
plt.ylabel('Time Until Potty (seconds)', fontsize=16)
plt.yticks(fontsize=16)
plt.title('Time Until Potty vs Time of Day by Location', fontsize=20)
legend_elements = [Patch(facecolor='blue', label='Upstairs'),
                   Patch(facecolor='red', label='Downstairs')]
plt.legend(handles=legend_elements, title='Location', fontsize=16, title_fontsize=20)
plt.savefig('tup_tod.png')
plt.show()

# --- Plot 2: Boxplots by location and book reading ---
groups = [
    df[(df['location'] == 'Upstairs') & (df['book'] == 'Y')]['TuP'],
    df[(df['location'] == 'Upstairs') & (df['book'] == 'N')]['TuP'],
    df[(df['location'] == 'Downstairs') & (df['book'] == 'Y')]['TuP'],
    df[(df['location'] == 'Downstairs') & (df['book'] == 'N')]['TuP']
]
labels = ['Upstairs + Book', 'Upstairs + No Book',
          'Downstairs + Book', 'Downstairs + No Book']

plt.figure(figsize=(12, 9))
plt.ylabel('TuP (seconds)', fontsize=16)
plt.xticks(fontsize=16)
plt.yticks(fontsize=16)
plt.boxplot(groups, labels=labels)
plt.ylabel('Time Until Potty (seconds)')
plt.title('Time until Potty by Location and Book Reading', fontsize=20)
plt.xticks(rotation=20)
plt.savefig('tup_book.png')
plt.show()

# --- Plot 3: Incentive distribution by location ---
counts = df.groupby(['location', 'incentive']).size().unstack(fill_value=0)
counts.plot(kind='bar', figsize=(10, 6))
plt.ylabel('Number of Potties', fontsize=16)
plt.yticks(fontsize=16)
plt.title('Incentive Distribution by Location', fontsize=20)
plt.xlabel('Location', fontsize=16)
plt.xticks(fontsize=16, rotation=0)
plt.legend(title='Incentive', title_fontsize=20, fontsize=16)
plt.savefig('tup_inc.png')
plt.show()
