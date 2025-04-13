import string
import json
import jsonpickle
from datamodel import OrderDepth, UserId, TradingState, Order, Symbol, ProsperityEncoder, Listing, Trade, Observation
from typing import List, Dict, Any
from collections import deque

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

    def run_strategy(self, product: str, order_depth: OrderDepth, position: int, position_limit: int) -> List[Order]:
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
        # soft_limit = 10
        # if position > soft_limit: # if you're holding a lot, trying to make prices more favorable for market
        #     ask_price -= 1
        # elif position < -soft_limit:
        #     bid_price += 1
        avg = sum(self.prices) / len(self.prices)
        variance = sum((p - avg) ** 2 for p in self.prices) / len(self.prices)
        std = variance ** 0.5
        soft_limit = (100/ std) 
        
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

    def run_strategy(self, product: str, order_depth, position: int, position_limit: int) -> List[Order]:
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
            "KELP": [
                checkArb(),
                # possibly combine multiple - cant figure out
                # KelpStratOne(),  # "take-clear-make" style with reversion
                # meanRev(),
                KelpStratTwo()   # "popular buy/sell" approach with pinned logic
            ],
           
        }

        # define position limits for each product
        self.position_limits = {
    
            "KELP": 50,
        
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
                new_orders = strat.run_strategy(product, order_depth, current_position, position_limit)

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