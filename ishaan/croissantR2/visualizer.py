import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, CheckButtons

# --- CONFIG ---
scale_factor = 13.7399
offset_constants = [0.3, 0.25, 0.2]  # controlled by checkbox
offset_colors = ['green', 'blue', 'purple']
window_size = 100

# --- READ DATA ---
df_minus1 = pd.read_csv('prices_round_2_day_-1.csv', delimiter=';')
df_0 = pd.read_csv('prices_round_2_day_0.csv', delimiter=';')
df_1 = pd.read_csv('prices_round_2_day_1.csv', delimiter=';')

# --- CROISSANTS ---
df_c1 = df_minus1[df_minus1['product'] == 'CROISSANTS'].reset_index(drop=True)
df_c2 = df_0[df_0['product'] == 'CROISSANTS'].reset_index(drop=True)
df_c3 = df_1[df_1['product'] == 'CROISSANTS'].reset_index(drop=True)

offset_0 = df_c1['timestamp'].iloc[-1] + 100
offset_1 = offset_0 + len(df_c2) * 100
df_c2['timestamp'] += offset_0
df_c3['timestamp'] += offset_1

productDf = pd.concat([df_c1, df_c2, df_c3], ignore_index=True)
productDf['new_mp'] = productDf['mid_price'] * scale_factor
productDf['std_price'] = productDf['new_mp'].std()

# --- CROISSANT OFFSET BANDS ---
for i, c in enumerate(offset_constants):
    productDf[f'plot_{i}'] = productDf['new_mp'] + c * productDf['std_price']

# --- PICNIC_BASKET1 ---
df_b1 = df_minus1[df_minus1['product'] == 'PICNIC_BASKET1'].reset_index(drop=True)
df_b2 = df_0[df_0['product'] == 'PICNIC_BASKET1'].reset_index(drop=True)
df_b3 = df_1[df_1['product'] == 'PICNIC_BASKET1'].reset_index(drop=True)

offset_0_b = df_b1['timestamp'].iloc[-1] + 100
offset_1_b = offset_0_b + len(df_b2) * 100
df_b2['timestamp'] += offset_0_b
df_b3['timestamp'] += offset_1_b

picknickBasket = pd.concat([df_b1, df_b2, df_b3], ignore_index=True)

# --- PLOT SETUP ---
start = 0
max_start = len(productDf) - window_size
end = start + window_size

fig, ax = plt.subplots()
plt.subplots_adjust(bottom=0.3, right=0.8)

# Line 1: Croissants scaled mid price
line_croissant, = ax.plot(productDf['timestamp'][start:end],
                          productDf['new_mp'][start:end],
                          label='Croissants Mid Price × 13.7399')

# Line 2: Picnic Basket 1 raw mid price
line_basket, = ax.plot(picknickBasket['timestamp'][start:end],
                       picknickBasket['mid_price'][start:end],
                       label='Picknick Basket 1 Mid Price')

# Lines 3-5: Offset bands from checkbox
offset_lines = []
offset_visibility = [True] * len(offset_constants)
offset_labels = [f'+ {c} * STD' for c in offset_constants]

for i, c in enumerate(offset_constants):
    line, = ax.plot(productDf['timestamp'][start:end],
                    productDf[f'plot_{i}'][start:end],
                    label=offset_labels[i],
                    linestyle='--',
                    color=offset_colors[i])
    offset_lines.append(line)

# --- AXES CONFIG ---
ax.set_title('Scrollable Croissant vs Basket + Custom STD Offsets')
ax.set_xlabel('Ticks')
ax.set_ylabel('Mid Price')
ax.grid(True)
ax.legend(loc='upper right')

# --- SLIDER ---
ax_slider = plt.axes([0.15, 0.15, 0.65, 0.03])
slider = Slider(ax_slider, 'Start Tick', 0, max_start, valinit=0, valstep=1)

def update(val):
    start = int(slider.val)
    end = start + window_size

    ts = productDf['timestamp'][start:end]
    ts_basket = picknickBasket['timestamp'][start:end]

    # Update base lines
    line_croissant.set_xdata(ts)
    line_croissant.set_ydata(productDf['new_mp'][start:end])

    line_basket.set_xdata(ts_basket)
    line_basket.set_ydata(picknickBasket['mid_price'][start:end])

    # Update checkbox-controlled offset bands
    for i in range(len(offset_constants)):
        offset_lines[i].set_xdata(ts)
        offset_lines[i].set_ydata(productDf[f'plot_{i}'][start:end])
        offset_lines[i].set_visible(offset_visibility[i])

    ax.set_xlim(ts.iloc[0], ts.iloc[-1])
    ax.relim()
    ax.autoscale_view()
    fig.canvas.draw_idle()

slider.on_changed(update)

# --- CHECKBOX ---
ax_check = plt.axes([0.82, 0.4, 0.15, 0.15])
checkbox = CheckButtons(ax_check, offset_labels, offset_visibility)

def toggle_offset(label):
    i = offset_labels.index(label)
    offset_visibility[i] = not offset_visibility[i]
    offset_lines[i].set_visible(offset_visibility[i])
    fig.canvas.draw_idle()

checkbox.on_clicked(toggle_offset)

plt.show()