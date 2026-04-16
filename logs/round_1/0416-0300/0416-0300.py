from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Tuple

class Trader:
    PARAMS = {
        "ASH_COATED_OSMIUM": {
            "limit": 80,      
            "size": 15,       
            "soft_cap": 72,   
            "hard_cap": 75    
        },
        "INTARIAN_PEPPER_ROOT": {
            "limit": 80,      
            "size": 12,       
            "soft_cap": 72, 
            "hard_cap": 75
        },
    }

    def _best_bid_ask(self, depth: OrderDepth):
        bb = max(depth.buy_orders.keys()) if depth.buy_orders else None
        ba = min(depth.sell_orders.keys()) if depth.sell_orders else None
        return bb, ba
    
    def _wall_mid(self, depth: OrderDepth):
        """Fair value from deepest liquidity levels (more stable than best bid/ask mid as shown by top teams in P3)."""
        if not depth.buy_orders or not depth.sell_orders:
            return None
        bid_wall = min(depth.buy_orders.keys())
        ask_wall = max(depth.sell_orders.keys())
        return (bid_wall + ask_wall) / 2

    def _trade_osmium(self, depth: OrderDepth, position: int, params: dict):
        orders = []
        bb, ba = self._best_bid_ask(depth)
        if bb is None or ba is None:
            return orders

        fair = self._wall_mid(depth)
        if fair is None:
            return orders

        buy_limit = params["limit"] - position
        sell_limit = params["limit"] + position

        # --- TAKE: sweep mispriced orders ---
        for ask_px in sorted(depth.sell_orders.keys()):
            if ask_px < fair and buy_limit > 0:
                qty = min(-depth.sell_orders[ask_px], buy_limit)
                orders.append(Order("ASH_COATED_OSMIUM", ask_px, qty))
                buy_limit -= qty

        for bid_px in sorted(depth.buy_orders.keys(), reverse=True):
            if bid_px > fair and sell_limit > 0:
                qty = min(depth.buy_orders[bid_px], sell_limit)
                orders.append(Order("ASH_COATED_OSMIUM", bid_px, -qty))
                sell_limit -= qty

        # --- MAKE: penny best bid/ask ---
        bid_px = bb + 1 if ba > bb + 1 else bb
        ask_px = ba - 1 if ba > bb + 1 else ba

        quote_bid = position < params["soft_cap"] and buy_limit > 0
        quote_ask = position > -params["soft_cap"] and sell_limit > 0

        if position >= params["hard_cap"]:
            quote_bid = False
            ask_px = bb
        elif position <= -params["hard_cap"]:
            quote_ask = False
            bid_px = ba

        if quote_bid:
            orders.append(Order("ASH_COATED_OSMIUM", int(bid_px), min(params["size"], buy_limit)))
        if quote_ask:
            orders.append(Order("ASH_COATED_OSMIUM", int(ask_px), -min(params["size"], sell_limit)))

        return orders
    
    def _trade_pepper(self, depth: OrderDepth, position: int, params: dict):
        """PEPPER_ROOT drifts +1000/day. Go max long ASAP, hold."""
        orders = []
        bb, ba = self._best_bid_ask(depth)
        if bb is None or ba is None:
            return orders

        buy_limit = params["limit"] - position

        # Take all available asks — spread cost (~13) recouped in ~130 ticks of drift
        for ask_px in sorted(depth.sell_orders.keys()):
            if buy_limit <= 0:
                break
            qty = min(-depth.sell_orders[ask_px], buy_limit)
            orders.append(Order("INTARIAN_PEPPER_ROOT", ask_px, qty))
            buy_limit -= qty

        # Passive bid for any remaining capacity
        if buy_limit > 0:
            orders.append(Order("INTARIAN_PEPPER_ROOT", bb + 1, buy_limit))

        return orders


    def run(self, state: TradingState):
        result = {}
        for product, params in self.PARAMS.items():
            depth = state.order_depths.get(product)
            if not depth:
                continue
            position = state.position.get(product, 0)
            if product == "ASH_COATED_OSMIUM":
                result[product] = self._trade_osmium(depth, position, params)
            else:
                result[product] = self._trade_pepper(depth, position, params)
        return result, 0, ""