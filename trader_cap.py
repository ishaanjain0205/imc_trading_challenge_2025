from datamodel import OrderDepth, Order, TradingState
from typing import List, Dict
import jsonpickle

# Overfitted model parameters (trained offline)
model_params = {
    "KELP": {
        "intercept": 0.0011594331946658736,
        "linear": {
            "mid": 0.7804977931125856,
            "imbalance": 0.017077507182431822,
            "bid_vol": 0.653922880681153,
            "ask_vol": -0.9937201574492769
        },
        "quadratic": {
            "mid^2": 0.00022238930699497577,
            "imbalance^2": 0.3752790892334634,
            "bid_vol^2": 0.001392884441082223,
            "ask_vol^2": -0.008910741311448683
        },
        "cubic": {
            "mid^3": -5.625121501629271e-08,
            "imbalance^3": 0.04341658895639751,
            "bid_vol^3": -3.741526270695507e-05,
            "ask_vol^3": 0.00017996419524654326
        },
        "interaction": {
            "mid*imbalance": 0.00045007627367088797,
            "mid*bid_vol": -0.0002991142358336581,
            "mid*ask_vol": 0.0005203169437946474,
            "imbalance*bid_vol": 0.01642218390219515,
            "imbalance*ask_vol": -0.013605139858170816,
            "bid_vol*ask_vol": 0.00016257071222626246
        }
    },
    "RAINFOREST_RESIN": {
        "intercept": 3.850993759742502e-12,
        "linear": {
            "mid": 4.291618292826162e-08,
            "imbalance": -4.118431493591833e-08,
            "bid_vol": 8.57876547586767e-08,
            "ask_vol": 2.4741112296814025e-07
        },
        "quadratic": {
            "mid^2": 0.00030079054392480396,
            "imbalance^2": 9.07487028936893e-05,
            "bid_vol^2": -0.0014292238428086257,
            "ask_vol^2": -0.005153445755103978
        },
        "cubic": {
            "mid^3": -2.00790730258549e-08,
            "imbalance^3": -0.0005795388303500877,
            "bid_vol^3": 2.017653393146523e-05,
            "ask_vol^3": 0.00010299198660984027
        },
        "interaction": {
            "mid*imbalance": 5.46327601441065e-06,
            "mid*bid_vol": 3.9272520382941385e-06,
            "mid*ask_vol": 7.115799712290214e-06,
            "imbalance*bid_vol": 0.0026546204201686905,
            "imbalance*ask_vol": -0.000481902547438404,
            "bid_vol*ask_vol": 0.00018888857181246997
        }
    }
}


class Trader:
    def run(self, state: TradingState):
        try:
            result: Dict[str, List[Order]] = {}
            conversions = 0

            # Decode previous state (if any); can be used for persistence if needed.
            previous_data = jsonpickle.decode(state.traderData) if state.traderData else {}
            new_data = {}

            for product in state.order_depths:
                order_depth: OrderDepth = state.order_depths[product]
                orders: List[Order] = []

                # Extract best bid, best ask, and their volumes
                buy_orders = order_depth.buy_orders
                sell_orders = order_depth.sell_orders

                best_bid = max(buy_orders.keys()) if buy_orders else None
                best_ask = min(sell_orders.keys()) if sell_orders else None

                # Current mid price: use mid if both sides are available; fallback otherwise.
                if best_bid is not None and best_ask is not None:
                    current_mid = (best_bid + best_ask) / 2
                else:
                    current_mid = previous_data.get(product, {}).get('last_mid', 10)

                # Extract volumes at the best bid/ask levels (default to 0 if missing)
                bid_vol = buy_orders.get(best_bid, 0) if best_bid is not None else 0
                ask_vol = -sell_orders.get(best_ask, 0) if best_ask is not None else 0

                # Compute a simple imbalance feature: difference between best bid and ask
                imbalance = (best_bid - best_ask) if (best_bid is not None and best_ask is not None) else 0

                # --- Super Overfitted Model Prediction ---
                if product in model_params:
                    params = model_params[product]
                    prediction = params["intercept"]
                    # Linear terms
                    prediction += params["linear"]["mid"] * current_mid
                    prediction += params["linear"]["imbalance"] * imbalance
                    prediction += params["linear"]["bid_vol"] * bid_vol
                    prediction += params["linear"]["ask_vol"] * ask_vol
                    # Quadratic terms
                    prediction += params["quadratic"]["mid^2"] * (current_mid ** 2)
                    prediction += params["quadratic"]["imbalance^2"] * (imbalance ** 2)
                    prediction += params["quadratic"]["bid_vol^2"] * (bid_vol ** 2)
                    prediction += params["quadratic"]["ask_vol^2"] * (ask_vol ** 2)
                    # Cubic terms
                    prediction += params["cubic"]["mid^3"] * (current_mid ** 3)
                    prediction += params["cubic"]["imbalance^3"] * (imbalance ** 3)
                    prediction += params["cubic"]["bid_vol^3"] * (bid_vol ** 3)
                    prediction += params["cubic"]["ask_vol^3"] * (ask_vol ** 3)
                    # Interaction terms
                    prediction += params["interaction"]["mid*imbalance"] * (current_mid * imbalance)
                    prediction += params["interaction"]["mid*bid_vol"] * (current_mid * bid_vol)
                    prediction += params["interaction"]["mid*ask_vol"] * (current_mid * ask_vol)
                    prediction += params["interaction"]["imbalance*bid_vol"] * (imbalance * bid_vol)
                    prediction += params["interaction"]["imbalance*ask_vol"] * (imbalance * ask_vol)
                    prediction += params["interaction"]["bid_vol*ask_vol"] * (bid_vol * ask_vol)
                    predicted_future_mid = prediction
                else:
                    predicted_future_mid = current_mid

                # --- Decision Logic ---
                # Use the difference between predicted future mid and current mid to decide on orders.
                diff = predicted_future_mid - current_mid
                order_qty = max(5, int(abs(diff)))  # Scale order size with magnitude of difference

                # Get current position and enforce position limits (assumed limit: 20)
                position = state.position.get(product, 0)
                position_limit = 20

                if diff > 0 and position < position_limit:
                    # Expecting price increase -> buy at best bid
                    order_price = best_bid if best_bid is not None else int(current_mid)
                    orders.append(Order(product, int(order_price), order_qty))
                elif diff < 0 and position > -position_limit:
                    # Expecting price decrease -> sell at best ask
                    order_price = best_ask if best_ask is not None else int(current_mid)
                    orders.append(Order(product, int(order_price), -order_qty))

                result[product] = orders
                new_data[product] = {'last_mid': current_mid}

            traderData = jsonpickle.encode(new_data)
            return result, conversions, traderData

        except Exception as e:
            print("Error in trader.run:", e)
            return {}, 0, ""
