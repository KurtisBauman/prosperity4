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

    def run(self, state: TradingState):
        result = {}

        for product, params in self.PARAMS.items():
            depth = state.order_depths.get(product)
            if not depth: continue
            
            position = state.position.get(product, 0)
            orders = []
            bb, ba = self._best_bid_ask(depth)
            
            # --- PRICE DISCOVERY LOGIC ---
            if bb is None or ba is None: continue
            bid_px = bb + 1 if ba > bb + 1 else bb
            ask_px = ba - 1 if ba > bb + 1 else ba
            
            # --- TRADING LIMITS & QUOTING ---
            buy_limit = params["limit"] - position
            sell_limit = params["limit"] + position

            quote_bid = position < params["soft_cap"] and buy_limit > 0
            quote_ask = position > -params["soft_cap"] and sell_limit > 0

            # --- INVENTORY RISK MANAGEMENT ---
            if position >= params["hard_cap"]:
                quote_bid = False
                # If we're too long, we become the best seller (cross the spread)
                if bb is not None: ask_px = bb 
            elif position <= -params["hard_cap"]:
                quote_ask = False
                # If we're too short, we become the best buyer
                if ba is not None: bid_px = ba

            # --- ORDER PLACEMENT ---
            if quote_bid:
                # Use params["size"] for Osmium to ensure consistent fills
                vol = params["size"] if product == "ASH_COATED_OSMIUM" else depth.buy_orders[bb]
                orders.append(Order(product, int(bid_px), min(vol, buy_limit)))
            
            if quote_ask:
                vol = params["size"] if product == "ASH_COATED_OSMIUM" else depth.sell_orders[ba]
                orders.append(Order(product, int(ask_px), -min(vol, sell_limit)))

            result[product] = orders

        return result, 0, ""