import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, CheckButtons
import numpy as np

# --- CONFIGURATION ---
scale_factor = 13.7399
X_vals = [1.0, 1.5, 1.8, 2.0]  # STD bands for Basket
custom_constants = [1.3, 2.1, 2.4]  # STD multipliers for Croissants
colors = ['green', 'blue', 'brown', 'purple']
window_size = 100

# --- READ FILES ---
df_minus1 = pd.read_csv('prices_round_2_day_-1.csv', delimiter=';')
df_0 = pd.read_csv('prices_round_2_day_0.csv', delimiter=';')
df_1 = pd.read_csv('prices_round_2_day_1.csv', delimiter=';')

# --- CROISSANTS ---
c1 = df_minus1[df_minus1['product'] == 'CROISSANTS'].reset_index(drop=True)
c2 = df_0[df_0['product'] == 'CROISSANTS'].reset_index(drop=True)
c3 = df_1[df_1['product'] == 'CROISSANTS'].reset_index(drop=True)

offset_0 = c1['timestamp'].iloc[-1] + 100
offset_1 = offset_0 + len(c2) * 100
c2['timestamp'] += offset_0
c3['timestamp'] += offset_1

croissants = pd.concat([c1, c2, c3], ignore_index=True)
croissants['scaled_mid_price'] = croissants['mid_price'] * scale_factor
croissants['STD'] = croissants['scaled_mid_price'].std()

# Custom STD plots
croissants['plot1'] = croissants['scaled_mid_price'] + custom_constants[0] * croissants['STD']
croissants['plot2'] = croissants['scaled_mid_price'] + custom_constants[1] * croissants['STD']
croissants['plot3'] = croissants['scaled_mid_price'] + custom_constants[2] * croissants['STD']

# --- PICNIC_BASKET1 ---
b1 = df_minus1[df_minus1['product'] == 'PICNIC_BASKET1'].reset_index(drop=True)
b2 = df_0[df_0['product'] == 'PICNIC_BASKET1'].reset_index(drop=True)
b3 = df_1[df_1['product'] == 'PICNIC_BASKET1'].reset_index(drop=True)

offset_0_b = b1['timestamp'].iloc[-1] + 100
offset_1_b = offset_0_b + len(b2) * 100
b2['timestamp'] += offset_0_b
b3['timestamp'] += offset_1_b

basket = pd.concat([b1, b2, b3], ignore_index=True)
basket['scaled_mid_price'] = basket['mid_price']

basket_std = basket['scaled_mid_price'].std()
basket_mean = basket['scaled_mid_price'].mean()

# --- INITIAL PLOT RANGE ---
start = 0
max_start = len(basket) - window_size
end = start + window_size

# --- PLOT SETUP ---
fig, ax = plt.subplots()
plt.subplots_adjust(bottom=0.3, right=0.8)

# Plot croissant and basket
line_croissants, = ax.plot(croissants['timestamp'][start:end],
                           croissants['scaled_mid_price'][start:end],
                           label='Croissants Mid Price × 13.7399')

line_basket, = ax.plot(basket['timestamp'][start:end],
                       basket['scaled_mid_price'][start:end],
                       label='Basket Mid Price')

# Basket STD lines
std_lines = []
visibility = [True] * len(X_vals)

for i, X in enumerate(X_vals):
    threshold = basket_mean + X * basket_std
    line = ax.hlines(threshold,
                     xmin=basket['timestamp'][start],
                     xmax=basket['timestamp'][start + window_size - 1],
                     colors=colors[i], linestyles='--',
                     label=f'Basket Mean + {X}σ')
    std_lines.append(line)

# Croissant STD custom lines
plot_lines = []
plot_labels = [f'Croissants + {c}σ' for c in custom_constants]
plot_visibility = [True, True, True]

line_plot1, = ax.plot(croissants['timestamp'][start:end], croissants['plot1'][start:end],
                      label=plot_labels[0], linestyle='--', color='black')
line_plot2, = ax.plot(croissants['timestamp'][start:end], croissants['plot2'][start:end],
                      label=plot_labels[1], linestyle='--', color='gray')
line_plot3, = ax.plot(croissants['timestamp'][start:end], croissants['plot3'][start:end],
                      label=plot_labels[2], linestyle='--', color='darkred')
plot_lines.extend([line_plot1, line_plot2, line_plot3])

# --- CHART DETAILS ---
ax.set_title('Scrollable Mid Price Comparison')
ax.set_xlabel('Ticks')
ax.set_ylabel('Scaled Mid Price')
ax.grid(True)
ax.legend(loc='upper right')

# --- SLIDER ---
ax_slider = plt.axes([0.15, 0.15, 0.65, 0.03])
slider = Slider(ax_slider, 'Start Tick', 0, max_start, valinit=0, valstep=1)

def update(val):
    start = int(slider.val)
    end = start + window_size

    ts_c = croissants['timestamp'][start:end]
    ts_b = basket['timestamp'][start:end]
    mp_c = croissants['scaled_mid_price'][start:end]
    mp_b = basket['scaled_mid_price'][start:end]

    line_croissants.set_xdata(ts_c)
    line_croissants.set_ydata(mp_c)

    line_basket.set_xdata(ts_b)
    line_basket.set_ydata(mp_b)

    for i, X in enumerate(X_vals):
        y = basket_mean + X * basket_std
        std_lines[i].remove()
        std_lines[i] = ax.hlines(y,
                                 xmin=ts_b.iloc[0],
                                 xmax=ts_b.iloc[-1],
                                 colors=colors[i],
                                 linestyles='--')
        std_lines[i].set_visible(visibility[i])

    # Update croissant custom lines
    plot_lines[0].set_xdata(ts_c)
    plot_lines[0].set_ydata(croissants['plot1'][start:end])
    plot_lines[1].set_xdata(ts_c)
    plot_lines[1].set_ydata(croissants['plot2'][start:end])
    plot_lines[2].set_xdata(ts_c)
    plot_lines[2].set_ydata(croissants['plot3'][start:end])

    for i in range(3):
        plot_lines[i].set_visible(plot_visibility[i])

    ax.set_xlim(ts_b.iloc[0], ts_b.iloc[-1])
    ax.relim()
    ax.autoscale_view()
    fig.canvas.draw_idle()

slider.on_changed(update)

# --- CHECKBOXES ---

# Basket STD bands
ax_check = plt.axes([0.82, 0.55, 0.15, 0.15])
labels = [f'{X}σ Basket band' for X in X_vals]
checkbox = CheckButtons(ax_check, labels, visibility)

def toggle(label):
    i = labels.index(label)
    visibility[i] = not visibility[i]
    std_lines[i].set_visible(visibility[i])
    fig.canvas.draw_idle()

checkbox.on_clicked(toggle)

# Croissant custom bands
ax_check2 = plt.axes([0.82, 0.3, 0.15, 0.15])
checkbox2 = CheckButtons(ax_check2, plot_labels, plot_visibility)

def toggle_custom(label):
    i = plot_labels.index(label)
    plot_visibility[i] = not plot_visibility[i]
    plot_lines[i].set_visible(plot_visibility[i])
    fig.canvas.draw_idle()

checkbox2.on_clicked(toggle_custom)

plt.show()