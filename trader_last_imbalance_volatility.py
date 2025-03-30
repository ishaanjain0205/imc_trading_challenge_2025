from datamodel import OrderDepth, Order, TradingState
from typing import List, Dict
import jsonpickle

class Trader:
    def run(self, state: TradingState):
        try:
            # Initialize result dictionary and conversion value
            result: Dict[str, List[Order]] = {}
            conversions = 0

            # Use traderData to recall previous state (if any)
            previous_data = jsonpickle.decode(state.traderData) if state.traderData else {}
            new_data = {}

            # Loop over each product in the market state
            for product in state.order_depths:
                order_depth: OrderDepth = state.order_depths[product]
                orders: List[Order] = []

                # Get market order details
                buy_orders = order_depth.buy_orders
                sell_orders = order_depth.sell_orders

                # Find the best bid and best ask (if available)
                best_bid = max(buy_orders.keys()) if buy_orders else None
                best_ask = min(sell_orders.keys()) if sell_orders else None
                position = state.position.get(product, 0)

                # Calculate current price as the mid-price if both sides are available
                if best_bid is not None and best_ask is not None:
                    current_price = (best_bid + best_ask) / 2
                else:
                    # Fallback: use the previous price or a default (10)
                    current_price = previous_data.get(product, 10)

                # Retrieve last price for volatility calculation
                last_price = previous_data.get(product, current_price)
                volatility = abs(current_price - last_price)

                # Calculate order imbalance from the order depth
                total_bid_vol = sum(buy_orders.values())
                total_ask_vol = -sum(sell_orders.values())
                imbalance = 0
                if (total_bid_vol + total_ask_vol) > 0:
                    imbalance = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol)

                tick_size = 1
                spread_adjustment = volatility + tick_size

                # Apply the "last+im+v" market making strategy:
                # Adjust order prices based on volatility (v) and order imbalance (im)
                if imbalance > 0.5:
                    ask_price = current_price + (spread_adjustment + tick_size)
                    bid_price = current_price - spread_adjustment
                elif imbalance < -0.5:
                    ask_price = current_price + spread_adjustment
                    bid_price = current_price - (spread_adjustment + tick_size)
                else:
                    ask_price = current_price + spread_adjustment
                    bid_price = current_price - spread_adjustment

                # Set a fixed order quantity (this can be refined)
                quantity = 5

                # Enforce position limits (assuming a limit of 20 for demonstration)
                position_limit = 20
                max_buy = min(quantity, position_limit - position)
                max_sell = min(quantity, position + position_limit)

                if max_buy > 0:
                    orders.append(Order(product, int(bid_price), max_buy))
                if max_sell > 0:
                    orders.append(Order(product, int(ask_price), -max_sell))

                result[product] = orders
                new_data[product] = current_price  # Save the current price for the next iteration

            # Serialize state for the next iteration using jsonpickle
            traderData = jsonpickle.encode(new_data)
            return result, conversions, traderData

        except Exception as e:
            print("Error in trader.run:", e)
            # Return a default tuple if an error occurs to prevent unpacking errors
            return {}, 0, ""
