import pandas as pd
import matplotlib.pyplot as plt

file_path = 'prices_round_2_day_1.csv'
product = 'CROISSANTS'

df = pd.read_csv(file_path, delimiter=';')

# Ensure volumes are numeric
cols = [
    'bid_volume_1','bid_volume_2','bid_volume_3',
    'ask_volume_1','ask_volume_2','ask_volume_3'
]
for c in cols:
    df[c] = pd.to_numeric(df[c], errors='coerce')

df = df[df['product']==product].fillna(0)

# Sum top-3 bid & ask volumes
df['total_bid_volume'] = df['bid_volume_1']+df['bid_volume_2']+df['bid_volume_3']
df['total_ask_volume'] = df['ask_volume_1']+df['ask_volume_2']+df['ask_volume_3']

# Calculate difference
df['volume_difference'] = df['total_bid_volume'] - df['total_ask_volume']

# 1) Group so each timestamp has exactly one volume_difference (use mean, sum, etc.)
agg_df = df.groupby('timestamp', as_index=False)['volume_difference'].mean()

# Sort by timestamp (important for a proper line plot)
agg_df = agg_df.sort_values('timestamp')

plt.figure(figsize=(12,6))
plt.plot(agg_df['timestamp'], agg_df['volume_difference'], color='blue', marker='o', linestyle='-')
plt.title(f'{product}: (Bid Vol - Ask Vol) Over Time')
plt.xlabel('Timestamp')
plt.ylabel('Volume Difference')
plt.grid(True)
plt.tight_layout()
plt.show()