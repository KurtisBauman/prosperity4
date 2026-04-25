import math
import os
from typing import Dict, List, Optional

import jsonpickle

from datamodel import Order, OrderDepth, TradingState


class Trader:
    """Round 3 initial trader: delta-one fair-value taking plus BS voucher taking."""

    USE_SPOT_BRACKET = False
    USE_DIAGNOSTICS = True

    HYDROGEL = "HYDROGEL_PACK"
    VELVET = "VELVETFRUIT_EXTRACT"
    ACTIVE_VOUCHERS = [
        "VEV_4000",
        "VEV_4500",
        "VEV_5000",
        "VEV_5100",
        "VEV_5200",
        "VEV_5300",
        "VEV_5400",
        "VEV_5500",
    ]

    LIMITS = {
        HYDROGEL: 200,
        VELVET: 200,
        "VEV_4000": 300,
        "VEV_4500": 300,
        "VEV_5000": 300,
        "VEV_5100": 300,
        "VEV_5200": 300,
        "VEV_5300": 300,
        "VEV_5400": 300,
        "VEV_5500": 300,
    }

    DELTA_ONE_CONFIG = {
        HYDROGEL: {"anchor": 9991.0, "anchor_wt": 0.3, "edge": 0.5},
        VELVET: {"anchor": 5250.0, "anchor_wt": 0.3, "edge": 0.5},
    }

    VOUCHER_EDGE = 1.0
    DAYS_AT_START = {0: 8.0, 1: 7.0, 2: 6.0}

    VOUCHER_SIGMA = {
        "VEV_4000": 0.79,
        "VEV_4500": 0.45,
        "VEV_5000": 0.2330,
        "VEV_5100": 0.2308,
        "VEV_5200": 0.2334,
        "VEV_5300": 0.2359,
        "VEV_5400": 0.2211,
        "VEV_5500": 0.2398,
    }

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _best_bid_ask(self, depth: OrderDepth):
        best_bid = max(depth.buy_orders) if depth.buy_orders else None
        best_ask = min(depth.sell_orders) if depth.sell_orders else None
        return best_bid, best_ask

    def _wall_mid(self, depth: OrderDepth) -> Optional[float]:
        """Volume-weighted best bid/ask midpoint using side totals as weights."""
        best_bid, best_ask = self._best_bid_ask(depth)
        if best_bid is None or best_ask is None:
            return None

        bid_volume = sum(depth.buy_orders.values())
        ask_volume = sum(-volume for volume in depth.sell_orders.values())
        total_volume = bid_volume + ask_volume
        if total_volume <= 0:
            return (best_bid + best_ask) / 2.0

        return (best_bid * ask_volume + best_ask * bid_volume) / total_volume

    def _time_to_expiry(self, timestamp: int) -> float:
        del timestamp
        day_value = os.getenv("PROSPERITY3BT_DAY")
        try:
            day_num = int(day_value) if day_value is not None else None
        except ValueError:
            day_num = None

        # Historical books are most consistent with a day-level TTE surface,
        # not intraday decay, so keep T fixed within each backtest day.
        return self.DAYS_AT_START.get(day_num, 5.0) / 365.0

    def _norm_cdf(self, x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def _bs_call(self, spot: float, strike: int, time_years: float, sigma: float) -> float:
        if time_years <= 0.0 or sigma <= 1e-12:
            return max(spot - strike, 0.0)
        if spot <= 0.0:
            return 0.0

        vol_term = sigma * math.sqrt(time_years)
        if vol_term <= 1e-12:
            return max(spot - strike, 0.0)

        d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * time_years) / vol_term
        d2 = d1 - vol_term
        return spot * self._norm_cdf(d1) - strike * self._norm_cdf(d2)

    def _implied_vol(
        self,
        price: float,
        spot: float,
        strike: int,
        time_years: float,
        lo: float = 0.01,
        hi: float = 3.0,
    ) -> float:
        intrinsic = max(spot - strike, 0.0)
        if time_years <= 0.0 or price <= intrinsic:
            return 0.0

        left = lo
        right = hi
        for _ in range(30):
            mid = (left + right) / 2.0
            mid_price = self._bs_call(spot, strike, time_years, mid)
            if mid_price < price:
                left = mid
            else:
                right = mid
        return (left + right) / 2.0

    def _deserialize_memory(self, trader_data: str) -> dict:
        try:
            memory = jsonpickle.decode(trader_data) if trader_data else {}
        except Exception:
            memory = {}
        if not isinstance(memory, dict):
            memory = {}

        memory.setdefault("diag", {})
        memory.setdefault("last_trade_ts", {})
        memory.setdefault("last_fair", {})
        return memory

    def _update_diagnostics(self, state: TradingState, memory: dict) -> None:
        if not self.USE_DIAGNOSTICS:
            return

        diag = memory["diag"]
        last_trade_ts = memory["last_trade_ts"]
        last_fair = memory["last_fair"]

        tracked_products = [self.HYDROGEL, self.VELVET] + self.ACTIVE_VOUCHERS
        for product in tracked_products:
            product_diag = diag.setdefault(
                product,
                {"fill_count": 0, "fill_qty": 0, "edge_sum": 0.0, "max_abs_pos": 0},
            )
            product_diag["max_abs_pos"] = max(
                product_diag["max_abs_pos"],
                abs(state.position.get(product, 0)),
            )

        for product, trades in state.own_trades.items():
            if not trades:
                continue

            product_diag = diag.setdefault(
                product,
                {"fill_count": 0, "fill_qty": 0, "edge_sum": 0.0, "max_abs_pos": 0},
            )
            seen_ts = last_trade_ts.get(product, -1)
            fair = last_fair.get(product)
            max_seen = seen_ts

            for trade in trades:
                if trade.timestamp <= seen_ts:
                    continue

                signed_edge = 0.0
                if fair is not None:
                    if trade.buyer == "SUBMISSION":
                        signed_edge = (fair - trade.price) * trade.quantity
                    elif trade.seller == "SUBMISSION":
                        signed_edge = (trade.price - fair) * trade.quantity

                product_diag["fill_count"] += 1
                product_diag["fill_qty"] += trade.quantity
                product_diag["edge_sum"] += signed_edge
                max_seen = max(max_seen, trade.timestamp)

            last_trade_ts[product] = max_seen

    def _record_fair(self, memory: dict, product: str, fair: Optional[float]) -> None:
        if fair is None:
            return
        memory["last_fair"][product] = fair

    # ------------------------------------------------------------------ #
    # Strategy blocks                                                    #
    # ------------------------------------------------------------------ #

    def _trade_delta_one(self, product: str, depth: OrderDepth, position: int) -> List[Order]:
        config = self.DELTA_ONE_CONFIG[product]
        fair = self._wall_mid(depth)
        if fair is None:
            return []

        fair = (1.0 - config["anchor_wt"]) * fair + config["anchor_wt"] * config["anchor"]
        limit = self.LIMITS[product]
        edge = config["edge"]

        orders: List[Order] = []
        buy_remaining = limit - position
        sell_remaining = limit + position

        for ask in sorted(depth.sell_orders):
            if buy_remaining <= 0 or ask > fair - edge:
                break
            available = -depth.sell_orders[ask]
            quantity = min(available, buy_remaining)
            if quantity > 0:
                orders.append(Order(product, ask, quantity))
                buy_remaining -= quantity

        for bid in sorted(depth.buy_orders, reverse=True):
            if sell_remaining <= 0 or bid < fair + edge:
                break
            available = depth.buy_orders[bid]
            quantity = min(available, sell_remaining)
            if quantity > 0:
                orders.append(Order(product, bid, -quantity))
                sell_remaining -= quantity

        return orders

    def _trade_vouchers(self, state: TradingState, memory: dict) -> Dict[str, List[Order]]:
        orders: Dict[str, List[Order]] = {}
        velvet_depth = state.order_depths.get(self.VELVET)
        if not velvet_depth:
            return orders

        spot_mid = self._wall_mid(velvet_depth)
        spot_bid, spot_ask = self._best_bid_ask(velvet_depth)
        if spot_mid is None or spot_bid is None or spot_ask is None:
            return orders

        time_years = self._time_to_expiry(state.timestamp)

        for product in self.ACTIVE_VOUCHERS:
            depth = state.order_depths.get(product)
            if not depth:
                continue

            strike = int(product.split("_")[1])
            sigma = self.VOUCHER_SIGMA[product]
            fair_mid = self._bs_call(spot_mid, strike, time_years, sigma)
            self._record_fair(memory, product, fair_mid)

            fair_buy = fair_mid
            fair_sell = fair_mid
            if self.USE_SPOT_BRACKET:
                fair_buy = self._bs_call(float(spot_bid), strike, time_years, sigma)
                fair_sell = self._bs_call(float(spot_ask), strike, time_years, sigma)

            position = state.position.get(product, 0)
            buy_remaining = self.LIMITS[product] - position
            sell_remaining = self.LIMITS[product] + position
            product_orders: List[Order] = []

            for ask in sorted(depth.sell_orders):
                if buy_remaining <= 0 or fair_buy - ask < self.VOUCHER_EDGE:
                    break
                available = -depth.sell_orders[ask]
                quantity = min(available, buy_remaining)
                if quantity > 0:
                    product_orders.append(Order(product, ask, quantity))
                    buy_remaining -= quantity

            for bid in sorted(depth.buy_orders, reverse=True):
                if sell_remaining <= 0 or bid - fair_sell < self.VOUCHER_EDGE:
                    break
                available = depth.buy_orders[bid]
                quantity = min(available, sell_remaining)
                if quantity > 0:
                    product_orders.append(Order(product, bid, -quantity))
                    sell_remaining -= quantity

            if product_orders:
                orders[product] = product_orders

        return orders

    # ------------------------------------------------------------------ #
    # Entry point                                                        #
    # ------------------------------------------------------------------ #

    def run(self, state: TradingState):
        memory = self._deserialize_memory(state.traderData)
        self._update_diagnostics(state, memory)

        result: Dict[str, List[Order]] = {}

        for product in [self.HYDROGEL, self.VELVET]:
            depth = state.order_depths.get(product)
            if not depth:
                continue

            fair = self._wall_mid(depth)
            if fair is not None:
                config = self.DELTA_ONE_CONFIG[product]
                anchored_fair = (1.0 - config["anchor_wt"]) * fair + config["anchor_wt"] * config["anchor"]
                self._record_fair(memory, product, anchored_fair)

            orders = self._trade_delta_one(product, depth, state.position.get(product, 0))
            if orders:
                result[product] = orders

        voucher_orders = self._trade_vouchers(state, memory)
        result.update(voucher_orders)

        trader_data = jsonpickle.encode(memory)
        return result, 0, trader_data
