import json
from abc import abstractmethod
from collections import deque
from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState, UserId
from typing import Any, TypeAlias
import jsonpickle
import math
import numpy as np

JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None

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
#                            STRATEGY BASE CLASSES                            #
###############################################################################
class Strategy:
    def __init__(self, symbol: str, limit: int) -> None:
        self.symbol = symbol
        self.limit = limit

    @abstractmethod
    def act(self, state: TradingState) -> None:
        raise NotImplementedError()

    def run(self, state: TradingState) -> list[Order]:
        self.orders = []
        self.act(state)
        return self.orders

    def buy(self, price: int, quantity: int) -> None:
        self.orders.append(Order(self.symbol, price, quantity))

    def sell(self, price: int, quantity: int) -> None:
        self.orders.append(Order(self.symbol, price, -quantity))

    def save(self) -> JSON:
        return None

    def load(self, data: JSON) -> None:
        pass

class MarketMakingStrategy(Strategy):
    def __init__(self, symbol: Symbol, limit: int) -> None:
        super().__init__(symbol, limit)
        self.window = deque()
        self.window_size = 10

    @abstractmethod
    def get_true_value(state: TradingState) -> int:
        raise NotImplementedError()

    def act(self, state: TradingState) -> None:
        true_value = self.get_true_value(state)

        order_depth = state.order_depths[self.symbol]
        buy_orders = sorted(order_depth.buy_orders.items(), reverse=True)
        sell_orders = sorted(order_depth.sell_orders.items())

        position = state.position.get(self.symbol, 0)
        to_buy = self.limit - position
        to_sell = self.limit + position

        self.window.append(abs(position) == self.limit)
        if len(self.window) > self.window_size:
            self.window.popleft()

        soft_liquidate = len(self.window) == self.window_size and sum(self.window) >= self.window_size / 2 and self.window[-1]
        hard_liquidate = len(self.window) == self.window_size and all(self.window)

        max_buy_price = true_value - 1 if position > self.limit * 0.5 else true_value
        min_sell_price = true_value + 1 if position < self.limit * -0.5 else true_value

        for price, volume in sell_orders:
            if to_buy > 0 and price <= max_buy_price:
                quantity = min(to_buy, -volume)
                self.buy(price, quantity)
                to_buy -= quantity

        if to_buy > 0 and hard_liquidate:
            quantity = to_buy // 2
            self.buy(true_value, quantity)
            to_buy -= quantity

        if to_buy > 0 and soft_liquidate:
            quantity = to_buy // 2
            self.buy(true_value - 2, quantity)
            to_buy -= quantity

        if to_buy > 0:
            popular_buy_price = max(buy_orders, key=lambda tup: tup[1])[0]
            price = min(max_buy_price, popular_buy_price + 1)
            self.buy(price, to_buy)

        for price, volume in buy_orders:
            if to_sell > 0 and price >= min_sell_price:
                quantity = min(to_sell, volume)
                self.sell(price, quantity)
                to_sell -= quantity

        if to_sell > 0 and hard_liquidate:
            quantity = to_sell // 2
            self.sell(true_value, quantity)
            to_sell -= quantity

        if to_sell > 0 and soft_liquidate:
            quantity = to_sell // 2
            self.sell(true_value + 2, quantity)
            to_sell -= quantity

        if to_sell > 0:
            popular_sell_price = min(sell_orders, key=lambda tup: tup[1])[0]
            price = max(min_sell_price, popular_sell_price - 1)
            self.sell(price, to_sell)

    def save(self) -> JSON:
        return list(self.window)

    def load(self, data: JSON) -> None:
        self.window = deque(data)

###############################################################################
#                            PRODUCT STRATEGIES                               #
###############################################################################
class RAINFORESTRESINStrategy(MarketMakingStrategy):
    def get_true_value(self, state: TradingState) -> int:
        return 10_000

class KELPStrategy(MarketMakingStrategy):
    def get_true_value(self, state: TradingState) -> int:
        order_depth = state.order_depths[self.symbol]
        buy_orders = sorted(order_depth.buy_orders.items(), reverse=True)
        sell_orders = sorted(order_depth.sell_orders.items())
        popular_buy_price = max(buy_orders, key=lambda tup: tup[1])[0]
        popular_sell_price = min(sell_orders, key=lambda tup: tup[1])[0]
        return round((popular_buy_price + popular_sell_price) / 2)

###############################################################################
#                      SQUID INK STRATEGY (UPDATED)                         #
###############################################################################
class SQUIDINKStrategy(MarketMakingStrategy):
    def __init__(self, symbol: Symbol, limit: int) -> None:
        super().__init__(symbol, limit)
        # Internal memory variables for the squid ink strategy.
        self.last_price = 2000.0
        self.rolling_volatility = 0.0
        self.alpha = 0.2  # Weight for the volatility update

    def act(self, state: TradingState) -> None:
        order_depth = state.order_depths[self.symbol]
        buy_orders = order_depth.buy_orders
        sell_orders = order_depth.sell_orders

        best_bid = max(buy_orders.keys()) if buy_orders else None
        best_ask = min(sell_orders.keys()) if sell_orders else None
        position = state.position.get(self.symbol, 0)

        # Determine the current price: use the mid-price when available.
        if best_bid is not None and best_ask is not None:
            current_price = (best_bid + best_ask) / 2
        else:
            current_price = self.last_price

        raw_volatility = abs(current_price - self.last_price)
        new_rolling_volatility = self.alpha * raw_volatility + (1 - self.alpha) * self.rolling_volatility
        new_rolling_volatility = max(new_rolling_volatility, 0.5)
        self.rolling_volatility = new_rolling_volatility

        total_bid_vol = sum(buy_orders.values())
        total_ask_vol = -sum(sell_orders.values())
        imbalance = 0
        if (total_bid_vol + total_ask_vol) > 0:
            imbalance = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol)

        tick_size = 0
        spread_adjustment = new_rolling_volatility + tick_size

        if imbalance > 0.5:
            ask_price = current_price + (spread_adjustment + tick_size)
            bid_price = current_price - spread_adjustment
        elif imbalance < -0.5:
            ask_price = current_price + spread_adjustment
            bid_price = current_price - (spread_adjustment + tick_size)
        else:
            ask_price = current_price + spread_adjustment
            bid_price = current_price - spread_adjustment

        base_quantity = 50
        # if new_rolling_volatility > 5:
        #     base_quantity = 10
        # elif new_rolling_volatility < 1:
        #     base_quantity = 30
        quantity = base_quantity

        max_buy = min(quantity, self.limit - position)
        max_sell = min(quantity, self.limit + position)

        # If no best bid/ask or wide spread, restrict maximum orders.
        if best_bid is None or best_ask is None or ((best_ask - best_bid) > 4 * spread_adjustment):
            max_buy = min(max_buy, 2)
            max_sell = min(max_sell, 2)

        if max_buy > 0:
            self.buy(int(bid_price), max_buy)
        if max_sell > 0:
            self.sell(int(ask_price), max_sell)

        self.last_price = current_price

    def save(self) -> JSON:
        return {"last_price": self.last_price, "rolling_volatility": self.rolling_volatility}

    def load(self, data: JSON) -> None:
        if isinstance(data, dict):
            self.last_price = data.get("last_price", 10.0)
            self.rolling_volatility = data.get("rolling_volatility", 0.0)

###############################################################################
#                             TRADER CLASS                                  #
###############################################################################
class Trader:
    def __init__(self) -> None:
        limits = {
            "RAINFOREST_RESIN": 50,
            "KELP": 50,
            "SQUID_INK": 50
        }
        self.strategies = {symbol: clazz(symbol, limits[symbol]) for symbol, clazz in {
            "RAINFOREST_RESIN": RAINFORESTRESINStrategy,
            "KELP": KELPStrategy,
            "SQUID_INK": SQUIDINKStrategy
        }.items()}

    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        conversions = 0
        old_trader_data = json.loads(state.traderData) if state.traderData != "" else {}
        new_trader_data = {}

        orders = {}
        for symbol, strategy in self.strategies.items():
            if symbol in old_trader_data:
                strategy.load(old_trader_data.get(symbol, None))
            if symbol in state.order_depths:
                orders[symbol] = strategy.run(state)
            new_trader_data[symbol] = strategy.save()

        trader_data = json.dumps(new_trader_data, separators=(",", ":"))
        logger.flush(state, orders, conversions, trader_data)
        return orders, conversions, trader_data
