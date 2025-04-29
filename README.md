# 🏝️ IMC Prosperity Island Trading Challenge

This repository documents our team's strategies and algorithms developed throughout the IMC Prosperity algorithmic trading simulation. The challenge unfolded over multiple rounds, each introducing new products, market mechanics, and strategic considerations. We focused on building modular, adaptive trading bots capable of handling diverse asset classes—ranging from commodities and baskets to exotic options.

---

## 📚 Tutorial Round

### Products: `RAINFOREST_RESIN`, `KELP`  
- Introduced basic market-making strategies with symmetric bid/ask spreads.
- Observed `KELP` volatility and implemented reversion-based scalping.
- Used this round to stress test execution logic and develop a reusable framework.

**Position Limits:**  
- `RAINFOREST_RESIN`: 50  
- `KELP`: 50  

---

## 🔄 Round 1

### Products: `RAINFOREST_RESIN`, `KELP`, `SQUID_INK`
- Carried forward market-making for stable assets (`RESIN`, `KELP`).
- Developed mean-reversion model for `SQUID_INK` using deviation from moving average.
- Volatility filters helped avoid overtrading during large price swings.

**Position Limits:**  
- `RAINFOREST_RESIN`: 50  
- `KELP`: 50  
- `SQUID_INK`: 50  

---

## 🧺 Round 2

### Products: `CROISSANTS`, `JAMS`, `DJEMBES`, `PICNIC_BASKET1`, `PICNIC_BASKET2`
- Introduced **Basket Arbitrage**: 
  - Estimated synthetic values of `PICNIC_BASKET1` and `PICNIC_BASKET2` based on components.
  - Executed arbitrage trades when discrepancies exceeded dynamic thresholds.
- Built conversion-aware inventory tracking system to avoid overshooting position limits.

**Position Limits:**  
- `CROISSANTS`: 250  
- `JAMS`: 350  
- `DJEMBES`: 60  
- `PICNIC_BASKET1`: 60  
- `PICNIC_BASKET2`: 100  

---

## 🌋 Round 3

### Products: `VOLCANIC_ROCK`, `VOLCANIC_ROCK_VOUCHER_*`
- Deployed **Volatility Arbitrage Engine (VolcanicVoucherArb)**:
  - Used Black-Scholes modeling to infer implied volatility from each voucher.
  - Fit a parabola to IV vs moneyness (log(K/S) / sqrt(TTE)) for arbitrage opportunities.
  - Implemented delta hedging using `VOLCANIC_ROCK` to minimize risk.
- Added tracking for time-to-expiry and adjusted risk exposure accordingly.

**Position Limits:**  
- `VOLCANIC_ROCK`: 400  
- Each `VOLCANIC_ROCK_VOUCHER_*`: 200  

---

## 🍬 Round 4

### Product: `MAGNIFICENT_MACARONS`
- Built **CSI-based macro strategy**:
  - Estimated Critical Sunlight Index (CSI) threshold.
  - Traded long MACARONS and SUGAR components when sunlight index fell below CSI.
  - Applied trend confirmation logic to prevent false triggers.

**Position Limits:**  
- `MAGNIFICENT_MACARONS`: 75  
- Conversion Limit: 10  

---

## 🏁 Round 5

### No New Products Introduced

- Focused on **strategy refinement** and **PnL optimization**.
- Leveraged new `counter_party` field from `OwnTrade` to identify predatory participants.
- Adjusted pricing based on counterparty behavior and patterns (e.g., avoid overfitting to aggressive bots).

---

## ⚙️ Strategy Highlights

- 📊 **Basket Arbitrage**: Fast comparison of synthetic vs market price using vectorized calculations.
- 🔁 **Mean Reversion**: Multi-asset deviation detection with adaptive windowing.
- 🧠 **Volatility Arbitrage**: Fitted implied volatility curve and traded mispriced options.
- 🧮 **Delta Hedging**: Real-time greeks approximation with slippage- and inventory-aware execution.
- 🌞 **Macro Factor Strategy**: CSI-driven macro indicator for luxury goods pricing.

---

## 🛠️ Tech Stack

- **Language**: Python 3.10+
- **Frameworks**: Custom strategy scheduler and state tracker
- **Tools**: Pandas, NumPy, Matplotlib for analysis and debugging
- **Testing**: Historical simulation via provided replay engine and backtesting logs

---

---

## 📬 Contact

For questions, reach out to our team:  
**Ishaan Jain**  
📧 [ishaanj@umich.edu](mailto:ishaanj@umich.edu)  
**Sunny Shah**  
📧 [sunnysha@umich.edu](mailto:sunnysha@umich.edu)  
**Anirudh Nanduri**  
📧 [anirudn@umich.edu](mailto:anirudn@umich.edu)  
**Abhinav Attaluri**  
📧 [abhiatt@umich.edu](mailto:abhiatt@umich.edu)  
**Aadi Samineni**  
📧 [asaminen@umich.edu](mailto:asaminen@umich.edu)  


---
