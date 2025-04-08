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

            # Parameters
            alpha = 0.20  # Smoothing factor for exponential moving average
            position_limit = 50
            base_quantity = 5

            # Known price band for mean reversion
            LOWER_BOUND = 9996
            UPPER_BOUND = 10004
            BOUND_TOLERANCE = 2   # How close we have to be to an edge to trade more aggressively

            for product in state.order_depths:
            
               

                order_depth: OrderDepth = state.order_depths[product]
                orders: List[Order] = []

                buy_orders = order_depth.buy_orders
                sell_orders = order_depth.sell_orders

                # Identify best bid and best ask
                best_bid = max(buy_orders.keys()) if buy_orders else None
                best_ask = min(sell_orders.keys()) if sell_orders else None
                position = state.position.get(product, 0)

                # -----------------------------------------
                # 2) Compute a simple 'current price' basis
                # -----------------------------------------
                if best_bid is not None and best_ask is not None:
                    current_price = (best_bid + best_ask) / 2
                else:
                    # Fallback
                    current_price = previous_data.get(product, {}).get('fair_value', 10_000)

                # -----------------------------------------
                # 3) Track history for volatility / EMA
                # -----------------------------------------
                history = previous_data.get(product, {}).get('history', [])
                previous_fv = previous_data.get(product, {}).get('fair_value', current_price)
                history.append(current_price)
                if len(history) > 4:
                    history = history[-4:]

                # Compute volatility (std dev over last prices)
                if len(history) > 1:
                    try:
                        volatility = statistics.stdev(history)
                    except Exception:
                        volatility = abs(current_price - history[-2])
                else:
                    volatility = 0

                # Exponential moving average as "fair value"
                fair_value = alpha * current_price + (1 - alpha) * previous_fv

                # -----------------------------------------
                # 4) Range-based mean reversion logic
                #    - If near lower bound, buy more
                #    - If near upper bound, sell more
                # -----------------------------------------
                # Decide how aggressive to be when near edges
                near_lower = (current_price <= (LOWER_BOUND + BOUND_TOLERANCE))
                near_upper = (current_price >= (UPPER_BOUND - BOUND_TOLERANCE))

                # Base limit prices around fair_value plus a small “spread_adjustment”
                tick_size = 1
                spread_adjustment = max(1, volatility)  # At least 1 to keep a decent spread

                bid_price = fair_value - spread_adjustment
                ask_price = fair_value + spread_adjustment

                # If we are near the lower bound, push bid up (we want to buy more aggressively)
                if near_lower:
                    bid_price = min(bid_price + tick_size, current_price)
                
                # If we are near the upper bound, push ask down (we want to sell more aggressively)
                if near_upper:
                    ask_price = max(ask_price - tick_size, current_price)

                # -----------------------------------------
                # 5) Position sizing
                # -----------------------------------------
                # By default, order_qty is base_quantity
                order_qty = base_quantity

                # If we're near the lower bound, we might increase buy size
                if near_lower:
                    order_qty *= 4  # buy double if at the bottom
                # If we're near the upper bound, we might increase sell size
                if near_upper:
                    order_qty *= 4  # sell double if at the top

                # Clip to position limits
                max_buy = min(order_qty, position_limit - position)
                max_sell = min(order_qty, position + position_limit)

                # -----------------------------------------
                # 6) Place limit orders (Market-Making)
                # -----------------------------------------
                # Only place buy if we haven't hit the long-side limit
                if max_buy > 0:
                    orders.append(Order(product, int(bid_price), max_buy))
                # Only place sell if we haven't hit the short-side limit
                if max_sell > 0:
                    orders.append(Order(product, int(ask_price), -max_sell))

                # -----------------------------------------
                # 7) Optional: Check for cross (best_bid > best_ask)
                #    This snippet tries to do an arbitrage if mispriced
                # -----------------------------------------
                if best_bid is not None and best_ask is not None and best_bid > best_ask:
                    available_bid_vol = buy_orders[best_bid]
                    available_ask_vol = -sell_orders[best_ask]  # negative in the book, so take absolute
                    arbitrage_volume = min(available_bid_vol, available_ask_vol)
                    
                    # Maximum we can buy or sell without violating limits
                    max_arbitrage_buy = position_limit - position
                    max_arbitrage_sell = position + position_limit
                    arbitrage_volume = min(arbitrage_volume, max_arbitrage_buy, max_arbitrage_sell)

                    if arbitrage_volume > 0:
                        orders.append(Order(product, int(best_ask), arbitrage_volume))
                        orders.append(Order(product, int(best_bid), -arbitrage_volume))

                # Store the final orders for RAINFOREST RESIN
                result[product] = orders

                # Save updated info for next iteration
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
