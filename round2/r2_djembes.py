import string
import statistics
import json
import jsonpickle
from collections import deque
from typing import List, Dict, Any
import numpy as np

from datamodel import (
    OrderDepth,
    TradingState,
    Order,
    Symbol,
    ProsperityEncoder,
    Listing,
    Trade,
    Observation
)

class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, List[Order]], conversions: int, trader_data: str) -> None:
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

    def compress_state(self, state: TradingState, trader_data: str) -> List[Any]:
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

    def compress_listings(self, listings: Dict[Symbol, Listing]) -> List[List[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing.symbol, listing.product, listing.denomination])
        return compressed

    def compress_order_depths(self, order_depths: Dict[Symbol, OrderDepth]) -> Dict[Symbol, List[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]
        return compressed

    def compress_trades(self, trades: Dict[Symbol, List[Trade]]) -> List[List[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append([
                    trade.symbol,
                    trade.price,
                    trade.quantity,
                    trade.buyer,
                    trade.seller,
                    trade.timestamp,
                ])
        return compressed

    def compress_observations(self, observations: Observation) -> List[Any]:
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

    def compress_orders(self, orders: Dict[Symbol, List[Order]]) -> List[List[Any]]:
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

import numpy as np
from typing import List, Dict

# Assuming Order, OrderDepth, and TradingState classes are already defined in your framework.

class PicnicBasket2Strat:
    def __init__(self) -> None:
        self.name = "PicnicBasket2Strat"
        # Parameters calibrated from historical data analysis:
        self.spread_std_window = 30          # number of spread observations to use (you can adjust this)
        self.zscore_threshold = 2.0          # entry threshold for trading (calibrated from historical data)
        self.exit_threshold = 0.2            # exit threshold (neutralization zone)
        self.target_position = 70            # maximum target position (long or short)
        self.spread_history: List[float] = []  # history of spread values

    def load(self, data: dict) -> None:
        # No persistent state is maintained for this strategy.
        pass

    def save(self) -> dict:
        return {}

    def get_synthetic_order_depth(self, order_depths: Dict[str, 'OrderDepth']) -> 'OrderDepth':
        """
        Construct a synthetic order depth for PICNIC_BASKET2 from CROISSANTS and JAMS.
        PICNIC_BASKET2 consists of:
            - 4 CROISSANTS
            - 2 JAMS
        """
        synthetic = OrderDepth()
        synthetic.buy_orders = {}
        synthetic.sell_orders = {}
        
        croissant_od = order_depths.get("CROISSANTS")
        jams_od = order_depths.get("JAMS")
        if croissant_od is None or jams_od is None:
            return synthetic
        
        best_bid_C = max(croissant_od.buy_orders.keys()) if croissant_od.buy_orders else 0
        best_ask_C = min(croissant_od.sell_orders.keys()) if croissant_od.sell_orders else float("inf")
        best_bid_J = max(jams_od.buy_orders.keys()) if jams_od.buy_orders else 0
        best_ask_J = min(jams_od.sell_orders.keys()) if jams_od.sell_orders else float("inf")
        
        # Calculate the implied bid and ask prices based on component prices.
        implied_bid = (best_bid_C * 4) + (best_bid_J * 2)
        implied_ask = (best_ask_C * 4) + (best_ask_J * 2)
        
        # Determine available volume (full baskets available).
        if best_bid_C > 0 and best_bid_J > 0:
            vol_bid_C = croissant_od.buy_orders[best_bid_C] // 4
            vol_bid_J = jams_od.buy_orders[best_bid_J] // 2
            synthetic_bid_volume = min(vol_bid_C, vol_bid_J)
            synthetic.buy_orders[implied_bid] = synthetic_bid_volume
        
        if best_ask_C < float("inf") and best_ask_J < float("inf"):
            vol_ask_C = abs(croissant_od.sell_orders[best_ask_C]) // 4
            vol_ask_J = abs(jams_od.sell_orders[best_ask_J]) // 2
            synthetic_ask_volume = min(vol_ask_C, vol_ask_J)
            synthetic.sell_orders[implied_ask] = -synthetic_ask_volume

        return synthetic

    def get_swmid(self, order_depth: 'OrderDepth') -> float:
        """
        Computes a volume-weighted mid-price (swmid) given an order depth.
        """
        if order_depth.buy_orders and order_depth.sell_orders:
            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            bid_vol = order_depth.buy_orders[best_bid]
            ask_vol = abs(order_depth.sell_orders[best_ask])
            return (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)
        return None

    def convert_synthetic_orders(self, synthetic_orders: List['Order'],
                                 order_depths: Dict[str, 'OrderDepth'],
                                 positions: Dict[str, int]) -> List['Order']:
        """
        Convert a synthetic PICNIC_BASKET2 order to underlying orders for CROISSANTS and JAMS.
        Basket weights: 4 CROISSANTS and 2 JAMS.
        This updated version also checks that executing the order will not push the underlying positions
        past their limits (assumed: CROISSANTS limit = 250, JAMS limit = 350).
        """
        converted_orders = []
        # Define underlying limits
        croissant_limit = 250
        jams_limit = 350
        
        croissant_od = order_depths.get("CROISSANTS")
        jams_od = order_depths.get("JAMS")
        if not croissant_od or not jams_od or synthetic_orders is None:
            return converted_orders

        for order in synthetic_orders:
            # For BUY synthetic orders, we execute underlying SELL orders.
            # (Selling underlying reduces long positions or increases short positions.)
            if order.quantity > 0:
                best_ask_C = min(croissant_od.sell_orders.keys()) if croissant_od.sell_orders else None
                best_ask_J = min(jams_od.sell_orders.keys()) if jams_od.sell_orders else None
                if best_ask_C is None or best_ask_J is None:
                    continue
                # Liquidity check: ensure underlying volumes are sufficient.
                if croissant_od.sell_orders[best_ask_C] < order.quantity * 4 or \
                   jams_od.sell_orders[best_ask_J] < order.quantity * 2:
                    continue

                # Retrieve current positions for underlying instruments.
                current_c_pos = positions.get("CROISSANTS", 0)
                current_j_pos = positions.get("JAMS", 0)
                # For a SELL order, the position will decrease.
                # If already short (negative), further selling moves farther from zero.
                # Only constrain if the instrument is already short.
                if current_c_pos < 0:
                    allowed_sell_C = croissant_limit - abs(current_c_pos)
                else:
                    allowed_sell_C = order.quantity * 4  # no limit issue if position is non-negative
                if current_j_pos < 0:
                    allowed_sell_J = jams_limit - abs(current_j_pos)
                else:
                    allowed_sell_J = order.quantity * 2

                # The maximum underlying volume we can safely trade without breaching the limits:
                max_safe_qty = min((allowed_sell_C / 4), (allowed_sell_J / 2))
                # Scale down synthetic order if needed.
                adjusted_quantity = int(order.quantity * min(max_safe_qty, 1))
                if adjusted_quantity <= 0:
                    continue
                converted_orders.append(Order("CROISSANTS", best_ask_C, adjusted_quantity * 4))
                converted_orders.append(Order("JAMS", best_ask_J, adjusted_quantity * 2))
            
            # For SELL synthetic orders, we execute underlying BUY orders.
            elif order.quantity < 0:
                best_bid_C = max(croissant_od.buy_orders.keys()) if croissant_od.buy_orders else None
                best_bid_J = max(jams_od.buy_orders.keys()) if jams_od.buy_orders else None
                if best_bid_C is None or best_bid_J is None:
                    continue
                if croissant_od.buy_orders[best_bid_C] < abs(order.quantity) * 4 or \
                   jams_od.buy_orders[best_bid_J] < abs(order.quantity) * 2:
                    continue

                current_c_pos = positions.get("CROISSANTS", 0)
                current_j_pos = positions.get("JAMS", 0)
                # For a BUY order, the position will increase.
                # If already long (positive), additional buying moves further from zero.
                if current_c_pos > 0:
                    allowed_buy_C = croissant_limit - current_c_pos
                else:
                    allowed_buy_C = abs(order.quantity) * 4
                if current_j_pos > 0:
                    allowed_buy_J = jams_limit - current_j_pos
                else:
                    allowed_buy_J = abs(order.quantity) * 2

                max_safe_qty = min((allowed_buy_C / 4), (allowed_buy_J / 2))
                adjusted_quantity = int(abs(order.quantity) * min(max_safe_qty, 1))
                if adjusted_quantity <= 0:
                    continue
                # Note the negative sign in the order quantity for an underlying BUY order.
                converted_orders.append(Order("CROISSANTS", best_bid_C, -adjusted_quantity * 4))
                converted_orders.append(Order("JAMS", best_bid_J, -adjusted_quantity * 2))
        return converted_orders

    def execute_spread_orders(self, target_position: int, basket_position: int,
                                order_depths: Dict[str, 'OrderDepth'],
                                positions: Dict[str, int]) -> List['Order']:
        """
        Executes spread orders for PICNIC_BASKET2:
          - Adjusts the current basket position toward the target.
          - Simultaneously creates a synthetic order (to be hedged) which is then converted to underlying orders.
        Note: The positions dict is passed along so that underlying orders can be checked against limits.
        """
        orders = []
        # Using updated position limits (100 for PICNIC_BASKET2)
        target_qty = abs(target_position - basket_position)
        
        basket_od = order_depths.get("PICNIC_BASKET2")
        if basket_od is None:
            return orders

        synthetic_od = self.get_synthetic_order_depth(order_depths)

        # For increasing basket position (long entry)
        if target_position > basket_position:
            if not basket_od.sell_orders or not synthetic_od.buy_orders:
                return orders
            basket_ask_price = min(basket_od.sell_orders.keys())
            basket_ask_vol = abs(basket_od.sell_orders[basket_ask_price])
            
            synthetic_bid_price = max(synthetic_od.buy_orders.keys())
            synthetic_bid_vol = synthetic_od.buy_orders[synthetic_bid_price]
            
            exec_vol = min(basket_ask_vol, synthetic_bid_vol, target_qty)
            if exec_vol > 0:
                basket_order = Order("PICNIC_BASKET2", basket_ask_price, exec_vol)
                synthetic_order = Order("SYNTHETIC_PICNIC_BASKET2", synthetic_bid_price, -exec_vol)
                orders.append(basket_order)
                underlying_orders = self.convert_synthetic_orders([synthetic_order], order_depths, positions)
                orders.extend(underlying_orders)
        # For decreasing basket position (short entry or exiting long)
        else:
            if not basket_od.buy_orders or not synthetic_od.sell_orders:
                return orders
            basket_bid_price = max(basket_od.buy_orders.keys())
            basket_bid_vol = basket_od.buy_orders[basket_bid_price]
            
            synthetic_ask_price = min(synthetic_od.sell_orders.keys())
            synthetic_ask_vol = abs(synthetic_od.sell_orders[synthetic_ask_price])
            
            exec_vol = min(basket_bid_vol, synthetic_ask_vol, target_qty)
            if exec_vol > 0:
                basket_order = Order("PICNIC_BASKET2", basket_bid_price, -exec_vol)
                synthetic_order = Order("SYNTHETIC_PICNIC_BASKET2", synthetic_ask_price, exec_vol)
                orders.append(basket_order)
                underlying_orders = self.convert_synthetic_orders([synthetic_order], order_depths, positions)
                orders.extend(underlying_orders)
        return orders

    def run_strategy(self, state: 'TradingState') -> List['Order']:
        """
        Main entry:
         - Computes the spread (actual basket price minus synthetic value).
         - Dynamically scales the target basket position when the z–score exceeds the entry threshold.
         - Implements exit logic (neutralization) when the spread z–score is within a narrow band (±exit_threshold).
         - Passes state.position to ensure the synthetic orders don’t hit underlying position limits.
        """
        orders: List[Order] = []
        required = ["PICNIC_BASKET2", "CROISSANTS", "JAMS"]
        for key in required:
            if key not in state.order_depths:
                return orders

        basket_od = state.order_depths["PICNIC_BASKET2"]
        basket_position = state.position.get("PICNIC_BASKET2", 0)
        synthetic_od = self.get_synthetic_order_depth(state.order_depths)

        swmid_basket = self.get_swmid(basket_od)
        swmid_synthetic = self.get_swmid(synthetic_od)
        if swmid_basket is None or swmid_synthetic is None:
            return orders

        spread = swmid_basket - swmid_synthetic
        self.spread_history.append(spread)
        # Keep the history window up to spread_std_window.
        if len(self.spread_history) > self.spread_std_window:
            self.spread_history = self.spread_history[-self.spread_std_window:]
        
        # Only trade when we have enough observations.
        if len(self.spread_history) < self.spread_std_window:
            return orders
        
        spread_mean = np.mean(self.spread_history)
        spread_std = np.std(self.spread_history)
        if spread_std == 0:
            return orders  # avoid division by zero
        zscore = (spread - spread_mean) / spread_std

        # --- Exit logic: If spread mean reverts (zscore near 0), close out position.
        if abs(zscore) < self.exit_threshold and basket_position != 0:
            # Neutralize the position (target position = 0)
            return self.execute_spread_orders(0, basket_position, state.order_depths, state.position)
        
        # --- Entry logic: if zscore exceeds entry threshold, adjust position.
        if abs(zscore) >= self.zscore_threshold:
            # Dynamically scale the target position.
            # When zscore equals zscore_threshold, multiplier is 0; when zscore equals 4, multiplier is 1.
            multiplier = (abs(zscore) - self.zscore_threshold) / (4.0 - self.zscore_threshold)
            multiplier = min(max(multiplier, 0), 1)
            scaled_target = int(self.target_position * multiplier)
            target_position = -scaled_target if zscore > 0 else scaled_target
            if basket_position != target_position:
                return self.execute_spread_orders(target_position, basket_position, state.order_depths, state.position)

        # Otherwise, no orders.
        return orders

class arbDynamic:
    def __init__(self) -> None:
        self.name = "arbDynamic"
        self.threshold = 0.00035  # stdev threshold for DJEMBES volatility
        self.rollingWindow = 10    # rolling window length for DJEMBES price history
        self.price_history: List[float] = []  # store DJEMBES mid prices

    def load(self, data: dict) -> None:
        if data and "price_history" in data:
            self.price_history = data["price_history"]
        else:
            self.price_history = []

    def save(self) -> dict:
        return {"price_history": self.price_history}
    
    def run_strategy(self, state: TradingState) -> List[Order]:
        """
        This strategy trades only PICNIC_BASKET1 (ignoring PICNIC_BASKET2)
        based on the rolling volatility of DJEMBES. If the DJEMBES volatility
        exceeds self.threshold, no trade is executed.
        
        Otherwise, the strategy computes the expected price for PICNIC_BASKET1 using:
             Expected_B1 = mid_PICNIC_BASKET2 + 2*(mid_CROISSANTS) + (mid_JAMSS) + (mid_DJEMBES)
        and compares it with the mid–price of PICNIC_BASKET1.
        
        A positive signal (expected > actual) triggers a BUY order on PICNIC_BASKET1;
        a negative signal triggers a SELL order. The quantity traded is limited both
        by the basket position limits and by the available capacity on the underlying
        products to "build" the basket:
            - PICNIC_BASKET1 consists of: 6 CROISSANTS, 3 JAMSS, 1 DJEMBES.
        """
        # Helper function: Compute mid–price from an order depth.
        def get_mid(depth: OrderDepth) -> float:
            if depth.buy_orders and depth.sell_orders:
                best_bid = max(depth.buy_orders.keys())
                best_ask = min(depth.sell_orders.keys())
                return (best_bid + best_ask) / 2.0
            return None

        # Update DJEMBES price history.
        if "DJEMBES" not in state.order_depths:
            return []
        mid_D = get_mid(state.order_depths["DJEMBES"])
        if mid_D is None:
            return []
        self.price_history.append(mid_D)
        if len(self.price_history) > self.rollingWindow:
            self.price_history = self.price_history[-self.rollingWindow:]
        
        # Calculate rolling volatility for DJEMBES.
        def calc_rolling_volatility() -> float:
            if len(self.price_history) > 1:
                returns = [p2 - p1 for p1, p2 in zip(self.price_history[:-1], self.price_history[1:])]
                if len(returns) > 1:
                    return statistics.pstdev(returns)
                else:
                    return abs(returns[0])
            else:
                return 0.0

        if calc_rolling_volatility() > self.threshold:
            return []  # Do not trade if volatility of DJEMBES is too high.
        
        # Check that required order depths are available.
        required = ["PICNIC_BASKET1", "PICNIC_BASKET2", "CROISSANTS", "JAMSS", "DJEMBES"]
        for key in required:
            if key not in state.order_depths:
                return []
        
        # Compute mid–prices for all required products.
        mid_B1 = get_mid(state.order_depths["PICNIC_BASKET1"])
        mid_B2 = get_mid(state.order_depths["PICNIC_BASKET2"])
        mid_C  = get_mid(state.order_depths["CROISSANTS"])
        mid_J  = get_mid(state.order_depths["JAMSS"])
        # mid_D is already computed.
        if None in [mid_B1, mid_B2, mid_C, mid_J, mid_D]:
            return []
        
        # Compute expected price for PICNIC_BASKET1.
        expected_B1 = mid_B2 + 2 * mid_C + mid_J + mid_D  # per basket composition
        
        # Determine signal for PICNIC_BASKET1 (only trade basket1).
        signal_B1 = 1 if expected_B1 > mid_B1 else (-1 if expected_B1 < mid_B1 else 0)
        if signal_B1 == 0:
            return []
        
        # Position limits for baskets and underlying products.
        pos_limits = {
            "PICNIC_BASKET1": 60,
            "PICNIC_BASKET2": 100,
            "CROISSANTS": 250,
            "JAMSS": 350,
            "DJEMBES": 60,
        }
        
        # Get current position for PICNIC_BASKET1.
        pos_B1 = state.position.get("PICNIC_BASKET1", 0)
        # Determine available quantity for PICNIC_BASKET1 based on basket limits.
        avail_B1 = (pos_limits["PICNIC_BASKET1"] - pos_B1) if signal_B1 == 1 else (pos_B1 + pos_limits["PICNIC_BASKET1"])
        Q = avail_B1
        if Q <= 0:
            return []
        
        # Additional capacity check: Underlying product capacity to "build" PICNIC_BASKET1.
        # PICNIC_BASKET1 requires: 6 CROISSANTS, 3 JAMSS, 1 DJEMBES.
        curr_C = state.position.get("CROISSANTS", 0)
        curr_J = state.position.get("JAMSS", 0)
        curr_D = state.position.get("DJEMBES", 0)
        if signal_B1 == 1:
            max_create_b1 = min(
                (pos_limits["CROISSANTS"] - curr_C) // 6,
                (pos_limits["JAMSS"] - curr_J) // 3,
                (pos_limits["DJEMBES"] - curr_D) // 1
            )
        else:
            max_create_b1 = min(
                (curr_C + pos_limits["CROISSANTS"]) // 6,
                (curr_J + pos_limits["JAMSS"]) // 3,
                (curr_D + pos_limits["DJEMBES"]) // 1
            )
        
        Q = min(Q, max_create_b1)
        if Q <= 0:
            return []
        
        orders = []
        # Place order for PICNIC_BASKET1 only.
        if signal_B1 == 1:
            orders.append(Order("PICNIC_BASKET1", int(round(mid_B1)), Q))
        else:
            orders.append(Order("PICNIC_BASKET1", int(round(mid_B1)), -Q))
        return orders

class RainforestResinStrat:
    def __init__(self) -> None:
        self.name = "RainforestResinStrat"
        self.fair_value = 10000
        self.take_width = 1
        self.clear_width = 0
        self.disregard_edge = 1
        self.join_edge = 2
        self.default_edge = 4
        self.soft_position_limit = 10
        self.min_order_size = 5
        self.max_order_size = 30
        self.position_limit = 50

    def load(self, data: dict) -> None:
        # No persistent state is maintained for this strategy.
        pass

    def save(self) -> dict:
        return {}

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int, timestamp: int) -> List[Order]:
        orders: List[Order] = []
        # Attempt to take favorable orders.
        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders.keys())
            if best_ask <= self.fair_value - self.take_width:
                quantity = min(-order_depth.sell_orders[best_ask], position_limit - position)
                if quantity > 0:
                    orders.append(Order(product, best_ask, quantity))
        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders.keys())
            if best_bid >= self.fair_value + self.take_width:
                quantity = min(order_depth.buy_orders[best_bid], position + position_limit)
                if quantity > 0:
                    orders.append(Order(product, best_bid, -quantity))
        # Post market-making orders.
        bid_price = round(self.fair_value - self.default_edge)
        ask_price = round(self.fair_value + self.default_edge)
        if position > self.soft_position_limit:
            ask_price -= 1
        elif position < -self.soft_position_limit:
            bid_price += 1
        if position_limit - position > 0:
            orders.append(Order(product, bid_price, min(3, position_limit - position)))
        if position + position_limit > 0:
            orders.append(Order(product, ask_price, -min(3, position + position_limit)))
        return orders

class KelpStrat:
    def __init__(self, window_size: int = 10) -> None:
        self.name = "KelpStrat"
        self.symbol = "KELP"  # Expect only KELP data here.
        self.position_limit = 50
        self.threshold = 0.5
        self.trade_size = 10
        self.liquidation_window = window_size
        self.pinned_window = deque(maxlen=self.liquidation_window)

    def load(self, data: dict) -> None:
        if data and "pinned" in data:
            self.pinned_window = deque(data["pinned"], maxlen=self.liquidation_window)
        else:
            self.pinned_window = deque(maxlen=self.liquidation_window)

    def save(self) -> dict:
        return {"pinned": list(self.pinned_window)}

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int, timestamp: int) -> List[Order]:
        orders: List[Order] = []
        # Compute best bid and best ask.
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2.0
        else:
            return orders

        # Compute a combined VWAP from the top three levels of both sides.
        top_buy = sorted(order_depth.buy_orders.items(), key=lambda tup: -tup[0])[:3]
        top_sell = sorted(order_depth.sell_orders.items(), key=lambda tup: tup[0])[:3]
        numerator = 0.0
        denominator = 0.0
        for price, volume in top_buy:
            numerator += price * volume
            denominator += volume
        for price, volume in top_sell:
            abs_vol = abs(volume)
            numerator += price * abs_vol
            denominator += abs_vol
        combined_vwap = numerator / denominator if denominator > 0 else mid_price

        # Compute the raw difference between mid_price and the combined VWAP.
        vol_diff = mid_price - combined_vwap
        signal = 0
        if vol_diff > self.threshold:
            signal = -1  # Sell signal.
        elif vol_diff < -self.threshold:
            signal = 1   # Buy signal.

        # Update pinned state.
        current_position = position
        pinned_now = abs(current_position) >= self.position_limit
        self.pinned_window.append(pinned_now)
        soft_liquidate = False
        hard_liquidate = False
        if len(self.pinned_window) == self.liquidation_window:
            if sum(self.pinned_window) >= self.liquidation_window / 2:
                soft_liquidate = True
            if all(self.pinned_window):
                hard_liquidate = True

        # Compute popular prices by volume.
        if order_depth.buy_orders:
            popular_buy_price, _ = max(order_depth.buy_orders.items(), key=lambda tup: tup[1])
        else:
            popular_buy_price = best_bid
        if order_depth.sell_orders:
            popular_sell_price, _ = min(order_depth.sell_orders.items(), key=lambda tup: tup[1])
        else:
            popular_sell_price = best_ask

        true_value = round((popular_buy_price + popular_sell_price) / 2) if (popular_buy_price is not None and popular_sell_price is not None) else round(mid_price)
        max_buy_price = true_value
        min_sell_price = true_value
        if current_position > self.position_limit * 0.5:
            max_buy_price = true_value - 1
        if current_position < -self.position_limit * 0.5:
            min_sell_price = true_value + 1

        # Determine allowable order sizes.
        to_buy = position_limit - current_position
        to_sell = current_position + position_limit

        # Execute orders based on the signal.
        if signal == 1 and current_position < self.position_limit:
            if best_ask is not None and best_ask <= max_buy_price:
                available = abs(order_depth.sell_orders.get(best_ask, 0))
                qty = min(self.trade_size, to_buy, available)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))
                    to_buy -= qty
        elif signal == -1 and current_position > -self.position_limit:
            if best_bid is not None and best_bid >= min_sell_price:
                available = order_depth.buy_orders.get(best_bid, 0)
                qty = min(self.trade_size, to_sell, available)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))
                    to_sell -= qty

        # Liquidation adjustments.
        if to_buy > 0 and hard_liquidate:
            buy_qty = to_buy // 2
            if buy_qty > 0:
                orders.append(Order(product, true_value, buy_qty))
                to_buy -= buy_qty
        if to_sell > 0 and hard_liquidate:
            sell_qty = to_sell // 2
            if sell_qty > 0:
                orders.append(Order(product, true_value, -sell_qty))
                to_sell -= sell_qty
        if to_buy > 0 and soft_liquidate:
            buy_qty = to_buy // 2
            if buy_qty > 0:
                orders.append(Order(product, true_value - 2, buy_qty))
                to_buy -= buy_qty
        if to_sell > 0 and soft_liquidate:
            sell_qty = to_sell // 2
            if sell_qty > 0:
                orders.append(Order(product, true_value + 2, -sell_qty))
                to_sell -= sell_qty
        if to_buy > 0 and popular_buy_price is not None:
            fallback_buy_price = min(max_buy_price, popular_buy_price + 1)
            orders.append(Order(product, fallback_buy_price, to_buy))
            to_buy = 0
        if to_sell > 0 and popular_sell_price is not None:
            fallback_sell_price = max(min_sell_price, popular_sell_price - 1)
            orders.append(Order(product, fallback_sell_price, -to_sell))
            to_sell = 0

        return orders

class SquidInkStrat:
    def __init__(self) -> None:
        self.name = "SquidInkStrat"
        # We'll store price history for the SQUID_INK product.
        self.price_history: List[float] = []

    def load(self, data: dict) -> None:
        if data and "price_history" in data:
            self.price_history = data["price_history"]
        else:
            self.price_history = []

    def save(self) -> dict:
        return {"price_history": self.price_history}

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int, timestamp: int) -> List[Order]:
        orders: List[Order] = []
        buy_orders = order_depth.buy_orders
        sell_orders = order_depth.sell_orders

        # Determine current price.
        best_bid = max(buy_orders.keys()) if buy_orders else None
        best_ask = min(sell_orders.keys()) if sell_orders else None
        if best_bid is not None and best_ask is not None:
            current_price = (best_bid + best_ask) / 2.0
        else:
            current_price = 10.0  # fallback value

        # Update price history (maintain a window of recent prices, e.g., 20).
        self.price_history.append(current_price)
        window = 20
        if len(self.price_history) > window:
            self.price_history = self.price_history[-window:]

        # Calculate moving averages.
        short_window = 5
        short_ma = sum(self.price_history[-short_window:]) / short_window if len(self.price_history) >= short_window else current_price
        long_ma = sum(self.price_history) / len(self.price_history) if self.price_history else current_price
        trend_signal = short_ma - long_ma

        # Calculate volatility.
        if len(self.price_history) > 1:
            returns = [p2 - p1 for p1, p2 in zip(self.price_history[:-1], self.price_history[1:])]
            volatility = statistics.pstdev(returns) if len(returns) > 1 else 1
        else:
            volatility = 1

        k = 1.5  # factor for adaptive threshold.
        adaptive_threshold = k * volatility
        tick_size = 1
        spread_adjustment = volatility + tick_size
        quantity = 5  # base order size

        # Decide which strategy branch to use.
        if abs(trend_signal) > adaptive_threshold:
            # Momentum strategy.
            if trend_signal > 0:
                bid_price = int(best_bid) if best_bid is not None else int(current_price)
                max_buy = min(quantity, position_limit - position)
                if max_buy > 0:
                    orders.append(Order(product, bid_price, max_buy))
            else:
                ask_price = int(best_ask) if best_ask is not None else int(current_price)
                max_sell = min(quantity, position + position_limit)
                if max_sell > 0:
                    orders.append(Order(product, ask_price, -max_sell))
        else:
            # Mean reversion / Market making approach.
            deviation = current_price - long_ma
            alpha = 0.4
            if abs(deviation) > adaptive_threshold:
                if deviation > 0:
                    ask_price = int(current_price + spread_adjustment - alpha * deviation)
                    bid_price = int(current_price - spread_adjustment)
                    max_sell = min(quantity + int(deviation), position + position_limit)
                    if max_sell > 0:
                        orders.append(Order(product, ask_price, -max_sell))
                else:
                    bid_price = int(current_price - spread_adjustment + alpha * (-deviation))
                    ask_price = int(current_price + spread_adjustment)
                    max_buy = min(quantity + int(-deviation), position_limit - position)
                    if max_buy > 0:
                        orders.append(Order(product, bid_price, max_buy))
            else:
                total_bid_vol = sum(buy_orders.values())
                total_ask_vol = -sum(sell_orders.values())
                imbalance = 0
                if (total_bid_vol + total_ask_vol) > 0:
                    imbalance = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol)
                if imbalance > 0.5:
                    ask_price = int(current_price + spread_adjustment + tick_size)
                    bid_price = int(current_price - spread_adjustment)
                elif imbalance < -0.5:
                    ask_price = int(current_price + spread_adjustment)
                    bid_price = int(current_price - spread_adjustment - tick_size)
                else:
                    ask_price = int(current_price + spread_adjustment)
                    bid_price = int(current_price - spread_adjustment)
                max_buy = min(quantity, position_limit - position)
                max_sell = min(quantity, position + position_limit)
                if max_buy > 0:
                    orders.append(Order(product, bid_price, max_buy))
                if max_sell > 0:
                    orders.append(Order(product, ask_price, -max_sell))
        return orders

class PicnicBasket2PairTrader:
    """
    Pair-trading strategy for PICNIC_BASKET2 vs. its synthetic (4 * CROISSANTS + 2 * JAMS)
    with:
      - Multi-level liquidity checks,
      - Position-limit safeguards,
      - Rolling-window volatility to dynamically scale thresholds,
      - Partial exit (scale out) instead of all-or-nothing exits.
    """

    def __init__(self) -> None:
        self.name = "PicnicBasket2PairTrader"
        # Track recent price differences for volatility adjustment.
        self.diff_history: List[float] = []
        self.max_history = 50
        
        # Base thresholds (in price units) for entry and exit.
        self.base_entry_threshold = 20.0
        self.base_exit_threshold  = 5.0
        
        # Maximum basket order quantity per trade (subject to underlying limits).
        self.max_basket_order = 20

        # Position limits (should not be exceeded).
        self.limit_basket    = 100
        self.limit_croiss    = 250
        self.limit_jams      = 350

    def load(self, data: dict) -> None:
        if data and "diff_history" in data:
            self.diff_history = data["diff_history"]
        else:
            self.diff_history = []

    def save(self) -> dict:
        return {"diff_history": self.diff_history}

    def get_mid_price(self, order_depth) -> float:
        """Compute a simple mid–price from the best bid and best ask."""
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return None
        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        return (best_bid + best_ask) / 2.0

    def aggregate_liquidity(self, prices: Dict[float, int], desired_qty: int, side: str) -> (int, float):
        """
        Aggregate liquidity over multiple price levels.
        For side == "bid": prices are sorted descending.
        For side == "ask": prices are sorted ascending.
        Returns (executable_qty, worst_price) where worst_price is the price at which the
        cumulative volume reaches at least desired_qty.
        """
        sorted_prices = sorted(prices.keys(), reverse=(side=="bid"))
        agg_qty = 0
        worst_price = None
        for price in sorted_prices:
            # For sell orders in the order book the volumes are negative so take abs.
            vol = abs(prices[price])
            agg_qty += vol
            worst_price = price
            if agg_qty >= desired_qty:
                return desired_qty, worst_price
        return agg_qty, worst_price  # may be less than desired_qty

    def adjust_order_for_positions(self, product: str, desired_qty: int, current_pos: int, limit: int, side: str) -> int:
        """
        Adjusts the desired order quantity to respect the position limit.
          - For a buy order (side=="buy"), available capacity = limit - current_pos.
          - For a sell order (side=="sell"), available capacity = current_pos + limit.
        Returns the scaled order quantity.
        """
        if side == "buy":
            available = limit - current_pos
        else:
            available = current_pos + limit
        return min(desired_qty, max(0, available))

    def compute_dynamic_thresholds(self):
        """
        Computes effective thresholds scaled by the volatility of diff.
        If volatility is high, thresholds widen.
        """
        if len(self.diff_history) < 2:
            return self.base_entry_threshold, self.base_exit_threshold
        vol = np.std(self.diff_history)
        factor = 1 + (vol / 20.0)  # adjust denominator as needed
        return self.base_entry_threshold * factor, self.base_exit_threshold * factor

    def run_strategy(self, state) -> List['Order']:
        """
        Computes the price difference between PICNIC_BASKET2 and its synthetic value,
        then enters or partially exits positions accordingly.
        
        Order execution aggregates multiple liquidity levels and scales orders against
        current position limits.
        """
        orders: List[Order] = []
        # Ensure required markets are available.
        for sym in ["PICNIC_BASKET2", "CROISSANTS", "JAMS"]:
            if sym not in state.order_depths:
                return orders

        # Get current positions.
        pos_basket = state.position.get("PICNIC_BASKET2", 0)
        pos_croiss = state.position.get("CROISSANTS", 0)
        pos_jams   = state.position.get("JAMS", 0)
        
        # Obtain order depths.
        od_basket   = state.order_depths["PICNIC_BASKET2"]
        od_croiss   = state.order_depths["CROISSANTS"]
        od_jams     = state.order_depths["JAMS"]

        # Compute mid–prices.
        mp_basket = self.get_mid_price(od_basket)
        mp_croiss = self.get_mid_price(od_croiss)
        mp_jams   = self.get_mid_price(od_jams)
        if mp_basket is None or mp_croiss is None or mp_jams is None:
            return orders

        # Synthetic price = 4 * CROISSANTS + 2 * JAMS
        synthetic_price = 4 * mp_croiss + 2 * mp_jams
        diff = mp_basket - synthetic_price
        self.diff_history.append(diff)
        if len(self.diff_history) > self.max_history:
            self.diff_history = self.diff_history[-self.max_history:]

        # Compute dynamic thresholds.
        effective_entry, effective_exit = self.compute_dynamic_thresholds()
        # For clarity, when we are long the basket (bought because it was cheap), entry was at -effective_entry,
        # and exit threshold is -effective_exit. For a short basket, entry was at +effective_entry, exit at +effective_exit.
        
        # ----------------------------------------------
        # PART 1: Partial Exit / Scale-Out logic.
        # ----------------------------------------------
        # For a long basket (pos_basket > 0), we entered when diff <= -effective_entry.
        # To exit gradually, if diff has risen toward -effective_exit (i.e., is less negative), we exit a portion.
        if pos_basket > 0 and diff > -effective_exit and diff < -effective_entry:
            # Scale factor: 0 at entry level, 1 at exit threshold.
            # fraction_exit = (diff - (-effective_entry)) / ((-effective_exit) - (-effective_entry))
            fraction_exit = (diff + effective_entry) / (effective_entry - effective_exit)
            fraction_exit = min(max(fraction_exit, 0), 1)
            qty_to_exit = int(max(1, fraction_exit * pos_basket))
            # --- Check liquidity across multiple levels for basket sell (using bid side) ---
            desired_qty = qty_to_exit
            agg_qty, worst_price_basket = self.aggregate_liquidity(od_basket.buy_orders, desired_qty, "bid")
            if agg_qty < desired_qty:
                qty_to_exit = agg_qty  # scale down if not enough volume

            # Check basket position limit (we are reducing a long position, so no worry of breaching limit).
            if qty_to_exit > 0 and worst_price_basket is not None:
                orders.append(Order("PICNIC_BASKET2", worst_price_basket, -qty_to_exit))
                # For underlying: we originally shorted 4 CROISSANTS and 2 JAMS per basket.
                # Now we partially close: buy back underlying.
                # For CROISSANTS, use sell side liquidity.
                agg_qty_c, worst_price_c = self.aggregate_liquidity(od_croiss.sell_orders, qty_to_exit * 4, "ask")
                agg_qty_j, worst_price_j = self.aggregate_liquidity(od_jams.sell_orders, qty_to_exit * 2, "ask")
                # Scale order sizes to available liquidity.
                actual_qty_c = (qty_to_exit * 4) if agg_qty_c >= qty_to_exit * 4 else agg_qty_c
                actual_qty_j = (qty_to_exit * 2) if agg_qty_j >= qty_to_exit * 2 else agg_qty_j
                if worst_price_c is not None and actual_qty_c > 0:
                    orders.append(Order("CROISSANTS", worst_price_c, actual_qty_c))
                if worst_price_j is not None and actual_qty_j > 0:
                    orders.append(Order("JAMS", worst_price_j, actual_qty_j))
            return orders

        elif pos_basket < 0 and diff < effective_exit and diff > effective_entry:
            # For a short basket position (entered when diff >= effective_entry),
            # we want to exit gradually as diff falls toward effective_exit.
            fraction_exit = (effective_entry - diff) / (effective_entry - effective_exit)
            fraction_exit = min(max(fraction_exit, 0), 1)
            qty_to_exit = int(max(1, fraction_exit * abs(pos_basket)))
            desired_qty = qty_to_exit
            agg_qty, worst_price_basket = self.aggregate_liquidity(od_basket.sell_orders, desired_qty, "ask")
            if agg_qty < desired_qty:
                qty_to_exit = agg_qty
            if qty_to_exit > 0 and worst_price_basket is not None:
                orders.append(Order("PICNIC_BASKET2", worst_price_basket, qty_to_exit))
                # For underlying: for a short basket, we went long underlying.
                # To unwind, we sell underlying.
                agg_qty_c, worst_price_c = self.aggregate_liquidity(od_croiss.buy_orders, qty_to_exit * 4, "bid")
                agg_qty_j, worst_price_j = self.aggregate_liquidity(od_jams.buy_orders, qty_to_exit * 2, "bid")
                actual_qty_c = (qty_to_exit * 4) if agg_qty_c >= qty_to_exit * 4 else agg_qty_c
                actual_qty_j = (qty_to_exit * 2) if agg_qty_j >= qty_to_exit * 2 else agg_qty_j
                if worst_price_c is not None and actual_qty_c > 0:
                    orders.append(Order("CROISSANTS", worst_price_c, -actual_qty_c))
                if worst_price_j is not None and actual_qty_j > 0:
                    orders.append(Order("JAMS", worst_price_j, -actual_qty_j))
            return orders

        # ----------------------------------------------
        # PART 2: New Entry logic (flat position)
        # ----------------------------------------------
        if pos_basket == 0:
            # Determine available capacity for new positions.
            # For basket, ensure we don't exceed the limit.
            avail_basket_buy = self.limit_basket  # for a long basket order
            avail_basket_sell = self.limit_basket  # for a short basket order
            
            # Underlying available capacity:
            avail_croiss_buy = self.limit_croiss - state.position.get("CROISSANTS", 0)
            avail_croiss_sell = state.position.get("CROISSANTS", 0) + self.limit_croiss
            avail_jams_buy   = self.limit_jams - state.position.get("JAMS", 0)
            avail_jams_sell  = state.position.get("JAMS", 0) + self.limit_jams

            # For a long basket entry, we expect diff to be very negative.
            if diff < -effective_entry:
                desired_qty = self.max_basket_order
                # Adjust for basket position limit.
                desired_qty = self.adjust_order_for_positions("PICNIC_BASKET2", desired_qty, state.position.get("PICNIC_BASKET2", 0), self.limit_basket, "buy")
                # Check liquidity on basket sell side (we want to buy at the ask).
                available_basket, worst_price_basket = self.aggregate_liquidity(od_basket.sell_orders, desired_qty, "ask")
                if available_basket <= 0 or worst_price_basket is None:
                    return orders
                qty_to_trade = min(desired_qty, available_basket)
                # Underlying: we need to short 4 CROISSANTS and 2 JAMS per basket.
                available_croiss, worst_price_c = self.aggregate_liquidity(od_croiss.buy_orders, qty_to_trade * 4, "bid")
                available_jams, worst_price_j   = self.aggregate_liquidity(od_jams.buy_orders, qty_to_trade * 2, "bid")
                qty_possible = qty_to_trade
                # Scale down if liquidity in underlying is insufficient.
                if available_croiss < qty_to_trade * 4 or available_jams < qty_to_trade * 2:
                    qty_possible = min(available_croiss // 4, available_jams // 2)
                # Also adjust for underlying position limits.
                qty_possible = min(qty_possible,
                                   self.adjust_order_for_positions("CROISSANTS", qty_possible * 4, state.position.get("CROISSANTS", 0), self.limit_croiss, "sell") // 4,
                                   self.adjust_order_for_positions("JAMS", qty_possible * 2, state.position.get("JAMS", 0), self.limit_jams, "sell") // 2)
                if qty_possible > 0:
                    orders.append(Order("PICNIC_BASKET2", worst_price_basket, qty_possible))
                    orders.append(Order("CROISSANTS", worst_price_c, -qty_possible * 4))
                    orders.append(Order("JAMS", worst_price_j, -qty_possible * 2))
                return orders

            # For a short basket entry, we expect diff to be very positive.
            elif diff > effective_entry:
                desired_qty = self.max_basket_order
                desired_qty = self.adjust_order_for_positions("PICNIC_BASKET2", desired_qty, state.position.get("PICNIC_BASKET2", 0), self.limit_basket, "sell")
                available_basket, worst_price_basket = self.aggregate_liquidity(od_basket.buy_orders, desired_qty, "bid")
                if available_basket <= 0 or worst_price_basket is None:
                    return orders
                qty_to_trade = min(desired_qty, available_basket)
                available_croiss, worst_price_c = self.aggregate_liquidity(od_croiss.sell_orders, qty_to_trade * 4, "ask")
                available_jams, worst_price_j   = self.aggregate_liquidity(od_jams.sell_orders, qty_to_trade * 2, "ask")
                qty_possible = qty_to_trade
                if available_croiss < qty_to_trade * 4 or available_jams < qty_to_trade * 2:
                    qty_possible = min(available_croiss // 4, available_jams // 2)
                qty_possible = min(qty_possible,
                                   self.adjust_order_for_positions("CROISSANTS", qty_possible * 4, state.position.get("CROISSANTS", 0), self.limit_croiss, "buy") // 4,
                                   self.adjust_order_for_positions("JAMS", qty_possible * 2, state.position.get("JAMS", 0), self.limit_jams, "buy") // 2)
                if qty_possible > 0:
                    orders.append(Order("PICNIC_BASKET2", worst_price_basket, -qty_possible))
                    orders.append(Order("CROISSANTS", worst_price_c, qty_possible * 4))
                    orders.append(Order("JAMS", worst_price_j, qty_possible * 2))
                return orders

        # If no entry or partial exit criteria are met, do nothing.
        return orders

class DjembeStrat:
    # hyperparameters to tune:
    # window - 100
    # short_window - 20
    # k

    #(100,20) = 3.2
    #(100, 30), 1.9

    def __init__(self) -> None:
        self.name = "DjembeStrat"
        self.price_history: List[float] = []
        
    def load(self, data: dict) -> None:
        if data and "price_history" in data: 
            self.price_history = data["price_history"]
        else:
            self.price_history = []
    
    def save(self) -> dict:
        return {"price_history": self.price_history}
    
    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int, timestmap: int) -> List[Order]:
        orders: List[Order] = []
        buy_orders = order_depth.buy_orders
        sell_orders = order_depth.sell_orders

        # determine current price (mid_price)
        best_bid = max(buy_orders.keys()) if buy_orders else None
        best_ask = min(sell_orders.keys()) if sell_orders else None

        if best_bid is not None and best_ask is not None:
            current_price = (best_bid + best_ask) / 2.0
        else: 
            current_price = 10.0 
        
        # update price history 
        # hyperparameter = window
        self.price_history.append(current_price)
        window = 100
        if len(self.price_history) > window:
            self.price_history = self.price_history[-window:]

        # Calculate moving avg
        # hyperparameter = short_window
        short_window = 30
        short_ma = sum(self.price_history[-short_window:]) / short_window if len(self.price_history) >= short_window else current_price
        long_ma = sum(self.price_history) / len(self.price_history) if self.price_history else current_price
        trend_signal = short_ma - long_ma 

        # Calculate volatility
        if len(self.price_history) > 1:
            returns = [p2 - p1 for p1, p2 in zip(self.price_history[:-1], self.price_history[1:])]
            volatility = statistics.pstdev(returns) if len(returns) > 1 else 1
        else:
            volatility = 1

        # hyperparameter k = 1.5, 1.9
        k = 3.2 # factor for adaptive threshold
        adaptive_threshold = k * volatility
        tick_size = 1
        spread_adjustment = volatility + tick_size
        quantity = 5  # base order size

        # decide which strategy branch to use
        if abs(trend_signal) > adaptive_threshold:
            # momentum strat
            if trend_signal > 0: # if price is trending up
                bid_price = int(best_bid) if best_bid is not None else int(current_price)
                max_buy = min(quantity, position_limit - position)
                if max_buy > 0: 
                    orders.append(Order(product, bid_price, max_buy))
            else: # if price is trending down
                ask_price = int(best_ask) if best_ask is not None else int(current_price)
                max_sell = min(quantity, position + position_limit)
                if max_sell > 0:
                    orders.append(Order(product, ask_price, -max_sell))

        else:
            # Mean reversion / Market making approach.
            deviation = current_price - long_ma
            alpha = 0.4
            if abs(deviation) > adaptive_threshold:
                if deviation > 0:
                    ask_price = int(current_price + spread_adjustment - alpha * deviation)
                    bid_price = int(current_price - spread_adjustment)
                    max_sell = min(quantity + int(deviation), position + position_limit)
                    if max_sell > 0:
                        orders.append(Order(product, ask_price, -max_sell))
                else:
                    bid_price = int(current_price - spread_adjustment + alpha * (-deviation))
                    ask_price = int(current_price + spread_adjustment)
                    max_buy = min(quantity + int(-deviation), position_limit - position)
                    if max_buy > 0:
                        orders.append(Order(product, bid_price, max_buy))
            
            # Mean reversion / Market making approach.
            else:
                total_bid_vol = sum(buy_orders.values())
                total_ask_vol = -sum(sell_orders.values())
                imbalance = 0
                if (total_bid_vol + total_ask_vol) > 0:
                    imbalance = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol)
                if imbalance > 0.5:
                    ask_price = int(current_price + spread_adjustment + tick_size)
                    bid_price = int(current_price - spread_adjustment)
                elif imbalance < -0.5:
                    ask_price = int(current_price + spread_adjustment)
                    bid_price = int(current_price - spread_adjustment - tick_size)
                else:
                    ask_price = int(current_price + spread_adjustment)
                    bid_price = int(current_price - spread_adjustment)
                max_buy = min(quantity, position_limit - position)
                max_sell = min(quantity, position + position_limit)
                if max_buy > 0:
                    orders.append(Order(product, bid_price, max_buy))
                if max_sell > 0:
                    orders.append(Order(product, ask_price, -max_sell))
        return orders

class Trader:
    def __init__(self) -> None:
        # Product-specific strategies.
        self.product_strategies: Dict[str, Any] = {
            "RAINFOREST_RESIN": RainforestResinStrat(),
            "KELP": KelpStrat(),
            "SQUID_INK": SquidInkStrat(),
            "DJEMBES": DjembeStrat(),
        }
        # Arbitrage strategies (not tied to a single product).
        # Use arbDynamic for the picnic arbitrage (only trades PICNIC_BASKET1 based on DJEMBES volatility).
        # self.arb_strategies: Dict[str, Any] = {
        #     "PICNIC_ARB": arbDynamic(),
        # }
        # Add the new PICNIC_BASKET2 arbitrage strategy.
        # self.arb_strategies["PICNIC_BASKET2_ARB"] = PicnicBasket2PairTrader()

        # Updated position limits.
        self.position_limits: Dict[str, int] = {
            "RAINFOREST_RESIN": 50,
            "KELP": 50,
            "SQUID_INK": 50,
            # "PICNIC_BASKET1": 60,
            # "PICNIC_BASKET2": 100,
            "CROISSANTS": 250,
            "JAMS": 350,
            "DJEMBES": 60,
        }

    def run(self, state: TradingState):
        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))

        if state.traderData and state.traderData.strip():
            trader_object = jsonpickle.decode(state.traderData)
        else:
            trader_object = {}

        result: Dict[str, List[Order]] = {}

        # Process the per-product strategies.
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            current_position = state.position.get(product, 0)
            position_limit = self.position_limits.get(product, 50)
            orders: List[Order] = []

            strategy = self.product_strategies.get(product)
            if strategy is None:
                continue

            strat_data_key = f"{product}_{strategy.name}"
            if strat_data_key in trader_object:
                strategy.load(trader_object[strat_data_key])

            new_orders = strategy.run_strategy(product, order_depth, current_position, position_limit, state.timestamp)
            orders.extend(new_orders)
            result[product] = orders

            trader_object[strat_data_key] = strategy.save()

        # Process the arbitrage strategies.
        # arb_result: Dict[str, List[Order]] = {}
        # for arb_name, arb_strategy in self.arb_strategies.items():
        #     if arb_strategy is None:
        #         continue
        #     strat_data_key = f"{arb_name}_{arb_strategy.name}"
        #     if strat_data_key in trader_object:
        #         arb_strategy.load(trader_object[strat_data_key])

        #     new_orders = arb_strategy.run_strategy(state)
        #     for order in new_orders:
        #         arb_result.setdefault(order.symbol, []).append(order)

        #     trader_object[strat_data_key] = arb_strategy.save()

        # # Merge arbitrage orders into the final result.
        # for symbol, orders_list in arb_result.items():
        #     if symbol in result:
        #         result[symbol].extend(orders_list)
        #     else:
        #         result[symbol] = orders_list

        conversions = 0
        new_trader_data = jsonpickle.encode(trader_object)
        logger.flush(state, result, conversions, new_trader_data)
        return result, conversions, new_trader_data