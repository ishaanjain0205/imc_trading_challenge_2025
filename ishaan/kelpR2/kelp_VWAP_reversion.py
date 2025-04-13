# from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
# from typing import List, Any
# import string
# import jsonpickle
# import json

# class Logger:
#     def __init__(self) -> None:
#         self.logs = ""
#         self.max_log_length = 3750

#     def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
#         self.logs += sep.join(map(str, objects)) + end

#     def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
#         base_length = len(self.to_json([
#             self.compress_state(state, ""),
#             self.compress_orders(orders),
#             conversions,
#             "",
#             "",
#         ]))

#         max_item_length = (self.max_log_length - base_length) // 3

#         print(self.to_json([
#             self.compress_state(state, self.truncate(state.traderData, max_item_length)),
#             self.compress_orders(orders),
#             conversions,
#             self.truncate(trader_data, max_item_length),
#             self.truncate(self.logs, max_item_length),
#         ]))

#         self.logs = ""

#     def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
#         return [
#             state.timestamp,
#             trader_data,
#             self.compress_listings(state.listings),
#             self.compress_order_depths(state.order_depths),
#             self.compress_trades(state.own_trades),
#             self.compress_trades(state.market_trades),
#             state.position,
#             self.compress_observations(state.observations),
#         ]

#     def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
#         compressed = []
#         for listing in listings.values():
#             compressed.append([listing.symbol, listing.product, listing.denomination])
#         return compressed

#     def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
#         compressed = {}
#         for symbol, order_depth in order_depths.items():
#             compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]
#         return compressed

#     def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
#         compressed = []
#         for arr in trades.values():
#             for trade in arr:
#                 compressed.append([
#                     trade.symbol,
#                     trade.price,
#                     trade.quantity,
#                     trade.buyer,
#                     trade.seller,
#                     trade.timestamp,
#                 ])
#         return compressed

#     def compress_observations(self, observations: Observation) -> list[Any]:
#         conversion_observations = {}
#         for product, observation in observations.conversionObservations.items():
#             conversion_observations[product] = [
#                 observation.bidPrice,
#                 observation.askPrice,
#                 observation.transportFees,
#                 observation.exportTariff,
#                 observation.importTariff,
#                 observation.sunlight,
#                 observation.humidity,
#             ]
#         return [observations.plainValueObservations, conversion_observations]

#     def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
#         compressed = []
#         for arr in orders.values():
#             for order in arr:
#                 compressed.append([order.symbol, order.price, order.quantity])
#         return compressed

#     def to_json(self, value: Any) -> str:
#         return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

#     def truncate(self, value: str, max_length: int) -> str:
#         if len(value) <= max_length:
#             return value
#         return value[:max_length - 3] + "..."

# logger = Logger()
# # WORK ON THIS FILE
# # RUN FUNCTION => FUNCTION TO MODIFY, EXECUTES OUR TRADES
# class Trader:

#     def run(self, state: TradingState):
#         # Only method required. It takes all buy and sell orders for all symbols as an input, and outputs a list of orders to be sent
#         print("traderData: " + state.traderData)
#         print("Observations: " + str(state.observations))
#         result = {}

#         product = "KELP"
#         order_depth: OrderDepth = state.order_depths[product]
#         orders: List[Order] = []
#         acceptable_price = 10  # Participant should calculate this value

#         #####################################################
#         # PARAMS 
#         #####################################################

#         if state.traderData:
#             traderObject = jsonpickle.decode(state.traderData)
#             FIXED_STD = traderObject.get("FIXED_STD", [0.5468034905299181])[0]
#             X = traderObject.get("X", [1.8])[0]
#         else:
#             traderObject = {}
#             FIXED_STD = 0.5468034905299181
#             X = 1.5

#         VWAP = None

#         #####################################################
#         # 1) CALCULATE CURRENT VWAP
#         #####################################################

#         numeratorVWAP = 0
#         denominatorVWAP = 0
#         # numerator = sum(bid / ask price * bid / ask volume)
#         # denominator = sum(bid + ask volumes)
#         for best_ask, best_ask_amount in order_depth.buy_orders.items():
#             numeratorVWAP += best_ask * best_ask_amount
#             denominatorVWAP += best_ask_amount
#         for best_bid, best_bid_amount in order_depth.sell_orders.items():
#             numeratorVWAP += best_bid * best_bid_amount
#             denominatorVWAP += best_bid_amount

#         if denominatorVWAP != 0:
#             VWAP = numeratorVWAP / denominatorVWAP
#         else:
#             VWAP = 1
#             print("VWAP denominator is 0, setting VWAP to 1")

#         print("VWAP: " + str(VWAP))
#         #####################################################
#         # 2) CALCULATE MID PRICE
#         #####################################################

#         best_ask = list(order_depth.sell_orders.items())[0]
#         best_bid = list(order_depth.buy_orders.items())[0]

#         mid_price = (best_ask[0] + best_bid[0]) / 2

#         #####################################################
#         # 3) CALCULATE UPPER AND LOWER BOUNDS 
#         #####################################################

#         # upperbound = VWAP + (X * FIXED_STD) -->add average variance * a multiplier to execute at peaks and troughs
#         # lowerbound = VWAP - (X * FIXED_STD)

#         upper_bound = VWAP + (X * FIXED_STD)
#         lower_bound = VWAP - (X * FIXED_STD)
#         print("Upper bound: " + str(upper_bound))
#         print("Lower bound: " + str(lower_bound))

#         #####################################################
#         # 4) CALCULATE QUOTES
#         #####################################################

#         orderType = None

#         if mid_price >= upper_bound:
#             acceptable_price = upper_bound
#             orderType = "Sell"
#         elif mid_price <= lower_bound:
#             acceptable_price = lower_bound
#             orderType = "Buy"

#         print("Acceptable Price: " + str(acceptable_price))
#         print("Order Type: " + str(orderType))
#         print("Mid Price: " + str(mid_price))

#         #####################################################
#         # 5) PLACE ORDERS
#         #####################################################

#         # USER TODO: Change position limit from 50 
#         current_position = state.position.get(product, 0)
#         currentBuyPotential = 50 - current_position
#         currentSellPotential = current_position + 50  # because -50 is lower limit

#         # BUY
#         if orderType == "Buy" and currentBuyPotential > 0:
#             sorted_asks = sorted(order_depth.sell_orders.items())  # ascending order of price
#             for ask_price, ask_volume in sorted_asks:
#                 if int(ask_price) <= acceptable_price:
#                     volume_to_buy = min(ask_volume, currentBuyPotential)
#                     print("BUY", str(-volume_to_buy) + "x", ask_price)
#                     orders.append(Order(product, ask_price, -volume_to_buy))
#                     currentBuyPotential -= volume_to_buy
#                     if currentBuyPotential <= 0:
#                         break
#                 else:
#                     print(f"QUOTING BID at {acceptable_price} for {currentBuyPotential} units")
#                     orders.append(Order(product, acceptable_price, -currentBuyPotential))
#                     break

#         # SELL
#         if orderType == "Sell" and currentSellPotential > 0:
#             sorted_bids = sorted(order_depth.buy_orders.items(), reverse=True)  # descending order of price
#             for bid_price, bid_volume in sorted_bids:
#                 if int(bid_price) >= acceptable_price:
#                     volume_to_sell = min(bid_volume, currentSellPotential)
#                     print("SELL", str(volume_to_sell) + "x", bid_price)
#                     orders.append(Order(product, bid_price, volume_to_sell))
#                     currentSellPotential -= volume_to_sell
#                     if currentSellPotential <= 0:
#                         break
#                 else:
#                     print(f"QUOTING ASK at {acceptable_price} for {currentSellPotential} units")
#                     orders.append(Order(product, acceptable_price, currentSellPotential))
#                     break

#         #####################################################
#         # 6) RETURN ORDERS
#         #####################################################

#         bid_price = 0  # OPTIMAL BID PRICE DYNAMICALLY UPDATED
#         ask_price = 0  # OPTIMAL ASK PRICE DYNAMICALLY UPDATED

#         print("Acceptable price : " + str(acceptable_price))
#         print("Buy Order depth : " + str(len(order_depth.buy_orders)) + ", Sell order depth : " + str(len(order_depth.sell_orders)))

#         if len(order_depth.sell_orders) != 0:
#             best_ask, best_ask_amount = list(order_depth.sell_orders.items())[0]
#             if int(best_ask) < acceptable_price:
#                 print("BUY", str(-best_ask_amount) + "x", best_ask)
#                 orders.append(Order(product, best_ask, -best_ask_amount))

#         if len(order_depth.buy_orders) != 0:
#             best_bid, best_bid_amount = list(order_depth.buy_orders.items())[0]
#             if int(best_bid) > acceptable_price:
#                 print("SELL", str(best_bid_amount) + "x", best_bid)
#                 orders.append(Order(product, best_bid, -best_bid_amount))

#         result[product] = orders

#         # USER TODO: Add to traderData
#         traderObject['FIXED_STD'] = [FIXED_STD]
#         traderObject['X'] = [X]
#         traderData = jsonpickle.encode(traderObject)

#         conversions = 1
#         logger.flush(state, result, conversions, traderData)

#         return result, conversions, traderData

# WORK ON THIS FILE
# RUN FUNCTION => FUNCTION TO MODIFY, EXECUTES OUR TRADES

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
from typing import List, Any, Dict
import jsonpickle
import json

class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: Dict[Symbol, List[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(self.to_json([
            self.compress_state(state, ""),
            self.compress_orders(orders),
            conversions,
            "",
            "",
        ]))

        max_item_length = (self.max_log_length - base_length) // 3

        print(self.to_json([
            self.compress_state(state, self.truncate(state.traderData, max_item_length)),
            self.compress_orders(orders),
            conversions,
            self.truncate(trader_data, max_item_length),
            self.truncate(self.logs, max_item_length),
        ]))

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
        return [[listing.symbol, listing.product, listing.denomination] for listing in listings.values()]

    def compress_order_depths(self, order_depths: Dict[Symbol, OrderDepth]) -> Dict[Symbol, List[Any]]:
        return {
            symbol: [depth.buy_orders, depth.sell_orders]
            for symbol, depth in order_depths.items()
        }

    def compress_trades(self, trades: Dict[Symbol, List[Trade]]) -> List[List[Any]]:
        return [
            [trade.symbol, trade.price, trade.quantity, trade.buyer, trade.seller, trade.timestamp]
            for arr in trades.values()
            for trade in arr
        ]

    def compress_observations(self, obs: Observation) -> List[Any]:
        conversions = {
            p: [
                o.bidPrice,
                o.askPrice,
                o.transportFees,
                o.exportTariff,
                o.importTariff,
                o.sunlightIndex,
                o.sugarPrice,
            ]
            for p, o in obs.conversionObservations.items()
        }
        return [obs.plainValueObservations, conversions]

    def compress_orders(self, orders: Dict[Symbol, List[Order]]) -> List[List[Any]]:
        return [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr]

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        return value if len(value) <= max_length else value[:max_length - 3] + "..."

logger = Logger()

class Trader:
    def run(self, state: TradingState):
        # We'll trade for product KELP
        product = "KELP"
        orders: List[Order] = []
        result = {}

        # traderData: store persistent info about open positions, etc.
        if state.traderData:
            traderObject = jsonpickle.decode(state.traderData)
        else:
            traderObject = {}

        # Load or init parameters
        FIXED_STD = traderObject.get("FIXED_STD", [0.5468])[0]
        X = traderObject.get("X", [1.5])[0]
        # Example: track if we have an open position from a previous tick
        open_position_info = traderObject.get("open_position_info", None)

        order_depth = state.order_depths[product]

        # Basic checks
        if not order_depth.buy_orders or not order_depth.sell_orders:
            # No market => do nothing
            result[product] = []
            # flush + return
            traderObject["open_position_info"] = open_position_info
            traderData = jsonpickle.encode(traderObject)
            logger.flush(state, result, 1, traderData)
            return result, 1, traderData

        # ============== 1) CALCULATE VWAP ==============
        numeratorVWAP = 0.0
        denominatorVWAP = 0.0

        # Sells: market asks (you buy)
        for ask_price, ask_volume in order_depth.sell_orders.items():
            numeratorVWAP += ask_price * abs(ask_volume)
            denominatorVWAP += abs(ask_volume)
        # Buys: market bids (you sell)
        for bid_price, bid_volume in order_depth.buy_orders.items():
            numeratorVWAP += bid_price * abs(bid_volume)
            denominatorVWAP += abs(bid_volume)

        VWAP = numeratorVWAP / denominatorVWAP if denominatorVWAP > 0 else 1.0
        logger.print(f"VWAP: {VWAP:.2f}")

        # ============== 2) MID PRICE ==============
        best_bid_price = max(order_depth.buy_orders.keys())
        best_ask_price = min(order_depth.sell_orders.keys())
        mid_price = (best_bid_price + best_ask_price) / 2.0

        # ============== 3) BOUNDS ==============
        upper_bound = VWAP + (X * FIXED_STD)
        lower_bound = VWAP - (X * FIXED_STD)

        logger.print(f"BANDS => Lower: {lower_bound:.2f}  Upper: {upper_bound:.2f}, mid_price: {mid_price:.2f}")

        # ============== 3a) Simple Trend Filter ==============
        # We'll approximate a trend by seeing if best_bid_price > best_ask_price from a few ticks ago
        # For something more robust, store a small queue of prices in traderObject
        last_mid = traderObject.get("last_mid", mid_price)
        # if new mid is significantly above old mid => up-trend
        up_trend = (mid_price > last_mid + 1.0)  # 1.0 threshold is arbitrary
        down_trend = (mid_price < last_mid - 1.0)
        traderObject["last_mid"] = mid_price

        # ============== 4) Decide buy/sell signals ==============
        orderType = None
        acceptable_price = mid_price

        # If strong uptrend, skip selling
        # If strong downtrend, skip buying
        # => only trade if not trending
        if (not up_trend) and (mid_price >= upper_bound):
            orderType = "Sell"
            acceptable_price = upper_bound
        elif (not down_trend) and (mid_price <= lower_bound):
            orderType = "Buy"
            acceptable_price = lower_bound

        logger.print(f"orderType: {orderType}, acceptable_price: {acceptable_price:.2f}")

        # ============== 5) Manage existing open position ==============
        # If we have an open trade, check if we can exit at VWAP or trigger a stop
        current_pos = state.position.get(product, 0)

        # If there's an open position from last tick
        if open_position_info is not None:
            entry_side = open_position_info["side"]    # 'Buy' or 'Sell'
            entry_price = open_position_info["price"]  # float
            entry_size = open_position_info["size"]    # int, how big
            # We'll exit if mid crosses VWAP
            # or if price goes 2.5 x std from VWAP => stop
            stop_upper = VWAP + 2.5*FIXED_STD
            stop_lower = VWAP - 2.5*FIXED_STD

            logger.print(f"Open pos => side: {entry_side}, size: {entry_size}, entry: {entry_price}")

            # If we are in a long, we want to exit if mid_price >= VWAP
            # or if mid_price <= stop_lower
            if entry_side == "Buy":
                if mid_price >= VWAP:
                    # exit at VWAP (limit)
                    orders.append(Order(product, int(VWAP), -entry_size))
                    logger.print(f"Exiting BUY at VWAP => size: {entry_size}")
                    open_position_info = None
                elif mid_price <= stop_lower:
                    # stop out
                    orders.append(Order(product, int(stop_lower), -entry_size))
                    logger.print(f"STOPPING out BUY => size: {entry_size}")
                    open_position_info = None

            # If short, exit if mid_price <= VWAP
            # or if mid_price >= stop_upper
            elif entry_side == "Sell":
                if mid_price <= VWAP:
                    # exit at VWAP
                    orders.append(Order(product, int(VWAP), entry_size))
                    logger.print(f"Exiting SELL at VWAP => size: {entry_size}")
                    open_position_info = None
                elif mid_price >= stop_upper:
                    # stop out
                    orders.append(Order(product, int(stop_upper), entry_size))
                    logger.print(f"STOPPING out SELL => size: {entry_size}")
                    open_position_info = None

        # ============== 6) If no open position, place new trade if triggered ==============
        elif orderType is not None and orderType in ["Buy","Sell"] and current_pos != 50 and current_pos != -50:
            # Are we at position limit?
            if orderType == "Buy" and current_pos < 50:
                # Do a single-lot or partial-lot buy for demonstration
                # Or do bigger if you want
                buy_qty = min(10, 50 - current_pos)  # example size of 10
                # place the buy
                orders.append(Order(product, int(acceptable_price), buy_qty))
                # Save open pos
                open_position_info = {
                    "side":"Buy",
                    "price": acceptable_price,
                    "size": buy_qty
                }
                logger.print(f"OPENING Buy => {buy_qty} at {acceptable_price}")

            elif orderType == "Sell" and current_pos > -50:
                sell_qty = min(10, current_pos+50)
                orders.append(Order(product, int(acceptable_price), -sell_qty))
                open_position_info = {
                    "side":"Sell",
                    "price": acceptable_price,
                    "size": sell_qty
                }
                logger.print(f"OPENING Sell => {sell_qty} at {acceptable_price}")

        # ============== 7) Finalize orders & Save state ==============
        result[product] = orders

        # Update your persistent state
        traderObject["open_position_info"] = open_position_info
        traderData = jsonpickle.encode(traderObject)

        # Flush logs & return
        logger.flush(state, result, 1, traderData)
        return result, 1, traderData