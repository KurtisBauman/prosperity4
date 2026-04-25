from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List

class Trader:
    """
    Round 2 Optimized Trader
    ========================
    Backtested over 3 days of Round 2 data.

    Expected PNL  : ~6,170,000
    Breakdown     : Osmium ~5,930,000 | Pepper ~240,000

    Key findings from data analysis:
    ─────────────────────────────────
    ASH_COATED_OSMIUM
      • Dominant market maker always quotes at mid ± 8 ticks (spread = 16).
      • bid_price_1 is always ~mid - 8, ask_price_1 always ~mid + 8.
      • MAKE at bb+1 / ba-1 captures ~14 ticks per round-trip.
      • Optimal quote size = 15 lots per side (grid-searched; 12 undersizes,
        18+ overshoots inventory too often).
      • Soft cap 65 / hard cap 80.
      • TAKE logic removed — ask1 > mid and bid1 < mid always, so the
        old take block never fired (dead code). Pure market-making is optimal.
      • Order imbalance (bid_vol vs ask_vol) has ~1.5-2.5 tick predictive
        power but is already fully captured by the make strategy fill timing;
        adding a separate imbalance-take layer adds no edge.

    INTARIAN_PEPPER_ROOT
      • Confirmed +1000/day drift (+0.1/tick) across all 3 days (r²≈1.0).
      • Going SHORT loses ~240k over 3 days; stay MAX LONG.
      • Take all available ask liquidity immediately, passive bid for remainder.
    """

    PARAMS = {
        "ASH_COATED_OSMIUM": {
            "limit":    80,
            "size":     15,   # optimal: grid-searched (12→4.74M, 15→5.93M, 18→5.49M)
            "soft_cap": 65,   # suppress new quotes beyond this
            "hard_cap": 80,   # flip to dump/absorb mode
        },
        "INTARIAN_PEPPER_ROOT": {
            "limit": 80,      # go max long immediately, hold all day
        },
    }

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _best_bid_ask(self, depth: OrderDepth):
        bb = max(depth.buy_orders.keys())  if depth.buy_orders  else None
        ba = min(depth.sell_orders.keys()) if depth.sell_orders else None
        return bb, ba

    def _wall_mid(self, depth: OrderDepth):
        """
        Fair value from the deepest (weakest) bid and ask levels.
        Filters out thin one-lot noise at the top of book.
        """
        if not depth.buy_orders or not depth.sell_orders:
            return None
        bid_wall = min(depth.buy_orders.keys())
        ask_wall = max(depth.sell_orders.keys())
        return (bid_wall + ask_wall) / 2

    # ------------------------------------------------------------------ #
    #  ASH_COATED_OSMIUM  –  pure spread capture, optimal size            #
    # ------------------------------------------------------------------ #

    def _trade_osmium(self, depth: OrderDepth, position: int, params: dict):
        orders = []
        bb, ba = self._best_bid_ask(depth)
        if bb is None or ba is None:
            return orders

        fair = self._wall_mid(depth)
        if fair is None:
            return orders

        buy_limit  = params["limit"] - position
        sell_limit = params["limit"] + position

        # ── MAKE: penny-improve best bid/ask ────────────────────────────
        # Dominant MM always quotes mid±8; penny-improving puts us inside
        # their spread, capturing ~14 ticks per round-trip at size 15.
        bid_q = bb + 1 if ba > bb + 1 else bb
        ask_q = ba - 1 if ba > bb + 1 else ba

        quote_bid = position < params["soft_cap"] and buy_limit > 0
        quote_ask = position > -params["soft_cap"] and sell_limit > 0

        # Hard-cap: flip to aggressive dump/absorb to flatten inventory
        if position >= params["hard_cap"]:
            quote_bid = False
            ask_q = bb          # undercut best bid to dump faster
        elif position <= -params["hard_cap"]:
            quote_ask = False
            bid_q = ba          # overbid best ask to absorb faster

        if quote_bid:
            orders.append(Order("ASH_COATED_OSMIUM",
                                int(bid_q),
                                min(params["size"], buy_limit)))
        if quote_ask:
            orders.append(Order("ASH_COATED_OSMIUM",
                                int(ask_q),
                                -min(params["size"], sell_limit)))

        return orders

    # ------------------------------------------------------------------ #
    #  INTARIAN_PEPPER_ROOT  –  max long, hold                            #
    # ------------------------------------------------------------------ #

    def _trade_pepper(self, depth: OrderDepth, position: int, params: dict):
        """
        +1000/day drift confirmed (r²≈1.0 across all 3 days).
        Spread (~13 ticks) recouped within ~130 ticks of drift.
        Take all available asks; passive bid for remaining capacity.
        Never sell — going short costs ~240k over 3 days.
        """
        orders = []
        bb, ba = self._best_bid_ask(depth)
        if bb is None or ba is None:
            return orders

        buy_limit = params["limit"] - position
        if buy_limit <= 0:
            return orders

        # Aggressively take all ask-side liquidity (all 3 levels)
        for ask_px in sorted(depth.sell_orders.keys()):
            if buy_limit <= 0:
                break
            qty = min(-depth.sell_orders[ask_px], buy_limit)
            orders.append(Order("INTARIAN_PEPPER_ROOT", ask_px, qty))
            buy_limit -= qty

        # Passive bid for remaining capacity
        if buy_limit > 0:
            orders.append(Order("INTARIAN_PEPPER_ROOT", bb + 1, buy_limit))

        return orders

    # ------------------------------------------------------------------ #
    #  Entry point                                                         #
    # ------------------------------------------------------------------ #

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