from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState, UserId
from typing import List, Dict, Any
import jsonpickle
import math
import numpy as np
import json

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


###############################################################################
#                          PARAMETER DICTIONARY                               #
###############################################################################
# Renamed from AMETHYSTS -> RAINFOREST_RESIN, STARFRUIT -> KELP
class Product:
    RAINFOREST_RESIN = "RAINFOREST_RESIN"
    KELP = "KELP"
    SQUID_INK = "SQUID_INK"

PARAMS = {
    Product.RAINFOREST_RESIN: {
        "fair_value": 10000,
        "take_width": 1,
        "clear_width": 0,
        "disregard_edge": 1,
        "join_edge": 2,
        "default_edge": 4,
        "soft_position_limit": 10,
    },
    Product.KELP: {
        "take_width": 1,
        "clear_width": 0,
        "prevent_adverse": True,
        "adverse_volume": 15,
        "reversion_beta": -0.229,
        "disregard_edge": 1,
        "join_edge": 0,
        "default_edge": 1,
    },
}

###############################################################################
#                             TRADER CLASS                                    #
###############################################################################

class Trader:
    def __init__(self, params=None):
        # Initialize param-based logic for RAINFOREST_RESIN (was AMETHYSTS) & KELP (was STARFRUIT)
        if params is None:
            params = PARAMS
        self.params = params

        # Position limit dictionary
        # Adjust these as needed for your environment (e.g., 20 or 50)
        self.LIMIT = {
            Product.RAINFOREST_RESIN: 50,
            Product.KELP: 50,
            Product.SQUID_INK: 50  # We'll also apply a limit to SQUID_INK
        }

    ###############################################################################
    #                            HELPER FUNCTIONS                                 #
    ###############################################################################
    def take_best_orders(
        self,
        product: str,
        fair_value: float,
        take_width: float,
        orders: List[Order],
        order_depth: OrderDepth,
        position: int,
        buy_order_volume: int,
        sell_order_volume: int,
        prevent_adverse: bool = False,
        adverse_volume: int = 0,
    ):
        """
        Attempt to 'take' the best opposite-side orders if they are favorable
        compared to our fair_value ± take_width. This is the same logic originally
        used for AMETHYSTS/STARFRUIT, now assigned to RAINFOREST_RESIN/KELP.
        """
        position_limit = self.LIMIT[product]

        # Try to BUY if best_ask is below (fair_value - take_width)
        if len(order_depth.sell_orders) != 0:
            best_ask = min(order_depth.sell_orders.keys())
            best_ask_amount = -1 * order_depth.sell_orders[best_ask]

            # If we are preventing adverse selection, skip big size if > adverse_volume
            if not prevent_adverse or abs(best_ask_amount) <= adverse_volume:
                if best_ask <= fair_value - take_width:
                    quantity = min(
                        best_ask_amount, position_limit - position
                    )
                    if quantity > 0:
                        orders.append(Order(product, best_ask, quantity))
                        buy_order_volume += quantity
                        order_depth.sell_orders[best_ask] += quantity  # reduce remaining
                        if order_depth.sell_orders[best_ask] == 0:
                            del order_depth.sell_orders[best_ask]

        # Try to SELL if best_bid is above (fair_value + take_width)
        if len(order_depth.buy_orders) != 0:
            best_bid = max(order_depth.buy_orders.keys())
            best_bid_amount = order_depth.buy_orders[best_bid]

            # If we are preventing adverse selection, skip big size if > adverse_volume
            if not prevent_adverse or abs(best_bid_amount) <= adverse_volume:
                if best_bid >= fair_value + take_width:
                    quantity = min(
                        best_bid_amount, position_limit + position
                    )
                    if quantity > 0:
                        orders.append(Order(product, best_bid, -quantity))
                        sell_order_volume += quantity
                        order_depth.buy_orders[best_bid] -= quantity
                        if order_depth.buy_orders[best_bid] == 0:
                            del order_depth.buy_orders[best_bid]

        return buy_order_volume, sell_order_volume

    def market_make(
        self,
        product: str,
        orders: List[Order],
        bid: float,
        ask: float,
        position: int,
        buy_order_volume: int,
        sell_order_volume: int,
    ):
        """
        Post a bid and ask around your fair value. 
        """
        position_limit = self.LIMIT[product]

        # How many more we can buy
        buy_quantity = position_limit - (position + buy_order_volume)
        if buy_quantity > 0:
            orders.append(Order(product, round(bid), buy_quantity))

        # How many more we can sell
        sell_quantity = position_limit + (position - sell_order_volume)
        if sell_quantity > 0:
            orders.append(Order(product, round(ask), -sell_quantity))

        return buy_order_volume, sell_order_volume

    def clear_position_order(
        self,
        product: str,
        fair_value: float,
        width: float,
        orders: List[Order],
        order_depth: OrderDepth,
        position: int,
        buy_order_volume: int,
        sell_order_volume: int,
    ):
        """
        'Clear' or reduce a net position by offsetting at near fair_value ± width.
        """
        position_after_take = position + buy_order_volume - sell_order_volume
        fair_for_bid = round(fair_value - width)
        fair_for_ask = round(fair_value + width)

        position_limit = self.LIMIT[product]
        buy_quantity = position_limit - (position + buy_order_volume)
        sell_quantity = position_limit + (position - sell_order_volume)

        # If net long, we might want to sell some near fair_for_ask
        if position_after_take > 0:
            # Sum volumes at all buy prices >= fair_for_ask
            clear_quantity = sum(
                vol for px, vol in order_depth.buy_orders.items() if px >= fair_for_ask
            )
            clear_quantity = min(clear_quantity, position_after_take)
            sent_quantity = min(sell_quantity, clear_quantity)
            if sent_quantity > 0:
                orders.append(Order(product, fair_for_ask, -abs(sent_quantity)))
                sell_order_volume += abs(sent_quantity)

        # If net short, we might want to buy back near fair_for_bid
        if position_after_take < 0:
            # Sum volumes at all sell prices <= fair_for_bid
            clear_quantity = sum(
                abs(vol) for px, vol in order_depth.sell_orders.items() if px <= fair_for_bid
            )
            clear_quantity = min(clear_quantity, abs(position_after_take))
            sent_quantity = min(buy_quantity, clear_quantity)
            if sent_quantity > 0:
                orders.append(Order(product, fair_for_bid, abs(sent_quantity)))
                buy_order_volume += abs(sent_quantity)

        return buy_order_volume, sell_order_volume

    def kelp_fair_value(self, order_depth: OrderDepth, memory_state: dict) -> float:
        """
        Renamed from 'starfruit_fair_value' -> 'kelp_fair_value'.
        Contains logic for a reversion factor if we see a big-lot best bid/ask.
        """
        if not order_depth.sell_orders or not order_depth.buy_orders:
            return memory_state.get("kelp_last_price", 10.0)

        best_ask = min(order_depth.sell_orders.keys())
        best_bid = max(order_depth.buy_orders.keys())

        # Filter for large-lot levels
        filtered_ask_prices = [
            px for px in order_depth.sell_orders
            if abs(order_depth.sell_orders[px]) >= self.params[Product.KELP]["adverse_volume"]
        ]
        filtered_bid_prices = [
            px for px in order_depth.buy_orders
            if abs(order_depth.buy_orders[px]) >= self.params[Product.KELP]["adverse_volume"]
        ]
        mm_ask = min(filtered_ask_prices) if filtered_ask_prices else None
        mm_bid = max(filtered_bid_prices) if filtered_bid_prices else None

        # If we can't find big-lot extremes, fallback to basic mid
        if mm_ask is None or mm_bid is None:
            mid_price = (best_ask + best_bid) / 2.0
        else:
            mid_price = (mm_ask + mm_bid) / 2.0

        last_price = memory_state.get("kelp_last_price", mid_price)
        last_returns = (mid_price - last_price) / (last_price if last_price != 0 else 1)
        reversion_beta = self.params[Product.KELP]["reversion_beta"]
        pred_returns = last_returns * reversion_beta
        fair_val = mid_price + mid_price * pred_returns

        # Update memory
        memory_state["kelp_last_price"] = mid_price
        return fair_val

    def take_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        fair_value: float,
        take_width: float,
        position: int,
        prevent_adverse: bool = False,
        adverse_volume: int = 0,
    ):
        """
        Wrapper that calls 'take_best_orders' to capture favorable trades
        immediately if they are well beyond fair_value ± take_width.
        """
        orders: List[Order] = []
        buy_order_volume = 0
        sell_order_volume = 0

        buy_order_volume, sell_order_volume = self.take_best_orders(
            product,
            fair_value,
            take_width,
            orders,
            order_depth,
            position,
            buy_order_volume,
            sell_order_volume,
            prevent_adverse,
            adverse_volume,
        )
        return orders, buy_order_volume, sell_order_volume

    def clear_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        fair_value: float,
        clear_width: float,
        position: int,
        buy_order_volume: int,
        sell_order_volume: int,
    ):
        """
        Wrapper that calls 'clear_position_order' to reduce an existing position
        at near fair_value ± clear_width if possible.
        """
        orders: List[Order] = []
        buy_order_volume, sell_order_volume = self.clear_position_order(
            product,
            fair_value,
            clear_width,
            orders,
            order_depth,
            position,
            buy_order_volume,
            sell_order_volume,
        )
        return orders, buy_order_volume, sell_order_volume

    def make_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        fair_value: float,
        position: int,
        buy_order_volume: int,
        sell_order_volume: int,
        disregard_edge: float,
        join_edge: float,
        default_edge: float,
        manage_position: bool = False,
        soft_position_limit: int = 0,
    ):
        """
        Generate 'market-making' limit orders around the best known levels
        (pennying or joining).  This is the same logic used for AMETHYSTS/STARFRUIT,
        renamed for RAINFOREST_RESIN/KELP.
        """
        orders: List[Order] = []

        # Identify the set of ask (sell) prices that are well above fair_value + disregard_edge
        asks_above_fair = [
            price for price in order_depth.sell_orders
            if price > fair_value + disregard_edge
        ]
        bids_below_fair = [
            price for price in order_depth.buy_orders
            if price < fair_value - disregard_edge
        ]

        best_ask_above_fair = min(asks_above_fair) if asks_above_fair else None
        best_bid_below_fair = max(bids_below_fair) if bids_below_fair else None

        # Default edges from fair_value
        ask = round(fair_value + default_edge)
        if best_ask_above_fair is not None:
            dist_to_fair = abs(best_ask_above_fair - fair_value)
            if dist_to_fair <= join_edge:
                ask = best_ask_above_fair  # Join
            else:
                ask = best_ask_above_fair - 1  # Penny

        bid = round(fair_value - default_edge)
        if best_bid_below_fair is not None:
            dist_to_fair = abs(fair_value - best_bid_below_fair)
            if dist_to_fair <= join_edge:
                bid = best_bid_below_fair
            else:
                bid = best_bid_below_fair + 1

        # Manage position within 'soft_position_limit' by shading quotes
        if manage_position:
            if position > soft_position_limit:
                ask -= 1
            elif position < -soft_position_limit:
                bid += 1

        buy_order_volume, sell_order_volume = self.market_make(
            product,
            orders,
            bid,
            ask,
            position,
            buy_order_volume,
            sell_order_volume,
        )

        return orders, buy_order_volume, sell_order_volume

    ###############################################################################
    #                                RUN METHOD                                   #
    ###############################################################################
    def run(self, state: TradingState):

        # Decode any previously saved dictionary
        # We'll store both RAINFOREST_RESIN/KELP state and SQUID_INK state in here
        memory_state = {}
        if state.traderData:
            try:
                memory_state = jsonpickle.decode(state.traderData)
            except:
                memory_state = {}

        # Ensure sub-dicts exist for each product
        if "kelp_last_price" not in memory_state:
            memory_state["kelp_last_price"] = 10.0
        if "squid_ink_prices" not in memory_state:
            memory_state["squid_ink_prices"] = {}  # store last known price per iteration if desired

        result: Dict[str, List[Order]] = {}
        conversions = 0  # We'll keep this at 0 unless you truly need conversions

        PRECALC_FREQS = [0.00013333333, 0.00006666667, 0.00003333333]
        PRECALC_AMPS = [405967.39994, 732541.88318, 1000241.25709]
        PRECALC_PHASES = [-0.58284677, -2.52378785, -1.95510220]


        for product, order_depth in state.order_depths.items():
            position = state.position.get(product, 0)
            orders: List[Order] = []

            ###############################################################################
            # SQUID_INK LOGIC (the “last+im+v” approach you gave)
            ###############################################################################
            if product == Product.SQUID_INK:
                best_bid = max(order_depth.buy_orders.keys(), default=None)
                best_ask = min(order_depth.sell_orders.keys(), default=None)

                if best_bid is not None and best_ask is not None:
                    current_price = (best_bid + best_ask) / 2
                    price_series = memory_state["squid_ink_prices"].get("series", [])
                    price_series.append(current_price)
                    if len(price_series) > 256:
                        price_series = price_series[-256:]
                    memory_state["squid_ink_prices"]["series"] = price_series

                    # No trend slope logic, just price tracking
                    bid_price = best_bid
                    ask_price = best_ask

                    quantity = 50
                    position_limit = self.LIMIT[product]
                    max_buy = min(quantity, position_limit - position)
                    max_sell = min(quantity, position_limit + position)

                    if max_buy > 0:
                        orders.append(Order(product, int(bid_price), max_buy))
                    if max_sell > 0:
                        orders.append(Order(product, int(ask_price), -max_sell))

                    memory_state["squid_ink_prices"]["last_price"] = current_price
                    result[product] = orders

            ###############################################################################
            # RAINFOREST_RESIN / KELP LOGIC (renamed from AMETHYSTS / STARFRUIT)
            ###############################################################################
            elif product == Product.RAINFOREST_RESIN:
                # 1) 'take' favorable orders
                fair = self.params[Product.RAINFOREST_RESIN]["fair_value"]
                take_w = self.params[Product.RAINFOREST_RESIN]["take_width"]
                a_orders, buy_vol, sell_vol = self.take_orders(
                    Product.RAINFOREST_RESIN,
                    order_depth,
                    fair,
                    take_w,
                    position
                )
                # 2) 'clear' near fair_value if we’re net long/short
                clear_w = self.params[Product.RAINFOREST_RESIN]["clear_width"]
                c_orders, buy_vol, sell_vol = self.clear_orders(
                    Product.RAINFOREST_RESIN,
                    order_depth,
                    fair,
                    clear_w,
                    position,
                    buy_vol,
                    sell_vol
                )
                # 3) 'make' new limit orders around fair_value
                disregard_edge = self.params[Product.RAINFOREST_RESIN]["disregard_edge"]
                join_edge = self.params[Product.RAINFOREST_RESIN]["join_edge"]
                default_edge = self.params[Product.RAINFOREST_RESIN]["default_edge"]
                soft_lim = self.params[Product.RAINFOREST_RESIN]["soft_position_limit"]
                m_orders, _, _ = self.make_orders(
                    Product.RAINFOREST_RESIN,
                    order_depth,
                    fair,
                    position,
                    buy_vol,
                    sell_vol,
                    disregard_edge,
                    join_edge,
                    default_edge,
                    manage_position=True,
                    soft_position_limit=soft_lim
                )
                result[product] = a_orders + c_orders + m_orders

            elif product == Product.KELP:
                # 1) Compute dynamic fair value
                fair = self.kelp_fair_value(order_depth, memory_state)
                # 2) 'take' favorable orders
                take_w = self.params[Product.KELP]["take_width"]
                prev_adverse = self.params[Product.KELP]["prevent_adverse"]
                adv_vol = self.params[Product.KELP]["adverse_volume"]
                t_orders, buy_vol, sell_vol = self.take_orders(
                    Product.KELP,
                    order_depth,
                    fair,
                    take_w,
                    position,
                    prev_adverse,
                    adv_vol
                )
                # 3) Clear near fair_value ± clear_width
                clear_w = self.params[Product.KELP]["clear_width"]
                c_orders, buy_vol, sell_vol = self.clear_orders(
                    Product.KELP,
                    order_depth,
                    fair,
                    clear_w,
                    position,
                    buy_vol,
                    sell_vol
                )
                # 4) Post limit orders around the best known edges
                disregard_edge = self.params[Product.KELP]["disregard_edge"]
                join_edge = self.params[Product.KELP]["join_edge"]
                default_edge = self.params[Product.KELP]["default_edge"]
                # KELP doesn’t define a soft_position_limit in your param dict, we can omit or set 0
                m_orders, _, _ = self.make_orders(
                    Product.KELP,
                    order_depth,
                    fair,
                    position,
                    buy_vol,
                    sell_vol,
                    disregard_edge,
                    join_edge,
                    default_edge
                )
                result[product] = t_orders + c_orders + m_orders

        # Finally, encode the memory_state back for next iteration
        traderData = jsonpickle.encode(memory_state)
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData
