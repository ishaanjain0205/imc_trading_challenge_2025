from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string

MAX_POSITION = 50
FIXED_SPREAD = 3

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
            order_size = 5
            
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
        conversions = 1
        
        return result, conversions, traderData