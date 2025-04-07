from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import jsonpickle
import json
from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
from typing import Any

def calc_mid_price(bid, ask):
    return (bid + ask) / 2.0

class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
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
                compressed.append([
                    trade.symbol,
                    trade.price,
                    trade.quantity,
                    trade.buyer,
                    trade.seller,
                    trade.timestamp,
                ])
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
                observation.sunlight,
                observation.humidity,
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
        return value[:max_length - 3] + "..."

logger = Logger()

class Trader:
    def __init__(self):
        self.mid_prices = []
        self.mid_prices_MAX_len = 300
        self.emwa = 0
        self.default_volaitlity = 1.0
        self.low_volatilty_thresh = 0.55
        self.high_volatility_thresh = 2.90

    def run(self, state: TradingState):
        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))
        result = {}

        product = "RAINFOREST_RESIN"
        order_depth = state.order_depths[product]
        orders = []

        if state.traderData != "SAMPLE" and state.traderData != "":
            data = jsonpickle.decode(state.traderData)
            self.mid_prices = data.get("mid_prices", [])
            self.emwa = data.get("emwa", 0.0)

        best_bid = None
        best_bid_quantity = None
        best_ask = None
        best_ask_quantity = None

        if len(order_depth.buy_orders) != 0:
            bid, quantity = list(order_depth.buy_orders.items())[0]
            best_bid = bid
            best_bid_quantity = quantity

        if len(order_depth.sell_orders) != 0:
            ask, amount = list(order_depth.sell_orders.items())[0]
            best_ask = ask
            best_ask_quantity = amount

        current_mid_price = calc_mid_price(best_bid, best_ask)
        self.mid_prices.append(current_mid_price)
        if len(self.mid_prices) > self.mid_prices_MAX_len:
            self.mid_prices.pop(0)

        volatility = None
        if len(self.mid_prices) < self.mid_prices_MAX_len:
            self.emwa = self.default_volaitlity
            volatility = self.default_volaitlity
        else:
            prev_mid_price = self.mid_prices[-2]
            mid_price_diff = current_mid_price - prev_mid_price
            alpha = 0.94
            prev_emwa = self.emwa
            self.emwa = (1 - alpha) * prev_emwa + alpha * (mid_price_diff ** 2)
            volatility = self.emwa ** 0.5

        spread = 2.0
        quantity = 10
        if volatility < self.low_volatilty_thresh:
            spread = 4.0
            quantity = 15
        elif volatility > self.high_volatility_thresh:
            spread = 20.0
            quantity = 5
        else:
            spread = 6.0
            quantity = 10

        bid_price = None
        ask_price = None
        if best_ask - best_bid > spread:
            bid_price = best_bid + 1
            ask_price = best_ask - 1
        else:
            bid_price = current_mid_price - (spread / 2)
            ask_price = current_mid_price + (spread / 2)

        current_position = state.position.get(product, 0)
        max_pos = 50

               # Adjust bid/ask to reduce inventory risk
        inventory_ratio = current_position / max_pos
        if inventory_ratio > 0.5:
            ask_price = min(ask_price, best_ask - 1)
        elif inventory_ratio < -0.5:
            bid_price = max(bid_price, best_bid + 1)

        # Generate layered orders
        def generate_layered_orders(product, bid_price, ask_price, base_quantity, step, layers, max_pos, pos):
            orders = []
            qty_per_layer = base_quantity // layers

            # Buy layers
            buyable = max(0, max_pos - pos)
            for i in range(layers):
                price = int(round(bid_price - (i * step)))
                qty = min(qty_per_layer, buyable)
                if qty > 0:
                    orders.append(Order(product, price, qty))
                    buyable -= qty

            # Sell layers
            sellable = max(0, pos + max_pos)
            for i in range(layers):
                price = int(round(ask_price + (i * step)))
                qty = min(qty_per_layer, sellable)
                if qty > 0:
                    orders.append(Order(product, price, -qty))
                    sellable -= qty

            return orders

        step_size = max(1, round((best_ask - best_bid) / 4))
        orders = generate_layered_orders(product, bid_price, ask_price, quantity, step_size, 3, max_pos, current_position)

        result[product] = orders
        
        traderData = jsonpickle.encode({
            "mid_prices": self.mid_prices,
            "emwa": self.emwa
        })

        conversions = 0
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData