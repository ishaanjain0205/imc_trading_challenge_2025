import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, CheckButtons
import numpy as np

# VWAP Visualizer

# USER TODO: CHANGE PRODUCT NAME
product = 'CROISSANTS'

# USER TODO: CHANGE CSV FILE NAMES
df_minus1 = pd.read_csv('prices_round_2_day_-1.csv', delimiter=';')
df_0 = pd.read_csv('prices_round_2_day_0.csv', delimiter=';')
df_1 = pd.read_csv('prices_round_2_day_1.csv', delimiter=';')

# filter for product wanted
df_neg1 = df_minus1[df_minus1['product'] == product].reset_index(drop=True)
df_0 = df_0[df_0['product'] == product].reset_index(drop=True)
df_1 = df_1[df_1['product'] == product].reset_index(drop=True)

# calculate offsets for stitching
last_timestamp = df_neg1['timestamp'].iloc[-1]
offset_0 = last_timestamp + 100
offset_1 = offset_0 + len(df_0) * 100

# offset timestamps so stichable
df_0['timestamp'] += offset_0
df_1['timestamp'] += offset_1

# combine
productDf = pd.concat([df_neg1, df_0, df_1], ignore_index=True)

# df of mid price
productDf = productDf.reset_index(drop=True).fillna(0)
productDf['spread'] = productDf['bid_price_1'] - productDf['ask_price_1']

time = productDf['timestamp']
mid_price = productDf['mid_price']

# df of VWAP at each price 
# numerator = sum(bid / ask price * bid / ask volume)
numeratorVWAP = productDf['bid_price_1'] * productDf['bid_volume_1'] + productDf['ask_price_1'] * productDf['ask_volume_1']
numeratorVWAP += productDf['bid_price_2'] * productDf['bid_volume_2'] + productDf['ask_price_2'] * productDf['ask_volume_2']
numeratorVWAP += productDf['bid_price_3'] * productDf['bid_volume_3'] + productDf['ask_price_3'] * productDf['ask_volume_3']

# denominator = sum(bid + ask volumes)
denominatorVWAP = productDf['bid_volume_1'] + productDf['ask_volume_1'] 
denominatorVWAP += productDf['bid_volume_2'] + productDf['ask_volume_2']
denominatorVWAP += productDf['bid_volume_3'] + productDf['ask_volume_3']

productDf['vwap'] = numeratorVWAP / denominatorVWAP
vwap = productDf['vwap']

# calculate STD of mid price's variance from VWAP = mid_price - VWAP (how many dollars is mid price usually away from VWAP)
# based on this, we can set a threshold of when the variance is extreme and determine to buy or sell
productDf['vwap_spread'] = productDf['mid_price'] - productDf['vwap']
fixedSTD = productDf['vwap_spread'].std()
print(f'Fixed STD: {fixedSTD}')

# plot scrollable mid price and VWAP, zoomed

# USER TODO: CHANGE window size to zoom in or out
window_size = 10
max_start = len(productDf) - window_size

fig, ax = plt.subplots()
plt.subplots_adjust(bottom=0.3, right=0.8)

start = 0
end = start + window_size

# plot mid price
line_mid, = ax.plot(productDf['timestamp'][start:end], productDf['mid_price'][start:end], label='Mid Price')

# plot VWAP
line_vwap, = ax.plot(productDf['timestamp'][start:end], productDf['vwap'][start:end], label='VWAP', color='orange')

# plot VWAP +- X * STD (average variance betwewen mid price and VWAP), X is for multipler so we maximize setting orders at peaks and troughs
X_vals = [ 1.5, 1.6,1.8, 2.0]
colors = ['green', 'blue', 'brown','purple']
upper_lines = []
lower_lines = []
shaded_zones = []
band_visibility = [True] * len(X_vals)  # NEW: checkbox state tracking

for i, X in enumerate(X_vals):
    upper = productDf['vwap'][start:end] + X * fixedSTD
    lower = productDf['vwap'][start:end] - X * fixedSTD

    # upper/lower bands
    upper_line, = ax.plot(productDf['timestamp'][start:end], upper, label=f'Upper Bound ({X}σ)', color=colors[i], linestyle='--')
    lower_line, = ax.plot(productDf['timestamp'][start:end], lower, label=f'Lower Bound ({X}σ)', color=colors[i], linestyle='--')
    upper_lines.append(upper_line)
    lower_lines.append(lower_line)

    # signal zone (shade where mid_price > upper or < lower)
    mp = productDf['mid_price'][start:end]
    ts = productDf['timestamp'][start:end]
    vw = productDf['vwap'][start:end]
    signal_mask = (mp > upper) | (mp < lower)

    fill = ax.fill_between(ts, mp, vw, where=signal_mask, interpolate=True,
                           color=colors[i], alpha=0.2, label=f'Signal Zones {X}σ')
    shaded_zones.append(fill)

ax.set_title('Mid Price vs VWAP (Scrollable)')
ax.set_xlabel('Ticks')
ax.set_ylabel('Price')
ax.grid(True)
ax.legend(loc='upper right')  # move legend to top right

# Slider
ax_slider = plt.axes([0.15, 0.15, 0.65, 0.03])
slider = Slider(ax_slider, 'Start Tick', 0, max_start, valinit=0, valstep=1)

# Update for slider
def update(val):
    start = int(slider.val)
    end = start + window_size

    ts = productDf['timestamp'][start:end]
    mp = productDf['mid_price'][start:end]
    vw = productDf['vwap'][start:end]

    line_mid.set_xdata(ts)
    line_mid.set_ydata(mp)
    line_vwap.set_xdata(ts)
    line_vwap.set_ydata(vw)

    for i, X in enumerate(X_vals):
        upper_vals = vw + X * fixedSTD
        lower_vals = vw - X * fixedSTD

        upper_lines[i].set_xdata(ts)
        upper_lines[i].set_ydata(upper_vals)
        lower_lines[i].set_xdata(ts)
        lower_lines[i].set_ydata(lower_vals)

        shaded_zones[i].remove()
        signal_mask = (mp > upper_vals) | (mp < lower_vals)

        if band_visibility[i]:
            shaded_zones[i] = ax.fill_between(ts, mp, vw, where=signal_mask,
                                              interpolate=True, color=colors[i], alpha=0.2)
        else:
            # invisible placeholder so indexing stays clean
            shaded_zones[i] = ax.fill_between(ts, mp, vw, where=[False]*len(ts),
                                              interpolate=True, color=colors[i], alpha=0.0)

    ax.set_xlim(ts.iloc[0], ts.iloc[-1])
    ax.relim()
    ax.autoscale_view()
    fig.canvas.draw_idle()

slider.on_changed(update)

# Checkboxes for showing/hiding band pairs
ax_check = plt.axes([0.82, 0.4, 0.15, 0.15])
check_labels = [f'{X}σ bands' for X in X_vals]
checks = CheckButtons(ax_check, check_labels, band_visibility)

def toggle(label):
    i = check_labels.index(label)
    band_visibility[i] = not band_visibility[i]

    upper_lines[i].set_visible(band_visibility[i])
    lower_lines[i].set_visible(band_visibility[i])
    shaded_zones[i].set_visible(band_visibility[i])
    fig.canvas.draw_idle()

checks.on_clicked(toggle)

plt.show()

# KELP:
# Fixed STD: 0.5468034905299181
# X = 1.8 as multiplier to capture most profits as per plot
# if mid price > vwap + 1.8 * fixedSTD, sell all 
# if mid price < vwap - 1.8 * fixedSTD, buy all