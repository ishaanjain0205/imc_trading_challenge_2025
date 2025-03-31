from datamodel import OrderDepth, Order, TradingState
from typing import List, Dict
import jsonpickle
import statistics

class Trader:
    def run(self, state: TradingState):
        try:
            # Initialize result dictionary and conversion value
            result: Dict[str, List[Order]] = {}
            conversions = 0

            # Decode previous traderData (if available)
            previous_data = jsonpickle.decode(state.traderData) if state.traderData else {}
            new_data = {}

            # Parameters for fair value calculation
            alpha = 0.1  # Smoothing factor for exponential moving average

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
            return result, conversions, traderData

        except Exception as e:
            print("Error in trader.run:", e)
            return {}, 0, ""
