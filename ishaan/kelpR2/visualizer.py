import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider

# VWAP Visualizer

# USER TODO: CHANGE PRODUCT NAME
product = 'KELP'

# df of mid price
df = pd.read_csv('prices_round_2_day_-1.csv', delimiter=';')

productDf = df[df['product'] == product]
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

# plot mid price vs VWAP
plt.figure(figsize=(20, 10))

# plot mid price
plt.plot(time.to_numpy(), mid_price.to_numpy(), label='Mid Price')

# plot VWAP
plt.plot(time.to_numpy(), vwap.to_numpy(), label='VWAP', color='orange')

# plot VWAP +- STD (average variance betwewen mid price and VWAP)
plt.plot(productDf["timestamp"], productDf["vwap"] + fixedSTD, label='Upper bound FIXED (vwap + std)', color='green')
plt.plot(productDf["timestamp"], productDf["vwap"] - fixedSTD, label='Lower bound FIXED (vwap + std)', color='red')

plt.legend()
plt.xticks(time[::500], rotation = 90)
plt.title('Mid Price vs VWAP')
plt.xlabel('Ticks')
plt.ylabel('Mid Price')
plt.grid(True)
plt.show()


# calc and plot threshold