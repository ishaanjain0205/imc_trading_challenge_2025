import json
import jsonpickle
from typing import List, Dict, Any, Tuple
import statistics
import numpy as np
import math

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )

        # We truncate state.traderData, trader_data, and self.logs to the same max. length to fit the log limit
        max_item_length = (self.max_log_length - base_length) // 3

        print(
            self.to_json(
                [
                    self.compress_state(state, self.truncate(state.traderData, max_item_length)),
                    self.compress_orders(orders),
                    conversions,
                    self.truncate(trader_data, max_item_length),
                    self.truncate(self.logs, max_item_length),
                ]
            )
        )

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing.symbol, listing.product, listing.denomination])

        return compressed

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]

        return compressed

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append(
                    [
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.buyer,
                        trade.seller,
                        trade.timestamp,
                    ]
                )

        return compressed

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sugarPrice,
                observation.sunlightIndex,
            ]

        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        compressed = []
        for arr in orders.values():
            for order in arr:
                compressed.append([order.symbol, order.price, order.quantity])

        return compressed

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value

        return value[: max_length - 3] + "..."


logger = Logger()

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
        "position_limit": 50,
    },
    Product.KELP: {
        "alpha": 0.2,              # slightly higher alpha for more responsiveness
        "history_window": 10,      # longer history for volatility estimation
        "tick_size": 1,
        "take_threshold": 2,       # wait for larger deviation before aggressive orders
        "reversion_beta": -0.229,  # reversion factor to pull fair value toward mean
        "adverse_volume": 15,      # filter out small orders in order book
        "position_limit": 50,
        "base_quantity": 5,
        "LOWER_BOUND": 9996,
        "UPPER_BOUND": 10004,
        "BOUND_TOLERANCE": 2,
        "MAX_HISTORY": 2,
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
        self.alpha = params.get("alpha", 0.2)
        self.position_limit = params.get("position_limit", 50)
        self.base_quantity = params.get("base_quantity", 5)
        self.lower_bound = params.get("LOWER_BOUND", 9996)
        self.upper_bound = params.get("UPPER_BOUND", 10004)
        self.bound_tolerance = params.get("BOUND_TOLERANCE", 2)
        self.max_history = params.get("MAX_HISTORY", 2)
        self.history: List[float] = []
        self.fair_value: float = params.get("fair_value", 10000)

    def run(self, current_price: float, order_depth: OrderDepth, position: int) -> List[Order]:
        """
        Kelp-specific logic. We assume the Trader has already computed 'current_price',
        so we do *not* try to figure out best bid/ask here. We just do:
          - track a short rolling 'history'
          - update an EMA 'fair_value'
          - place mean-reversion & momentum-based orders
          - return a list of Orders
        """
        # 1) Update rolling history
        self.history.append(current_price)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        # 2) Estimate volatility from short history
        if len(self.history) > 1:
            try:
                volatility = statistics.stdev(self.history)
            except Exception:
                volatility = abs(self.history[-1] - self.history[-2])
        else:
            volatility = 0

        # 3) Update fair value (EMA)
        prev_fv = self.fair_value
        self.fair_value = self.alpha * current_price + (1 - self.alpha) * prev_fv

        # 4) Mean Reversion check
        near_lower = (current_price <= (self.lower_bound + self.bound_tolerance))
        near_upper = (current_price >= (self.upper_bound - self.bound_tolerance))

        tick_size = 1
        spread_adjustment = max(1, volatility)
        bid_price = self.fair_value - spread_adjustment
        ask_price = self.fair_value + spread_adjustment

        if near_lower:
            bid_price = min(bid_price + tick_size, current_price)
        if near_upper:
            ask_price = max(ask_price - tick_size, current_price)

        order_qty = self.base_quantity
        if near_lower:
            order_qty *= 30
        if near_upper:
            order_qty *= 30

        max_buy = min(order_qty, self.position_limit - position)
        max_sell = min(order_qty, position + self.position_limit)

        orders: List[Order] = []
        if max_buy > 0:
            orders.append(Order(Product.KELP, int(bid_price), max_buy))
        if max_sell > 0:
            orders.append(Order(Product.KELP, int(ask_price), -max_sell))

        # 5) Momentum filter
        if len(self.history) >= 2:
            prev_price = self.history[-2]
            if current_price > prev_price:
                momentum_buy_qty = min(20, self.position_limit - position)
                if momentum_buy_qty > 0:
                    buy_price = current_price
                    orders.append(Order(Product.KELP, int(buy_price), momentum_buy_qty))

        # 6) Return orders only (no flush or logging)
        return orders




        

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

    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        result = {}
        conversions = 0
        trader_data = ""

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
                if product == Product.RAINFOREST_RESIN:
                    orders = algo.run(current_price, order_depth, position)
                elif product == Product.KELP:
                    orders = algo.run(current_price, order_depth, position)
                # orders = algo.run(current_price, order_depth, position)
            else:
                orders = []

            result[product] = orders

        conversions = 1
        trader_data = jsonpickle.encode(traderState)

        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data
    


''' 
    restructure KelpAlgo to just perform the algorithm unique for it

    remove all steps such as calculating best bid and best ask price since those are already done in Trader.run()

    at the end of KelpAlgo, make sure to only return orders and do nothing else, remaining steps such as flushing 
    are done in Trader.run()

'''