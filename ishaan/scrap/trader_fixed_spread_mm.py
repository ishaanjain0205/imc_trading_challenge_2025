from imc_trading_challenge_2025.ishaan.scrap.datamodel_SAMPLE import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
from typing import List, Dict, Any, Tuple
import string
import json
import jsonpickle
import statistics
import numpy as np

MAX_POSITION = 50
FIXED_SPREAD = 3
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

class Trader:
    
    def run(self, state: TradingState):
        # Only method required. It takes all buy and sell orders for all symbols as an input,
        # and outputs a list of orders to be sent
        
        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))
        
        result = {}
        
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            
            # Current position for this product (0 if not present yet)
            position = state.position.get(product, 0)
            
            # Extract best bid & best ask
            if len(order_depth.buy_orders) > 0:
                best_bid = max(order_depth.buy_orders.keys())
            else:
                best_bid = None

            if len(order_depth.sell_orders) > 0:
                best_ask = min(order_depth.sell_orders.keys())
            else:
                best_ask = None
            
            # Calculate mid price if both sides exist
            if best_bid is not None and best_ask is not None:
                mid_price = (best_bid + best_ask) / 2
            else:
                # If missing data, default mid price:
                mid_price = 10  
            
            # Our passive quote prices at fixed spread around the mid
            bid_price = int(mid_price - FIXED_SPREAD / 2)
            ask_price = int(mid_price + FIXED_SPREAD / 2)
            
            # Decide how many units to quote on each side (try a small size, e.g. 5)
            order_size = 8
            
            # Place BUY orders if we haven't hit +15 limit
            if position < MAX_POSITION:
                buy_qty = min(order_size, MAX_POSITION - position)
                if buy_qty > 0:
                    orders.append(Order(product, bid_price, buy_qty))
            
            # Place SELL orders if we haven't hit -15 limit
            if position > -MAX_POSITION:
                sell_qty = min(order_size, position + MAX_POSITION)
                if sell_qty > 0:
                    orders.append(Order(product, ask_price, -sell_qty))

            # Collect the orders for this product
            result[product] = orders
        
        # TraderData can store any relevant info to pass into next run
        traderData = "SAMPLE"
        # 'conversions' can be set to 1 if not specifically using currency conversions
        conversions = 0
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData