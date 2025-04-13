from imc_trading_challenge_2025.ishaan.scrap.datamodel_SAMPLE import OrderDepth, UserId, TradingState, Order
from typing import List
import string
from imc_trading_challenge_2025.ishaan.scrap.datamodel_SAMPLE import Listing, OrderDepth, Trade, TradingState

# TESTING FILE NAME
from imc_trading_challenge_2025.ishaan.scrap.dynamic_spread_mm import Trader
# WORK ON THIS FILE
# RUN FUNCTION => FUNCTION TO MODIFY, EXECUTES OUR TRADES


# class Trader:
    
#     def run(self, state: TradingState):
#         # Only method required. It takes all buy and sell orders for all symbols as an input, and outputs a list of orders to be sent
#         print("traderData: " + state.traderData)
#         print("Observations: " + str(state.observations))
#         result = {}
#         for product in state.order_depths:
#             print(product)
#             order_depth: OrderDepth = state.order_depths[product]
#             orders: List[Order] = []
#             acceptable_price = 10;  # Participant should calculate this value


#             bid_price = None # OPTIMAL BID PRICE DYNAMICALLY UPDATED
#             ask_price = None # OPTIMAL ASK PRICE DYNAMICALLY UPDATED
            
#             print("Acceptable price : " + str(acceptable_price))
#             print("Buy Order depth : " + str(len(order_depth.buy_orders)) + ", Sell order depth : " + str(len(order_depth.sell_orders)))
            
#             if len(order_depth.sell_orders) != 0:
#                 best_ask, best_ask_amount = list(order_depth.sell_orders.items())[0]
#                 if int(best_ask) < acceptable_price:
#                     print("BUY", str(-best_ask_amount) + "x", best_ask)
#                     orders.append(Order(product, best_ask, -best_ask_amount))
    
#             if len(order_depth.buy_orders) != 0:
#                 best_bid, best_bid_amount = list(order_depth.buy_orders.items())[0]
#                 if int(best_bid) > acceptable_price:
#                     print("SELL", str(best_bid_amount) + "x", best_bid)
#                     orders.append(Order(product, best_bid, -best_bid_amount))
            
#             result[product] = orders
    
    
#         traderData = "SAMPLE" # String value holding Trader state data required. It will be delivered as TradingState.traderData on next execution.
        
#         conversions = 1
#         return result, conversions, traderData

def main():

    timestamp = 1000

    listings = {
        "RAINFOREST_RESIN": Listing(
            symbol="RAINFOREST_RESIN", 
            product="RAINFOREST_RESIN", 
            denomination= "SEASHELLS"
        ),
        "KELP": Listing(
            symbol="KELP", 
            product="KELP", 
            denomination= "SEASHELLS"
        ),
    }

    od1 = OrderDepth()
    # 7 buy orders at price 10
    od1.buy_orders = {10: 7, 9: 5}
    od1.sell_orders = {11: -4, 12: -8}

    od2 = OrderDepth()
    od2.buy_orders = {142: 3, 141: 5}
    od2.sell_orders = {144: -5, 145: -8}

    order_depths = {
        "RAINFOREST_RESIN": od1,
        "KELP": od2,
    }

    own_trades = {
        "RAINFOREST_RESIN": [],
        "KELP": []
    }

    market_trades = {
        "RAINFOREST_RESIN": [
            Trade(
                symbol="RAINFOREST_RESIN",
                price=11,
                quantity=4,
                buyer="",
                seller="",
                timestamp=900
            )
        ],
        "KELP": []
    }

    position = {
        "RAINFOREST_RESIN": 3,
        "KELP": -5
    }

    observations = {}
    traderData = ""

    state = TradingState(
        traderData,
        timestamp,
        listings,
        order_depths,
        own_trades,
        market_trades,
        position,
        observations
    )

    print("LISTINGS")
    for product, listing in state.listings.items():
        print(f"{product}: symbol={listing.symbol}, product={listing.product}, denomination={listing.denomination}")
    print()

    print("ORDER DEPTHS:")
    for product, depth in state.order_depths.items():
        print(f"{product}:")
        print(f"  Buy Orders: {depth.buy_orders}")
        print(f"  Sell Orders: {depth.sell_orders}")
    print()

    print("OWN TRADES:")
    for product, trades in state.own_trades.items():
        print(f"{product}: {trades}")
    print()

    print("MARKET TRADES:")
    for product, trades in state.market_trades.items():
        print(f"{product}:")
        for trade in trades:
            print(f"  (symbol={trade.symbol}, price={trade.price}, quantity={trade.quantity}, buyer={trade.buyer}, seller={trade.seller}, timestamp={trade.timestamp})")
    print()

    print("POSITION:")
    for product, pos in state.position.items():
        print(f"{product}: {pos}")
    print()

    print("OBSERVATIONS:")
    print(state.observations)
    print()
    
    trader = Trader()
    result, conversions, traderData = trader.run(state)
    



if __name__ == "__main__":
    main()