import string
import statistics
import json
import jsonpickle
from datamodel import OrderDepth, UserId, TradingState, Order, Symbol, ProsperityEncoder, Listing, Trade, Observation
from typing import List, Dict, Any
from collections import deque
import numpy as np

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

class FourierStrat:
    """
    A revised FourierStrat that:
      1) Reconstructs a forecast price via Fourier (same as before).
      2) Tracks mid-price changes from the last tick.
      3) Computes a rolling Z-score of recent mid-price differences.
      4) Trades *only if* the Fourier signal and the high |Z-score| indicate a likely snap-back (reversion).
    """

    def __init__(self) -> None:
        self.name = "FourierStrat"
        # Precalculated Fourier coefficients for each product (same as your original)
        self.coeffs = {
            "RAINFOREST_RESIN": {
                "freqs": [3.3333e-07, 6.6667e-07, 1.33333e-06, 1.66667e-06, 2e-06],
                "amps": [33.34138, 24.41806, 13.53225, 10.45029, 9.06918],
                "phases": [1.9551022, 2.52378785, 0.58284677, 1.53594377, 1.40839279],
                "mean": 10000
            },
            "KELP": {
                "freqs": [3.3333e-07, 6.6667e-07, 2e-06, 1.66667e-06, 3e-06],
                "amps": [166550.54165, 103999.2035, 58297.17692, 52297.06026, 45428.60863],
                "phases": [1.78312627, 1.90075364, 1.11510534, 2.17016315, 1.58262202],
                "mean": 2000
            },
            "SQUID_INK": {
                "freqs": [3.3333e-07, 6.6667e-07, 1.33333e-06, 1.66667e-06, 2e-06],
                "amps": [1000241.25709, 732541.88318, 405967.39994, 313508.62736, 272075.38086],
                "phases": [-1.9551022, -2.52378785, -0.58284677, -1.53594377, -1.40839279],
                "mean": 2000
            }
        }
        # ——— New state for difference-based reversion ———
        self.last_mid: Dict[str, float] = {}     # track last mid-price per product
        self.price_diffs: Dict[str, List[float]] = {}  # rolling diffs for each product
        self.max_window = 20                    # how many diffs to keep for rolling stats
        self.zscore_threshold = 1.5             # only trade if |zscore| >= this

        self.base_qty = 1
        self.threshold = 0.0

    def load(self, data: dict) -> None:
        """
        Reload saved memory variables, if any, for each product.
        Example structure in data:
            {
              "last_mid": {"RAINFOREST_RESIN": 9995.0, "KELP": ...},
              "price_diffs": {"RAINFOREST_RESIN": [..], "KELP": [...]}
            }
        """
        if data:
            self.last_mid = data.get("last_mid", {})
            self.price_diffs = data.get("price_diffs", {})

    def save(self) -> dict:
        """
        Save state so that next iteration can retrieve it via load().
        """
        return {
            "last_mid": self.last_mid,
            "price_diffs": self.price_diffs
        }

    def run_strategy(
        self,
        product: str,
        order_depth,
        position: int,
        position_limit: int,
        timestamp: int
    ) -> List:
        """
        1) Reconstruct forecast via Fourier (same as before).
        2) Compute mid. Then compute and store the price difference from last iteration.
        3) Compute z-score of that new difference using rolling diffs.
        4) If mid is below the Fourier forecast *and* the z-score is strongly negative
           => buy for reversion upward.
           If mid is above the Fourier forecast *and* the z-score is strongly positive
           => sell for reversion downward.
        """
        # If no Fourier coefficients for product, skip
        if product not in self.coeffs:
            return []

        # (A) Fourier reconstruction as usual
        c = self.coeffs[product]
        freqs, amps, phases, mean_val = c["freqs"], c["amps"], c["phases"], c["mean"]
        t = timestamp
        reconstruction = mean_val
        for f, a, ph in zip(freqs, amps, phases):
            reconstruction += a * np.cos(2 * np.pi * f * t + ph)

        # (B) Current mid-price from order_depth
        if order_depth.buy_orders and order_depth.sell_orders:
            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid = (best_bid + best_ask) / 2.0
        else:
            # fallback if not enough data
            mid = reconstruction

        # (C) Track rolling diffs and compute z-score
        #  Initialize if not in dictionary
        if product not in self.last_mid:
            self.last_mid[product] = mid
        if product not in self.price_diffs:
            self.price_diffs[product] = []

        new_diff = mid - self.last_mid[product]
        self.last_mid[product] = mid  # update for next time

        # store new_diff
        diffs_list = self.price_diffs[product]
        diffs_list.append(new_diff)
        if len(diffs_list) > self.max_window:
            diffs_list.pop(0)

        # compute z-score for the *latest* difference
        if len(diffs_list) >= 2:
            avg_diff = statistics.mean(diffs_list)
            std_diff = statistics.pstdev(diffs_list)  # population stdev or sample stdev
            if std_diff > 1e-9:
                zscore = (new_diff - avg_diff) / std_diff
            else:
                zscore = 0.0
        else:
            zscore = 0.0

        # (D) Decide whether to trade
        orders = []
        # We want to see if the mid < reconstruction => reversion up,
        # but also confirm that the last price move (diff) was strongly negative (zscore < -threshold).
        # That often signals an “overshoot” downward that we want to fade.

        # Similarly, if mid > reconstruction => reversion down,
        # confirm that the last price move was strongly positive (zscore > threshold).

        # Only trade if we have capacity
        if mid < reconstruction and zscore < -self.zscore_threshold and position < position_limit:
            diff = reconstruction - mid
            # quantity scaled by difference (like your older approach)
            qty = int(min(position_limit - position, max(1, int(self.base_qty * diff))))
            orders.append(Order(product, round(mid), qty))

        elif mid > reconstruction and zscore > self.zscore_threshold and position > -position_limit:
            diff = mid - reconstruction
            qty = int(min(position + position_limit, max(1, int(self.base_qty * diff))))
            orders.append(Order(product, round(mid), -qty))

        return orders


# old resin logic - clearly fucked something up 

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

    # Add load and save methods to avoid attribute error.
    def load(self, data: dict) -> None:
        # No persistent state to load for now.
        pass

    def save(self) -> dict:
        # Nothing is stored, return an empty dict.
        return {}

    def adjust_order_size(self, base_quantity: int, volatility: float) -> int:
        # Adjust order size based on volatility (hard-coded boundaries).
        if volatility > 5:
            adjusted = max(self.min_order_size, int(base_quantity * 0.5))
        elif volatility < 1:
            adjusted = min(self.max_order_size, int(base_quantity * 1.5))
        else:
            # Linear interpolation between extremes: scale decreases from 1.0 to 0.5
            scale = 1 - ((volatility - 1) / 4) * 0.5
            adjusted = int(base_quantity * scale)
        return max(self.min_order_size, min(self.max_order_size, adjusted))

    def take_best_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        position: int,
        orders: List[Order],
        buy_order_volume: int,
        sell_order_volume: int
    ) -> (int, int):
        # Attempt to take orders if prices are favorable compared to the fair value ± take_width.
        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders.keys())
            best_ask_volume = -order_depth.sell_orders[best_ask]  # Sell volumes are negative.
            if best_ask <= self.fair_value - self.take_width:
                quantity = min(best_ask_volume, self.position_limit - position)
                if quantity > 0:
                    orders.append(Order(product, best_ask, quantity))
                    buy_order_volume += quantity
                    order_depth.sell_orders[best_ask] += quantity  # Reduce remaining volume.
                    if order_depth.sell_orders.get(best_ask) == 0:
                        del order_depth.sell_orders[best_ask]
        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders.keys())
            best_bid_volume = order_depth.buy_orders[best_bid]
            if best_bid >= self.fair_value + self.take_width:
                quantity = min(best_bid_volume, self.position_limit + position)
                if quantity > 0:
                    orders.append(Order(product, best_bid, -quantity))
                    sell_order_volume += quantity
                    order_depth.buy_orders[best_bid] -= quantity
                    if order_depth.buy_orders.get(best_bid) == 0:
                        del order_depth.buy_orders[best_bid]
        return buy_order_volume, sell_order_volume

    def take_orders(
        self, product: str, order_depth: OrderDepth, position: int
    ) -> (List[Order], int, int):
        orders: List[Order] = []
        buy_order_volume, sell_order_volume = 0, 0
        buy_order_volume, sell_order_volume = self.take_best_orders(
            product, order_depth, position, orders, buy_order_volume, sell_order_volume
        )
        return orders, buy_order_volume, sell_order_volume

    def clear_position_order(
        self,
        product: str,
        order_depth: OrderDepth,
        position: int,
        orders: List[Order],
        buy_order_volume: int,
        sell_order_volume: int
    ) -> (int, int):
        # Compute net position, then try to clear (offset) the position near the fair value.
        net_position = position + buy_order_volume - sell_order_volume
        fair_for_bid = round(self.fair_value - self.clear_width)
        fair_for_ask = round(self.fair_value + self.clear_width)
        buy_quantity = self.position_limit - (position + buy_order_volume)
        sell_quantity = self.position_limit + (position - sell_order_volume)
        if net_position > 0:
            clear_quantity = sum(vol for px, vol in order_depth.buy_orders.items() if px >= fair_for_ask)
            clear_quantity = min(clear_quantity, net_position)
            sent_quantity = min(sell_quantity, clear_quantity)
            if sent_quantity > 0:
                orders.append(Order(product, fair_for_ask, -abs(sent_quantity)))
                sell_order_volume += abs(sent_quantity)
        if net_position < 0:
            clear_quantity = sum(abs(vol) for px, vol in order_depth.sell_orders.items() if px <= fair_for_bid)
            clear_quantity = min(clear_quantity, abs(net_position))
            sent_quantity = min(buy_quantity, clear_quantity)
            if sent_quantity > 0:
                orders.append(Order(product, fair_for_bid, abs(sent_quantity)))
                buy_order_volume += abs(sent_quantity)
        return buy_order_volume, sell_order_volume

    def clear_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        position: int,
        buy_order_volume: int,
        sell_order_volume: int
    ) -> (List[Order], int, int):
        orders: List[Order] = []
        buy_order_volume, sell_order_volume = self.clear_position_order(
            product, order_depth, position, orders, buy_order_volume, sell_order_volume
        )
        return orders, buy_order_volume, sell_order_volume

    def market_make(
        self,
        product: str,
        orders: List[Order],
        bid: float,
        ask: float,
        position: int,
        buy_order_volume: int,
        sell_order_volume: int
    ) -> (int, int):
        # Post orders to quote the market around the bid and ask.
        buy_quantity = self.position_limit - (position + buy_order_volume)
        if buy_quantity > 0:
            orders.append(Order(product, round(bid), buy_quantity))
        sell_quantity = self.position_limit + (position - sell_order_volume)
        if sell_quantity > 0:
            orders.append(Order(product, round(ask), -sell_quantity))
        return buy_order_volume, sell_order_volume

    def make_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        position: int,
        buy_order_volume: int,
        sell_order_volume: int
    ) -> (List[Order], int, int):
        orders: List[Order] = []
        # Determine prices using the edges.
        asks_above = [p for p in order_depth.sell_orders if p > self.fair_value + self.disregard_edge]
        bids_below = [p for p in order_depth.buy_orders if p < self.fair_value - self.disregard_edge]
        if asks_above:
            best_ask_above = min(asks_above)
        else:
            best_ask_above = None
        if bids_below:
            best_bid_below = max(bids_below)
        else:
            best_bid_below = None

        if best_ask_above is not None:
            if abs(best_ask_above - self.fair_value) <= self.join_edge:
                ask = best_ask_above
            else:
                ask = best_ask_above - 1
        else:
            ask = round(self.fair_value + self.default_edge)

        if best_bid_below is not None:
            if abs(self.fair_value - best_bid_below) <= self.join_edge:
                bid = best_bid_below
            else:
                bid = best_bid_below + 1
        else:
            bid = round(self.fair_value - self.default_edge)

        if position > self.soft_position_limit:
            ask -= 1
        elif position < -self.soft_position_limit:
            bid += 1

        self.market_make(product, orders, bid, ask, position, buy_order_volume, sell_order_volume)
        return orders, buy_order_volume, sell_order_volume

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int, timestamp: int) -> List[Order]:
        # In our hard-coded strategy, we use the fixed fair_value.
        # Step 1: Attempt to take favorable orders.
        a_orders, buy_vol, sell_vol = self.take_orders(product, order_depth, position)
        # Step 2: Clear any unwanted net position.
        c_orders, buy_vol, sell_vol = self.clear_orders(product, order_depth, position, buy_vol, sell_vol)
        # Step 3: Post market-making orders.
        base_qty = 20
        # As fair_value is fixed, price_vol will be 0; adjusted_qty is computed for completeness.
        price_vol = abs(self.fair_value - 10000)
        adjusted_qty = self.adjust_order_size(base_qty, price_vol)
        m_orders, _, _ = self.make_orders(product, order_depth, position, buy_vol, sell_vol)
        return a_orders + c_orders + m_orders

# check arbitrage - siagal
# simple arbitrage if there is market inefficiency where bid > ask or ask < bid
# for example, buy from the cheaper side and sell to the more expensive side
class checkArb:
    def __init__(self):
        # store any needed state for this strategy
        # here we only store a name for debugging or identification
        self.name = "checkArb" 

    def load(self, data: dict) -> None:
        # currently no stored state
        # this method is used to load any data saved by save() in previous iterations
        pass

    def save(self) -> dict:
        # currently nothing to save
        # returning an empty dict to comply with the pattern
        return {}

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int, timestamp: int) -> List[Order]:
        # run_strategy is called each iteration; it returns a list of orders to be executed
        orders: List[Order] = []  # create an empty list of orders

        # get the best ask if available
        if len(order_depth.sell_orders) > 0:
            # the best ask is the lowest sell price
            best_ask = min(order_depth.sell_orders.keys())  # find min price
            best_ask_volume = -order_depth.sell_orders[best_ask]  # volume is negative
        else:
            best_ask = None
            best_ask_volume = 0

        # get the best bid if available
        if len(order_depth.buy_orders) > 0:
            # the best bid is the highest buy price
            best_bid = max(order_depth.buy_orders.keys())
            best_bid_volume = order_depth.buy_orders[best_bid]
        else:
            best_bid = None
            best_bid_volume = 0

        # if we see a cross: best_bid > best_ask => arbitrage possibility
        if best_bid is not None and best_ask is not None and best_bid > best_ask:
            # figure out how many units we can buy without exceeding position limit
            can_buy = position_limit - position  # how many we can buy
            # figure out how many units we can sell without exceeding short side limit
            can_sell = position + position_limit  # how many we can sell
            # the quantity to trade is limited by volumes and our position constraints
            qty = min(best_bid_volume, best_ask_volume, can_buy, can_sell)
            if qty > 0:
                # buy at best_ask
                orders.append(Order(product, best_ask, qty))
                # sell at best_bid
                orders.append(Order(product, best_bid, -qty))

        # returns the list of orders (could be empty if no arbitrage found)
        return orders

class combinedSquidInkStrategy:
    def __init__(self):
        # store the name for debugging
        self.name = "combinedSquidInkStrategy"
        
        # create internal references to the sub-strategies
        self.lastImbVol_strat = lastImbVol()  
        self.momTrading_strat = momTrading()
        self.meanRev_strat = meanRev()
        self.bolBands_strat = bolBands()
        self.kelpStratTwo = KelpStratTwo()
        
        # you can store any needed state (like rolling volatility) here if you want
        # for example:
        self.high_vol_state = False  # just an example
    
    def load(self, data: Dict) -> None:
        # load sub-strategies if we saved them last iteration
        if data is not None:
            if "lastImbVol" in data:
                self.lastImbVol_strat.load(data["lastImbVol"])
            if "momTrading" in data:
                self.momTrading_strat.load(data["momTrading"])
            if "meanRev" in data:
                self.meanRev_strat.load(data["meanRev"])
            if "bolBands" in data:
                self.meanRev_strat.load(data["bolBands"])
            # if "kelpStratTwo" in data:
            #     self.kelpStratTwo.load(data["KelpStratTwo"])
            
            # if we track a boolean or any additional state:
            self.high_vol_state = data.get("high_vol_state", False)
    
    def save(self) -> Dict:
        # save sub-strategies + our own state
        return {
            "lastImbVol": self.lastImbVol_strat.save(),
            "momTrading": self.momTrading_strat.save(),
            "meanRev": self.meanRev_strat.save(),
            # "kelpStratTwo": self.kelpStratTwo.save(),

            "high_vol_state": self.high_vol_state
        }
    
    def is_high_vol_condition(self, state_timestamp: int) -> bool:
        """
        placeholder function to decide if we are in high volatility
        replace with your time-based or volatility-based logic
        e.g.: if state_timestamp > 1e8: return True
        or measure a rolling std somewhere
        """
        if state_timestamp > 49000:
            return True
        else:
            return False
    
    def run_strategy(self,
                     product: str,
                     order_depth: OrderDepth,
                     position: int,
                     position_limit: int,
                     state_timestamp: int  # pass in the simulation timestamp
                     ) -> List[Order]:
        """
        the main method that decides whether we are in high-vol or low-vol,
        then calls the appropriate sub-strategy's run_strategy to produce orders.
        note that if we decide 'high-vol', we combine orders from both lastImbVol and momTrading.
        if we decide 'low-vol', we just do meanRev.
        """
        orders: List[Order] = []
        
        # figure out if we are high vol or not
        # we store it in self.high_vol_state for reference
        self.high_vol_state = self.is_high_vol_condition(state_timestamp)
        
        if self.high_vol_state:
            # in high volatility => call lastImbVol and momTrading
            # high_vol_orders_1 = self.lastImbVol_strat.run_strategy(product, order_depth, position, position_limit)
            # we should adjust 'position' after these orders if we want to keep it accurate
            # or we can simply sum them up at the end in the main Trader's clamp logic
            # net1 = sum(o.quantity for o in high_vol_orders_1)
            # position_after_1 = position + net1
            
            high_vol_orders_1 = self.meanRev_strat.run_strategy(product, order_depth, position, position_limit)
            # # combine them
            orders.extend(high_vol_orders_1)
            # orders.extend(high_vol_orders_2)
        
        else:
            # in low volatility
            low_vol_orders = self.meanRev_strat.run_strategy(product, order_depth, position, position_limit)
            orders.extend(low_vol_orders)
        
        return orders

# last+im+v strategy
# a market making approach where orders are priced based on the latest trading price,
# then dynamically adjusted using both recent price volatility and order book imbalance
class lastImbVol:
    def __init__(self):
        self.name = "lastImbVol"         # Name for debugging purposes
        self.last_price = None           # Memory for the last trade price (or mid-price)
        self.vol_est = 1.0               # Initialize volatility estimate (works as the rolling volatility for SQUID_INK)
        self.alpha_vol = 0.2             # Smoothing factor used for volatility calculation
        
        # Parameters for the SQUID_INK strategy.
        # You can calibrate these values based on your risk or alpha preferences.
        self.params = {
            "SQUID_INK": {
                "volatility_scale": 1.0,  # Scale factor for the volatility-based spread adjustment.
                "min_order_size": 1,      # Minimum allowed order size.
                "max_order_size": 20      # Maximum allowed order size.
            }
        }
    
    def load(self, data: dict) -> None:
        """Reload saved memory variables."""
        if data is not None:
            self.last_price = data.get("last_price", None)
            self.vol_est = data.get("vol_est", 1.0)
    
    def save(self) -> dict:
        """Save state for use in the next iteration."""
        return {
            "last_price": self.last_price,
            "vol_est": self.vol_est
        }
    
    def adjust_order_size(self, base_quantity: int, volatility: float, min_size: int, max_size: int) -> int:
        """
        Adjust the order size inversely based on volatility.
        When volatility is high, reduce the order size; when volatility is low, increase the order size.
        The value is then clipped between min_size and max_size.
        """
        # A simple approach is to use an inverse relation with volatility.
        quantity = int(round(base_quantity / volatility))
        return max(min(quantity, max_size), min_size)
    
    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int) -> List[Order]:
        orders: List[Order] = []
        
        # --- Enhanced SQUID_INK strategy ---
        if product == "SQUID_INK":
            buy_orders = order_depth.buy_orders
            sell_orders = order_depth.sell_orders

            best_bid = max(buy_orders.keys()) if buy_orders else None
            best_ask = min(sell_orders.keys()) if sell_orders else None
            
            # Use the stored last_price or a default of 10.0 if not set
            last_price = self.last_price if self.last_price is not None else 10.0
            
            # 1) Compute the current mid-price
            if best_bid is not None and best_ask is not None:
                current_price = (best_bid + best_ask) / 2.0
            else:
                current_price = last_price
            
            # 2) Compute and smooth volatility (using the absolute change in price) and floor it at 0.5
            raw_volatility = abs(current_price - last_price)
            new_rolling_volatility = self.alpha_vol * raw_volatility + (1 - self.alpha_vol) * self.vol_est
            new_rolling_volatility = max(new_rolling_volatility, 0.5)
            
            # 3) Compute order imbalance
            total_bid_vol = sum(buy_orders.values())
            total_ask_vol = -sum(sell_orders.values())  # sell volumes are negative so negate them
            if (total_bid_vol + total_ask_vol) > 0:
                imbalance = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol)
            else:
                imbalance = 0
            
            # 4) Determine spread adjustment using the product’s volatility scale parameter.
            spread_adjustment = new_rolling_volatility * self.params[product]["volatility_scale"]
            
            # 5) Adjust bid and ask prices based on order imbalance
            if imbalance > 0.5:
                ask_price = current_price + (spread_adjustment + 0.5)
                bid_price = current_price - spread_adjustment
            elif imbalance < -0.5:
                ask_price = current_price + spread_adjustment
                bid_price = current_price - (spread_adjustment + 0.5)
            else:
                ask_price = current_price + spread_adjustment
                bid_price = current_price - spread_adjustment
            
            # 6) Determine order quantity using adaptive adjustment based on volatility
            base_quantity = 20
            min_size = self.params[product]["min_order_size"]
            max_size = self.params[product]["max_order_size"]
            quantity = self.adjust_order_size(base_quantity, new_rolling_volatility, min_size, max_size)
            
            # Respect position limits:
            max_buy = min(quantity, position_limit - position)  # how many units we can add to our long position
            max_sell = min(quantity, position_limit + position) # how many units we can reduce from our long position
            
            # Additional precaution: if market data is incomplete or the bid-ask spread is very wide, limit orders further.
            if best_bid is None or best_ask is None or (best_ask - best_bid) > 4 * spread_adjustment:
                max_buy = min(max_buy, 2)
                max_sell = min(max_sell, 2)
            
            # 7) Create orders for SQUID_INK using integer prices
            if max_buy > 0:
                orders.append(Order(product, int(bid_price), max_buy))
            if max_sell > 0:
                orders.append(Order(product, int(ask_price), -max_sell))
            
            # 8) Update state for next iteration
            self.last_price = current_price
            self.vol_est = new_rolling_volatility
        
        # --- Fallback default strategy for other products ---
        else:
            if order_depth.buy_orders:
                best_bid = max(order_depth.buy_orders.keys())
            else:
                best_bid = None
            if order_depth.sell_orders:
                best_ask = min(order_depth.sell_orders.keys())
            else:
                best_ask = None

            if self.last_price is not None:
                reference_price = self.last_price
            else:
                if best_bid is not None and best_ask is not None:
                    reference_price = (best_bid + best_ask) / 2.0
                else:
                    reference_price = 100  # fallback default

            if best_bid is not None and best_ask is not None:
                spread = best_ask - best_bid
            else:
                spread = 2

            self.vol_est = (1 - self.alpha_vol) * self.vol_est + self.alpha_vol * abs(spread)

            total_buys = sum(order_depth.buy_orders.values())
            total_sells = sum(-v for v in order_depth.sell_orders.values())
            if (total_buys + total_sells) > 0:
                imbalance = (total_buys - total_sells) / (total_buys + total_sells)
            else:
                imbalance = 0

            vol_offset = round(self.vol_est)
            im_offset = 1 if abs(imbalance) < 0.5 else 2
            combined_offset = vol_offset + im_offset

            can_buy = position_limit - position
            can_sell = position + position_limit

            if imbalance > 0.5:
                ask_price = reference_price + combined_offset + 1
                bid_price = reference_price - combined_offset
            elif imbalance < -0.5:
                ask_price = reference_price + combined_offset
                bid_price = reference_price - combined_offset - 1
            else:
                ask_price = reference_price + combined_offset
                bid_price = reference_price - combined_offset

            if can_buy > 0:
                buy_qty = min(can_buy, 3)  # small batch order
                orders.append(Order(product, round(bid_price), buy_qty))
            if can_sell > 0:
                sell_qty = min(can_sell, 3)
                orders.append(Order(product, round(ask_price), -sell_qty))

            self.last_price = reference_price
        
        return orders


# mean reversion approach
# trading strategy 
class meanRev:
    def __init__(self):
        self.name = "meanRev"
        self.last_midprice = None
        self.beta = -0.2  # negative for reversion

    def load(self, data: dict) -> None:
        # load last_midprice if we saved it
        if data is not None:
            self.last_midprice = data.get("last_midprice", None)

    def save(self) -> dict:
        # store last_midprice for next iteration
        return {
            "last_midprice": self.last_midprice
        }

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int) -> List[Order]:
        orders = []

        # find best bid and best ask
        if len(order_depth.buy_orders) > 0:
            best_bid = max(order_depth.buy_orders.keys())
        else:
            best_bid = None

        if len(order_depth.sell_orders) > 0:
            best_ask = min(order_depth.sell_orders.keys())
        else:
            best_ask = None

        # compute a mid price or fallback
        if best_bid is not None and best_ask is not None:
            mid = (best_bid + best_ask) / 2.0
        else:
            mid = self.last_midprice if self.last_midprice is not None else 100

        # if we have a last mid, do reversion logic
        if self.last_midprice is not None:
            returns = (mid - self.last_midprice) / self.last_midprice
            pred_ret = returns * self.beta
            fair_val = mid + mid * pred_ret
        else:
            fair_val = mid

        self.last_midprice = mid  # update

        # figure out how many we can buy or sell
        can_buy = position_limit - position
        can_sell = position + position_limit

        # if best_ask < fair_val => buy; if best_bid > fair_val => sell
        if best_ask is not None and best_ask < fair_val and can_buy > 0:
            qty = min(5, can_buy)
            orders.append(Order(product, best_ask, qty))

        if best_bid is not None and best_bid > fair_val and can_sell > 0:
            qty = min(5, can_sell)
            orders.append(Order(product, best_bid, -qty))

        return orders


# bollinger bands
class bolBands:
    def __init__(self):
        self.name = "bolBands"
        self.prices = []
        self.window_size = 10
        self.num_std = 2

    def load(self, data: dict) -> None:
        # if we saved a rolling list of prices, restore it
        if data is not None:
            self.prices = data.get("prices", [])

    def save(self) -> dict:
        # return the current list of rolling prices
        return {
            "prices": self.prices
        }

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int) -> List[Order]:
        orders = []
        if len(order_depth.buy_orders) > 0:
            best_bid = max(order_depth.buy_orders.keys())
        else:
            best_bid = None

        if len(order_depth.sell_orders) > 0:
            best_ask = min(order_depth.sell_orders.keys())
        else:
            best_ask = None

        # compute mid fallback
        if best_bid is not None and best_ask is not None:
            mid = (best_bid + best_ask) / 2.0
        else:
            mid = 100

        # store in rolling list
        self.prices.append(mid)
        if len(self.prices) > self.window_size:
            self.prices.pop(0)

        avg = sum(self.prices) / len(self.prices)
        variance = sum((p - avg) ** 2 for p in self.prices) / len(self.prices)
        std = variance ** 0.5

        upper_band = avg + self.num_std * std
        lower_band = avg - self.num_std * std

        can_buy = position_limit - position
        can_sell = position + position_limit

        # if mid < lower_band => buy, if mid > upper_band => sell
        if mid < lower_band and can_buy > 0 and best_ask is not None:
            qty = min(5, can_buy)
            orders.append(Order(product, best_ask, qty))
        elif mid > upper_band and can_sell > 0 and best_bid is not None:
            qty = min(5, can_sell)
            orders.append(Order(product, best_bid, -qty))

        return orders


# simple capture of bid-ask spread for stable items
class captureBidAskSpread:
    def __init__(self):
        self.name = "captureBidAskSpread"
        self.fair_value = 10000
        self.soft_position_limit = 10
        self.default_spread = 2

    def load(self, data: dict) -> None:
        # no stored data for now
        pass

    def save(self) -> dict:
        # no data to save
        return {}

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int) -> List[Order]:
        # a simple approach for stable products
        orders = []
        can_buy = position_limit - position
        can_sell = position + position_limit

        offset = self.default_spread
        # if position is large, shift quotes
        if position > self.soft_position_limit:
            ask_price = self.fair_value + offset - 1
            bid_price = self.fair_value - offset
        elif position < -self.soft_position_limit:
            ask_price = self.fair_value + offset
            bid_price = self.fair_value - offset + 1
        else:
            ask_price = self.fair_value + offset
            bid_price = self.fair_value - offset

        # place partial orders
        if can_buy > 0:
            orders.append(Order(product, ask_price - (offset * 2), can_buy // 2))
        if can_sell > 0:
            orders.append(Order(product, bid_price + (offset * 2), -(can_sell // 2)))

        return orders


# dynamic quoting strategy
class dynamicQuoting:
    def __init__(self):
        self.name = "dynamicQuoting"
        self.rolling_spreads = []
        self.window_size = 5
        self.alpha = 0.3
        self.current_spread_est = 2.0

    def load(self, data: dict) -> None:
        if data is not None:
            self.current_spread_est = data.get("current_spread_est", 2.0)

    def save(self) -> dict:
        # store current_spread_est
        return {
            "current_spread_est": self.current_spread_est
        }

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int) -> List[Order]:
        orders = []
        # find best_bid and best_ask
        if len(order_depth.buy_orders) > 0 and len(order_depth.sell_orders) > 0:
            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            spread = best_ask - best_bid
        else:
            best_bid = None
            best_ask = None
            spread = self.current_spread_est

        # smoothing for spread
        self.current_spread_est = (1 - self.alpha) * self.current_spread_est + self.alpha * spread

        if best_bid is not None and best_ask is not None:
            mid = (best_bid + best_ask) / 2.0
        else:
            mid = 10000  # fallback if no data

        can_buy = position_limit - position
        can_sell = position + position_limit
        half_spread = self.current_spread_est / 2.0

        # place buy if we have capacity
        if can_buy > 0:
            buy_price = round(mid - half_spread)
            orders.append(Order(product, buy_price, min(5, can_buy)))
        # place sell if we have capacity
        if can_sell > 0:
            sell_price = round(mid + half_spread)
            orders.append(Order(product, sell_price, -min(5, can_sell)))

        return orders


# position tracking
class positionTracking:
    def __init__(self):
        self.name = "positionTracking"
        self.window = deque()
        self.window_size = 10

    def load(self, data: dict) -> None:
        # if we saved pinned data, load it
        if data is not None and "window" in data:
            self.window = deque(data["window"], maxlen=self.window_size)

    def save(self) -> dict:
        # store current window
        return {
            "window": list(self.window)
        }

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int) -> List[Order]:
        orders = []
        # pinned => if abs(position) >= position_limit
        pinned = (abs(position) >= position_limit)
        self.window.append(pinned)
        if len(self.window) > self.window_size:
            self.window.popleft()

        fraction_liquidate = 0.0
        pinned_count = sum(self.window)
        if pinned_count > self.window_size / 2:
            fraction_liquidate = 0.5

        if fraction_liquidate > 0:
            # if pinned a lot => forcibly liquidate half
            if position > 0:
                if len(order_depth.buy_orders) > 0:
                    best_bid = max(order_depth.buy_orders.keys())
                    vol = int(abs(position) * fraction_liquidate) # -> vol is volume
                    orders.append(Order(product, best_bid, -vol))
            elif position < 0:
                if len(order_depth.sell_orders) > 0:
                    best_ask = min(order_depth.sell_orders.keys())
                    vol = int(abs(position) * fraction_liquidate) # -> vol is volume
                    orders.append(Order(product, best_ask, vol))

        return orders


# momentum trading
class momTrading:
    def __init__(self, alpha=0.3, k=1.5, vol_threshold=1.0, base_quantity=3, position_limit=20, max_history=20, long_bias=0.7):
        self.name = "momTrading"
        self.alpha = alpha
        self.k = k
        self.vol_threshold = vol_threshold
        self.base_quantity = base_quantity
        self.position_limit = position_limit
        self.max_history = max_history
        self.long_bias = long_bias
        self.product_data = {}

    def load(self, data: dict) -> None:
        if data:
            self.product_data = data.get("product_data", {})

    def save(self) -> dict:
        return {
            "product_data": self.product_data
        }

    def get_mid_price(self, order_depth) -> float:
        if order_depth.buy_orders and order_depth.sell_orders:
            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            return (best_bid + best_ask) / 2.0
        return 100.0  # Fallback value

    def run_strategy(self, product: str, order_depth, position: int, timestamp: int) -> List:
        if product not in self.product_data:
            self.product_data[product] = {"history": [], "fair_value": self.get_mid_price(order_depth)}

        prod_data = self.product_data[product]
        current_price = self.get_mid_price(order_depth)
        history = prod_data["history"]

        # Update history
        history.append(current_price)
        if len(history) > self.max_history:
            history = history[-self.max_history:]
        prod_data["history"] = history

        # Update fair value using EMA
        prev_fv = prod_data["fair_value"]
        fair_value = self.alpha * current_price + (1 - self.alpha) * prev_fv
        prod_data["fair_value"] = fair_value

        # Compute volatility
        if len(history) > 1:
            try:
                volatility = statistics.stdev(history)
            except:
                volatility = abs(history[-1] - history[-2])
        else:
            volatility = 0.0

        # Compute bounds and SMA
        lower_bound = fair_value - self.k * volatility
        upper_bound = fair_value + self.k * volatility
        sma = np.mean(history)
        bullish_trend = current_price > sma

        # Dynamic size
        if volatility > 0:
            dynamic_factor = abs(current_price - fair_value) / volatility
        else:
            dynamic_factor = 1
        dynamic_size = int(min(self.position_limit, self.base_quantity * dynamic_factor))
        if dynamic_size < 1:
            dynamic_size = 1

        orders = []
        can_buy = self.position_limit - position
        can_sell = position + self.position_limit

        # Mean reversion mode
        if volatility < self.vol_threshold:
            if current_price < lower_bound and can_buy > 0:
                best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else int(current_price)
                qty = min(dynamic_size, can_buy)
                orders.append(Order(product, best_ask, qty))
            elif current_price > upper_bound and can_sell > 0:
                best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else int(current_price)
                qty = min(dynamic_size, can_sell)
                orders.append(Order(product, best_bid, -qty))
        else:
            # Trend-following mode
            if bullish_trend and can_buy > 0:
                best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else int(current_price)
                qty = min(int(dynamic_size * self.long_bias), can_buy)
                orders.append(Order(product, best_ask, qty))
            elif not bullish_trend and can_sell > 0:
                best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else int(current_price)
                qty = min(dynamic_size, can_sell)
                orders.append(Order(product, best_bid, -qty))

        return orders



    def __init__(self):
        self.name = "checkSeasonSquidInk"
        self.prices = []
        self.window_size = 10
        self.vol_threshold = 10 # is volatility, but is a constant threshold

    def load(self, data: dict) -> None:
        if data is not None:
            self.prices = data.get("prices", [])

    def save(self) -> dict:
        return {
            "prices": self.prices
        }

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int) -> List[Order]:
        orders = []
        # compute mid
        if len(order_depth.buy_orders) > 0 and len(order_depth.sell_orders) > 0:
            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid = (best_bid + best_ask) / 2.0
        else:
            mid = 100

        self.prices.append(mid)
        if len(self.prices) > self.window_size:
            self.prices.pop(0)

        # compute std if we have at least 2 data points
        if len(self.prices) > 1:
            avg = sum(self.prices) / len(self.prices)
            variance = sum((p - avg) ** 2 for p in self.prices) / len(self.prices)
            std = variance ** 0.5
        else:
            std = 1

        can_buy = position_limit - position
        can_sell = position + position_limit

        # if std above threshold => momentum approach
        # Volatility increases → Spread widens
        # Volatility decreases → Spread tightens
        if std > self.vol_threshold:
            if mid > avg and can_buy > 0:
                qty = min(3, can_buy)
                if len(order_depth.sell_orders) > 0:
                    best_ask = min(order_depth.sell_orders.keys())
                    orders.append(Order(product, best_ask, qty))
            elif mid < avg and can_sell > 0:
                qty = min(3, can_sell)
                if len(order_depth.buy_orders) > 0:
                    best_bid = max(order_depth.buy_orders.keys())
                    orders.append(Order(product, best_bid, -qty))
        else:
            # simpler approach
            if can_buy > 0:
                buy_price = int(mid - 1)
                orders.append(Order(product, buy_price, min(2, can_buy)))
            if can_sell > 0:
                sell_price = int(mid + 1)
                orders.append(Order(product, sell_price, -min(2, can_sell)))

        return orders

# not working
# first KELP strategy: "take-clear-make" style with reversion
class KelpStratOne:
    def __init__(self):
        # hold reference data
        self.name = "KelpStratOne"
        self.last_price = None
        self.adverse_volume = 15
        self.reversion_beta = -0.229
        # define some widths
        self.take_width = 1
        self.clear_width = 0
        self.disregard_edge = 1
        self.join_edge = 0
        self.default_edge = 1

    def load(self, data: dict) -> None:
        # if we want to store last_price or something
        if data is not None:
            self.last_price = data.get("last_price", None)

    def save(self) -> dict:
        # return current last_price if needed
        return {
            "last_price": self.last_price
        }

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int) -> List[Order]:
        orders: List[Order] = []

        # we first compute a fair value with reversion
        # step A) find best bid and best ask
        if len(order_depth.sell_orders) > 0 and len(order_depth.buy_orders) > 0:
            best_ask = min(order_depth.sell_orders.keys())
            best_bid = max(order_depth.buy_orders.keys())
        else:
            # fallback
            best_ask = 1.01 * (best_ask + best_bid / 2)
            best_bid = .99 * (best_ask + best_bid) / 2

        # step B) filter out large volume levels
        big_asks = [p for p in order_depth.sell_orders if abs(order_depth.sell_orders[p]) >= self.adverse_volume]
        big_bids = [p for p in order_depth.buy_orders if abs(order_depth.buy_orders[p]) >= self.adverse_volume]

        if big_asks and big_bids:
            mm_ask = min(big_asks)
            mm_bid = max(big_bids)
            mid = (mm_ask + mm_bid) / 2.0
        else:
            # if we can't find big_asks or big_bids, fallback to normal mid
            mid = (best_ask + best_bid) / 2.0

        # step C) do a small reversion logic if we had a last_price
        if self.last_price is not None:
            last_returns = (mid - self.last_price) / self.last_price
            pred_returns = last_returns * self.reversion_beta
            fair_value = mid + (mid * pred_returns)
        else:
            fair_value = mid

        self.last_price = mid  # store mid as last

        # step D) "take" if best_ask < fair_value - take_width, or best_bid > fair_value + take_width
        can_buy = position_limit - position
        can_sell = position + position_limit

        # TAKE logic for ask side
        if best_ask <= fair_value - self.take_width and can_buy > 0:
            ask_qty = min(-order_depth.sell_orders[best_ask], can_buy)
            if ask_qty > 0:
                orders.append(Order(product, best_ask, ask_qty))

        # TAKE logic for bid side
        if best_bid >= fair_value + self.take_width and can_sell > 0:
            bid_qty = min(order_depth.buy_orders[best_bid], can_sell)
            if bid_qty > 0:
                orders.append(Order(product, best_bid, -bid_qty))

        # CLEAR logic: we skip advanced clearing here

        # MAKE logic: place a bid around (fair_value - default_edge) and ask around (fair_value + default_edge)
        bid_price = round(fair_value - self.default_edge)
        ask_price = round(fair_value + self.default_edge)

        # if position is large, we can shift quotes
        soft_limit = 10
        if position > soft_limit: # if you're holding a lot, trying to make prices more favorable for market
            ask_price -= 1
        elif position < -soft_limit:
            bid_price += 1
        
        # -> try dynamically shifting soft limit based on volatiliy
            # -> because the limit is meant to measure how risky

        # place small orders if we still can
        can_buy = position_limit - position  # recalc after above trades
        can_sell = position + position_limit
        if can_buy > 0:
            orders.append(Order(product, bid_price, min(3, can_buy)))
        if can_sell > 0:
            orders.append(Order(product, ask_price, -min(3, can_sell)))

        return orders


# second KELP strategy: "popular buy/sell price" with pinned logic
class KelpStratTwo:
    def __init__(self, window_size=10):
        # name for debugging
        self.name = "KelpStratTwo"
        # pinned status rolling window
        self.window_size = window_size
        self.pinned_window = deque()

    def load(self, data: dict) -> None:
        # load pinned window if it exists
        if data is not None and "pinned" in data:
            self.pinned_window = deque(data["pinned"], maxlen=self.window_size)

    def save(self) -> dict:
        # store pinned
        return {
            "pinned": list(self.pinned_window)
        }

    def run_strategy(self, product: str, order_depth, position: int, position_limit: int, timestamp: int) -> List[Order]:
        orders: List[Order] = []

        # if there's no buy or sell orders, do nothing
        if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
            return orders

        # sort buy orders descending, sell orders ascending
        buy_orders = sorted(order_depth.buy_orders.items(), reverse=True)
        sell_orders = sorted(order_depth.sell_orders.items())

        # popular buy price => largest volume on the buy side
        popular_buy_price, _ = max(buy_orders, key=lambda tup: tup[1])
        # popular sell price => largest (negative) volume on the sell side => min(sell_orders, key=volume)
        popular_sell_price, _ = min(sell_orders, key=lambda tup: tup[1])

        # compute midpoint => "true_value"
        true_value = round((popular_buy_price + popular_sell_price) / 2)

        # pinned => if abs(position) >= position_limit
        pinned_now = abs(position) >= position_limit
        self.pinned_window.append(pinned_now)
        if len(self.pinned_window) > self.window_size:
            self.pinned_window.popleft()

        # define soft/hard liquidation
        soft_liquidate = False
        hard_liquidate = False
        if len(self.pinned_window) == self.window_size:
            # if half or more pinned => soft
            if sum(self.pinned_window) >= self.window_size / 2:
                soft_liquidate = True
            if all(self.pinned_window):
                hard_liquidate = True

        # shift buy or sell threshold if position is more than half
        max_buy_price = true_value
        min_sell_price = true_value
        if position > (position_limit * 0.5):
            max_buy_price = true_value - 1
        if position < -(position_limit * 0.5):
            min_sell_price = true_value + 1

        # how many we can buy or sell
        to_buy = position_limit - position
        to_sell = position + position_limit

        # buy from the existing sell orders
        for price, volume in sell_orders:
            if to_buy > 0 and price <= max_buy_price:
                qty = min(to_buy, -volume)
                orders.append(Order(product, price, qty))
                to_buy -= qty
                if to_buy <= 0:
                    break

        # hard liquidation => buy half at true_value
        if to_buy > 0 and hard_liquidate:
            buy_qty = to_buy // 2
            if buy_qty > 0:
                orders.append(Order(product, true_value, buy_qty))
                to_buy -= buy_qty

        # soft liquidation => buy half at (true_value - 2)
        if to_buy > 0 and soft_liquidate:
            buy_qty = to_buy // 2
            if buy_qty > 0:
                orders.append(Order(product, true_value - 2, buy_qty))
                to_buy -= buy_qty

        # leftover buy => place a single limit at popular_buy_price + 1
        if to_buy > 0:
            top_buy = max(buy_orders, key=lambda tup: tup[1])[0]
            price = min(max_buy_price, top_buy + 1)
            if price > 0:
                orders.append(Order(product, price, to_buy))
            to_buy = 0

        # now sell to the existing buy orders
        for price, volume in buy_orders:
            if to_sell > 0 and price >= min_sell_price:
                qty = min(to_sell, volume)
                orders.append(Order(product, price, -qty))
                to_sell -= qty
                if to_sell <= 0:
                    break

        # hard liquidation => sell half at true_value
        if to_sell > 0 and hard_liquidate:
            sell_qty = to_sell // 2
            if sell_qty > 0:
                orders.append(Order(product, true_value, -sell_qty))
                to_sell -= sell_qty

        # soft liquidation => sell half at (true_value + 2)
        if to_sell > 0 and soft_liquidate:
            sell_qty = to_sell // 2
            if sell_qty > 0:
                orders.append(Order(product, true_value + 2, -sell_qty))
                to_sell -= sell_qty

        # leftover sell => place a single limit at popular_sell_price - 1
        if to_sell > 0:
            top_sell = min(sell_orders, key=lambda tup: tup[1])[0]
            price = max(min_sell_price, top_sell - 1)
            if price > 0:
                orders.append(Order(product, price, -to_sell))
            to_sell = 0

        return orders


class Trader:
    def __init__(self):
        # we list all strategies we want for each product
        # each strategy can produce orders in turn
        self.product_strategies: Dict[str, List[Any]] = {
            "RAINFOREST_RESIN": [
                RainforestResinStrat(),
                checkArb(),
                # FourierStrat()
                # captureBidAskSpread(),
            ],
            "KELP": [
                checkArb(),
                # FourierStrat(),
                # possibly combine multiple - cant figure out
                # KelpStratOne(),  # "take-clear-make" style with reversion
                # meanRev(),
                KelpStratTwo()   # "popular buy/sell" approach with pinned logic
            ],
            "SQUID_INK": [
                # checkArb(),
                # combinedSquidInkStrategy(),
                FourierStrat()
                # checkSeasonSquidInk(),
                # lastImbVol()
            ],
        }

        # define position limits for each product
        self.position_limits = {
            "RAINFOREST_RESIN": 50,
            "KELP": 50,
            "SQUID_INK": 50,
        }

    def run(self, state: TradingState):
        print("traderData: " + state.traderData)  # prints the stored data if any
        print("Observations: " + str(state.observations))  # prints the observation data

        # decode any saved data with jsonpickle
        # traderData is passed in from the game or environment
        if state.traderData and state.traderData.strip():
            trader_object = jsonpickle.decode(state.traderData)
        else:
            trader_object = {}

        result = {}  # dictionary to hold orders keyed by product

        # for each product in the order depths
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            product_orders: List[Order] = []
            # figure out current position in this product
            current_position = state.position.get(product, 0)
            # get position limit from dictionary
            position_limit = self.position_limits.get(product, 50)

            # retrieve strategies for this product
            strategies_for_product = self.product_strategies.get(product, [])

            # run each strategy in turn
            for strat in strategies_for_product:
                # create a unique key for saving/loading this strategy's data
                strat_data_key = f"{product}_{strat.name}"
                # if we have saved data from previous iteration, load it
                if strat_data_key in trader_object:
                    strat.load(trader_object[strat_data_key])

                # run strategy to produce new orders
                new_orders = strat.run_strategy(product, order_depth, current_position, position_limit, state.timestamp)

                # sum up all quantities to see the net effect on position
                net = sum(o.quantity for o in new_orders)
                if net > 0:
                    # clamp buy so we don't exceed position limit
                    if current_position + net > position_limit:
                        net_allowed = position_limit - current_position
                        if net_allowed <= 0:
                            # can't buy any more, so skip
                            new_orders = []
                            net = 0
                        else:
                            # scale down all buy orders proportionally
                            ratio = net_allowed / net
                            adjusted_orders = []
                            for o in new_orders:
                                if o.quantity > 0:
                                    scaled_qty = int(o.quantity * ratio)
                                    if scaled_qty > 0:
                                        adjusted_orders.append(Order(o.symbol, o.price, scaled_qty))
                                else:
                                    # keep any sells as is
                                    adjusted_orders.append(o)
                            new_orders = adjusted_orders
                            net = sum(o.quantity for o in new_orders)
                elif net < 0:
                    # clamp sells so we don't exceed short limit
                    if current_position + net < -position_limit:
                        net_allowed = -position_limit - current_position
                        if net_allowed >= 0:
                            # can't sell any more, skip
                            new_orders = []
                            net = 0
                        else:
                            ratio = net_allowed / net
                            adjusted_orders = []
                            for o in new_orders:
                                if o.quantity < 0:
                                    scaled_qty = int(o.quantity * ratio)
                                    adjusted_orders.append(Order(o.symbol, o.price, scaled_qty))
                                else:
                                    # keep any buys as is
                                    adjusted_orders.append(o)
                            new_orders = adjusted_orders
                            net = sum(o.quantity for o in new_orders)

                # after potential clamping, update current_position
                current_position += net

                # add these orders to the product_orders for this iteration
                product_orders.extend(new_orders)

                # save updated state for this strat so next iteration can load it
                trader_object[strat_data_key] = strat.save()

            # store final orders for this product in result
            result[product] = product_orders

        # we pick a conversions integer (example: 1)
        conversions = 1
        # encode the updated trader_object back to a string
        new_trader_data = jsonpickle.encode(trader_object)
        # return the final orders, conversions, and next iteration traderData
        logger.flush(state, result, conversions, new_trader_data)
        return result, conversions, new_trader_data