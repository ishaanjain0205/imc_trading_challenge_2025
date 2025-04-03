import json
import jsonpickle
from typing import List, Dict, Any, Tuple
import statistics
import numpy as np
import math

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState

# Define products (mapping our assets to competitor–style logic)
class Product:
    RAINFOREST_RESIN = "RAINFOREST_RESIN"  # stable asset
    KELP = "KELP"                          # more volatile

# Global parameters for each product
PARAMS = {
    Product.RAINFOREST_RESIN: {
        "fair_value": 10000,       # initial fair value
        "alpha": 0.2,              # smoothing factor for EMA
        "history_window": 5,       # short history since price is stable
        "tick_size": 1,            
        "take_threshold": 1,       # aggressive adjustment if price deviates by >1
        "position_limit": 20,
    },
    Product.KELP: {
        "alpha": 0.3,              # slightly higher alpha for more responsiveness
        "history_window": 10,      # longer history for volatility estimation
        "tick_size": 1,
        "take_threshold": 2,       # wait for larger deviation before aggressive orders
        "reversion_beta": -0.229,  # reversion factor to pull fair value toward mean
        "adverse_volume": 15,      # filter out small orders in order book
        "position_limit": 20,
    },
}

# -----------------------------
# Product-Specific Algorithm Classes
# -----------------------------

class RainforestResinAlgo:
    def __init__(self, params: Dict[str, Any]):
        self.params = params
        self.fair_value = params["fair_value"]
        self.history: List[float] = []
        self.alpha = params["alpha"]
        self.history_window = params["history_window"]
        self.tick_size = params["tick_size"]
        self.position_limit = params["position_limit"]

    def update_fair_value(self, current_price: float) -> float:
        # Update history with current price
        self.history.append(current_price)
        if len(self.history) > self.history_window:
            self.history = self.history[-self.history_window:]
        # Update fair value with EMA
        self.fair_value = self.alpha * current_price + (1 - self.alpha) * self.fair_value
        return self.fair_value

    def run(self, current_price: float, order_depth: OrderDepth, position: int) -> List[Order]:
        fv = self.update_fair_value(current_price)
        tick = self.tick_size
        # Since Rainforest Resin is stable, use a minimal spread adjustment.
        bid_price = fv - tick
        ask_price = fv + tick

        # Aggressive adjustment if current price deviates notably
        if current_price < fv - self.params["take_threshold"]:
            bid_price = current_price + tick  # buy aggressively
        if current_price > fv + self.params["take_threshold"]:
            ask_price = current_price - tick  # sell aggressively

        orders: List[Order] = []
        max_buy = max(0, self.position_limit - position)
        max_sell = max(0, self.position_limit + position)
        if max_buy > 0:
            orders.append(Order(Product.RAINFOREST_RESIN, int(bid_price), max_buy))
        if max_sell > 0:
            orders.append(Order(Product.RAINFOREST_RESIN, int(ask_price), -max_sell))
        return orders

class KelpAlgo:
    def __init__(self, params: Dict[str, Any]):
        self.params = params
        self.history: List[float] = []
        self.fair_value: float = None  # will be computed dynamically
        self.alpha = params["alpha"]
        self.history_window = params["history_window"]
        self.tick_size = params["tick_size"]
        self.reversion_beta = params["reversion_beta"]
        self.adverse_volume = params["adverse_volume"]
        self.position_limit = params["position_limit"]
        self.last_mm_price: float = None  # to track last market maker mid-price

    def update_history(self, current_price: float) -> None:
        self.history.append(current_price)
        if len(self.history) > self.history_window:
            self.history = self.history[-self.history_window:]

    def compute_dynamic_fair_value(self, order_depth: OrderDepth, current_price: float) -> float:
        # Use order book if both sides available
        if order_depth.buy_orders and order_depth.sell_orders:
            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            # Filter orders to avoid small volumes (adverse volume)
            filtered_bids = [price for price in order_depth.buy_orders if order_depth.buy_orders[price] >= self.adverse_volume]
            filtered_asks = [price for price in order_depth.sell_orders if abs(order_depth.sell_orders[price]) >= self.adverse_volume]
            mm_bid = max(filtered_bids) if filtered_bids else best_bid
            mm_ask = min(filtered_asks) if filtered_asks else best_ask
            mm_mid = (mm_bid + mm_ask) / 2
        else:
            mm_mid = current_price
        # Use last mid-price to calculate return if available
        if self.last_mm_price is not None:
            last_return = (mm_mid - self.last_mm_price) / self.last_mm_price
            fv = mm_mid + (mm_mid * last_return * self.reversion_beta)
        else:
            fv = mm_mid
        self.last_mm_price = mm_mid
        return fv

    def run(self, current_price: float, order_depth: OrderDepth, position: int) -> List[Order]:
        # Update history window for volatility estimation
        self.update_history(current_price)
        # Compute dynamic fair value using order book data and reversion factor
        fv = self.compute_dynamic_fair_value(order_depth, current_price)
        # Optionally, update fair value via EMA for smoothing (if desired)
        if self.fair_value is None:
            self.fair_value = fv
        else:
            self.fair_value = self.alpha * fv + (1 - self.alpha) * self.fair_value

        # Calculate volatility from history
        if len(self.history) > 1:
            try:
                volatility = statistics.stdev(self.history)
            except Exception:
                volatility = abs(current_price - self.history[-2])
        else:
            volatility = 0

        tick = self.tick_size
        spread_adjustment = volatility + tick

        bid_price = self.fair_value - spread_adjustment
        ask_price = self.fair_value + spread_adjustment

        # For Kelp, use a wider threshold before aggressive adjustments
        if current_price < self.fair_value - self.params["take_threshold"]:
            bid_price = current_price + tick  # buy aggressively
        if current_price > self.fair_value + self.params["take_threshold"]:
            ask_price = current_price - tick  # sell aggressively

        orders: List[Order] = []
        max_buy = max(0, self.position_limit - position)
        max_sell = max(0, self.position_limit + position)
        if max_buy > 0:
            orders.append(Order(Product.KELP, int(bid_price), max_buy))
        if max_sell > 0:
            orders.append(Order(Product.KELP, int(ask_price), -max_sell))
        return orders

# -----------------------------
# Updated Trader Class
# -----------------------------

class Trader:
    def __init__(self, params: Dict[str, Dict[str, Any]] = None) -> None:
        if params is None:
            params = PARAMS
        self.params = params
        # Instantiate the product-specific algorithms
        self.algos = {
            Product.RAINFOREST_RESIN: RainforestResinAlgo(self.params[Product.RAINFOREST_RESIN]),
            Product.KELP: KelpAlgo(self.params[Product.KELP]),
        }

    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        # traderData can be used to store any cross-iteration information; here we reinitialize it.
        traderState = {}
        result: Dict[str, List[Order]] = {}

        # Loop over each product present in the order_depths
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            # Compute current price as mid-price if both sides available; otherwise, fallback to a default value
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                current_price = (best_bid + best_ask) / 2
            else:
                # Fallback: use previously stored fair value or default to 10
                current_price = traderState.get(product, {}).get("fair_value", 10)

            # Get current position for product
            position = state.position.get(product, 0)
            if product in self.algos:
                algo = self.algos[product]
                orders = algo.run(current_price, order_depth, position)
            else:
                orders = []

            result[product] = orders

        conversions = 1
        traderData = jsonpickle.encode(traderState)
        return result, conversions, traderData
