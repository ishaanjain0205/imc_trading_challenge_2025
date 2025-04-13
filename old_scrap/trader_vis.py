import json
import jsonpickle
from typing import List, Dict, Any
import statistics

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


class Trader:
    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        try:
            # Initialize result dictionary and conversion value
            result: Dict[str, List[Order]] = {}
            conversions = 0

            # Decode previous traderData (if available)
            previous_data = jsonpickle.decode(state.traderData) if state.traderData else {}
            new_data = {}

            # Parameters for fair value calculation
            alpha = 0.2  # Smoothing factor for exponential moving average

            # Loop over each product in the market state
            for product in state.order_depths:
                order_depth: OrderDepth = state.order_depths[product]
                orders: List[Order] = []

                # Get market order details
                buy_orders = order_depth.buy_orders
                sell_orders = order_depth.sell_orders

                # Find the best bid and best ask if available
                best_bid = max(buy_orders.keys()) if buy_orders else None
                best_ask = min(sell_orders.keys()) if sell_orders else None
                position = state.position.get(product, 0)

                # Compute current price: mid-price if both sides are available, otherwise fallback
                if best_bid is not None and best_ask is not None:
                    current_price = (best_bid + best_ask) / 2
                else:
                    current_price = previous_data.get(product, {}).get('fair_value', 10)

                # Retrieve price history and previous fair value for this product
                history = previous_data.get(product, {}).get('history', [])
                previous_fv = previous_data.get(product, {}).get('fair_value', current_price)
                history.append(current_price)
                # Keep only the last 5 prices
                if len(history) > 5:
                    history = history[-5:]
                
                # Compute volatility using standard deviation over the history
                if len(history) > 1:
                    try:
                        volatility = statistics.stdev(history)
                    except Exception:
                        volatility = abs(current_price - history[-2])
                else:
                    volatility = 0

                # Update fair value using exponential moving average (EMA)
                fair_value = alpha * current_price + (1 - alpha) * previous_fv

                # Calculate order imbalance from the order book volumes
                total_bid_vol = sum(buy_orders.values())
                total_ask_vol = -sum(sell_orders.values())
                imbalance = 0
                if (total_bid_vol + total_ask_vol) > 0:
                    imbalance = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol)

                tick_size = 1
                spread_adjustment = volatility + tick_size

                # Compute the deviation of the current price from fair value
                price_diff = current_price - fair_value

                # Set baseline bid and ask based on fair value
                bid_price = fair_value - spread_adjustment
                ask_price = fair_value + spread_adjustment

                # Adjust based on order imbalance
                if imbalance > 0.5:
                    ask_price = fair_value + (spread_adjustment + tick_size)
                    bid_price = fair_value - spread_adjustment
                elif imbalance < -0.5:
                    ask_price = fair_value + spread_adjustment
                    bid_price = fair_value - (spread_adjustment + tick_size)

                # Further adjust based on deviation: if current price is significantly above/below fair value
                if price_diff > 1:  # market appears overpriced
                    ask_price = current_price - tick_size  # sell aggressively
                elif price_diff < -1:  # market appears underpriced
                    bid_price = current_price + tick_size  # buy aggressively

                # Determine order quantity and adjust for market imbalance
                base_quantity = 5
                qty_adjustment = int(base_quantity * abs(imbalance))
                order_qty = base_quantity + qty_adjustment

                # Enforce position limits 
                position_limit = 20
                max_buy = min(order_qty, position_limit - position)
                max_sell = min(order_qty, position + position_limit)

                # Adjust for risk: if close to position limits, become more aggressive in clearing positions
                if position > position_limit * 0.8:
                    ask_price = current_price + spread_adjustment * 0.5
                    max_sell = order_qty
                    max_buy = 0
                elif position < -position_limit * 0.8:
                    bid_price = current_price - spread_adjustment * 0.5
                    max_buy = order_qty
                    max_sell = 0

                # Place orders if quantities are available
                if max_buy > 0:
                    orders.append(Order(product, int(bid_price), max_buy))
                if max_sell > 0:
                    orders.append(Order(product, int(ask_price), -max_sell))

                result[product] = orders

                # Save updated price history and fair value for the next iteration
                new_data[product] = {
                    'history': history,
                    'fair_value': fair_value
                }

            # Serialize state for next iteration
            traderData = jsonpickle.encode(new_data)

            logger.flush(state, result, conversions, traderData)
            return result, conversions, traderData
        except Exception as e:
            logger.print("Error in trader.run:", e)
            return {}, 0, ""