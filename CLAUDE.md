# IMC Prosperity 4 — Claude Code Context

## Challenge Overview

IMC Prosperity 4 is an algorithmic trading competition. You submit a Python `Trader` class that trades against bots on a simulated exchange to earn **XIRECs** (in-game currency). The simulation runs 1,000 iterations during testing and 10,000 for final scoring. Each iteration, `Trader.run()` is called with a `TradingState` and must return orders.

## File Structure

- `trader.py` — the submission file containing the `Trader` class
- `datamodel.py` — provided by IMC; defines `TradingState`, `Order`, `OrderDepth`, `Trade`, etc.
- `old_trader.py` — archived previous versions for comparison

## Trader Class Contract

```python
class Trader:
    def bid(self) -> int:
        """Round 2 only. Sealed-bid auction. Ignored in other rounds."""
        return 15

    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        """Called every iteration.
        Returns: (orders_dict, conversions_int, traderData_string)
        """
```

### Return values from run():
1. `result: Dict[str, List[Order]]` — product name → list of Order objects
2. `conversions: int` — conversion request count (Round 2+). Use 0 if not needed.
3. `traderData: str` — serialised state string, delivered back as `state.traderData` next iteration. Capped at 50,000 chars. Use `jsonpickle` to serialise.

## TradingState Properties

| Property | Type | Description |
|---|---|---|
| `traderData` | `str` | Your serialised state from the previous iteration |
| `timestamp` | `int` | Current simulation time (increments by 100 per tick) |
| `listings` | `Dict[Symbol, Listing]` | Product metadata (symbol, product, denomination) |
| `order_depths` | `Dict[Symbol, OrderDepth]` | Bot limit order book per product |
| `own_trades` | `Dict[Symbol, List[Trade]]` | Your fills since last iteration |
| `market_trades` | `Dict[Symbol, List[Trade]]` | Other participants' fills since last iteration |
| `position` | `Dict[Product, int]` | Signed integer position per product |
| `observations` | `Observation` | Contains `plainValueObservations` and `conversionObservations` |

## Key Data Classes

### Order
```python
Order(symbol: str, price: int, quantity: int)
# quantity > 0 = BUY, quantity < 0 = SELL
```

### OrderDepth
```python
class OrderDepth:
    buy_orders: Dict[int, int]   # price -> positive volume
    sell_orders: Dict[int, int]  # price -> NEGATIVE volume
```
- Buy prices must be strictly below sell prices.
- `sell_orders` volumes are negative (e.g., `{12: -3, 11: -4}`).

### Trade
```python
Trade(symbol, price: int, quantity: int, buyer: str, seller: str, timestamp: int)
# buyer/seller = "SUBMISSION" when it's your algo, "" otherwise
```

### ConversionObservation
```python
ConversionObservation(bidPrice, askPrice, transportFees, exportTariff, importTariff, sugarPrice, sunlightIndex)
```

## Hard Constraints

1. **Libraries**: Only Python 3.12 stdlib + pandas, NumPy, statistics, math, typing, jsonpickle. No other imports.
2. **Runtime**: `run()` must return within 900ms. Target ≤100ms.
3. **Stateless container**: AWS Lambda — class/global variables may NOT persist between calls. Use `traderData` string for all state.
4. **Position limits**: Per-product absolute caps (long and short). If aggregated buy (sell) volume would breach the limit assuming full fills, ALL orders on that side are rejected.
5. **traderData cap**: 50,000 characters max. Truncated by the framework beyond that.
6. **Order execution**: Instantaneous matching. Your orders are matched against resting bot quotes immediately. Unmatched residual rests for bots to trade against; cancelled at end of iteration if no bot fills it.

## Current Products (Round 1)

| Product | Position Limit | Spread (typical) | Mid Price Behavior |
|---|---|---|---|
| EMERALDS | 80 | 16 ticks (97% of time) | Pegged at ~10,000, stdev 0.69 |
| TOMATOES | 80 | 13-14 ticks (94% of time) | Slow drift (~20 ticks over 2000 iterations), stdev ~6 |

## What Works (Empirically Verified)

### Winning strategy: Pure passive market-making at bb+1 / ba-1
- Post bids at `best_bid + 1`, asks at `best_ask - 1` (one tick price improvement)
- Small-to-medium size per quote (currently 12 lots EMERALDS, 9 lots TOMATOES)
- Inventory skew via soft_cap (stop adding side) and hard_cap (only unload side)
- NO taking (crossing the spread). NO fair-value model. NO momentum. NO mean reversion.

### Why this works:
- Bots cross the spread at a fixed rate regardless of where we quote
- Posting tighter does NOT increase fill rate — it only reduces per-fill edge
- We earn ~7 ticks/fill on EMERALDS and ~5.5 ticks/fill on TOMATOES
- Zero adverse selection: next-tick mid moves in our favour after fills
- Fill rate: ~1.4% of ticks (EMERALDS), ~3.4% (TOMATOES)

## What Failed (Empirically Verified)

| Strategy | PnL | Why it failed |
|---|---|---|
| v1: Fair-value EMA + mean reversion (TOMATOES) | -5,830 | Crossed spread every trade; faded a trending series |
| v2: Fair-value EMA + momentum (TOMATOES) | -13,448 | Crossed spread; momentum amplified losses vs random walk |
| Tighter quotes (9999/10001 on EMERALDS) | ~200 | Fill rate didn't increase; gave up 6 ticks of edge per fill |

### Key lesson: NEVER cross the spread on these products.
Bot flow is crossing-aggressive but rate-insensitive. We don't attract more fills by quoting tighter — bots decide to cross when they cross. Paying the spread with directional signals destroyed PnL.

## PnL Progression

| Version | Strategy | EMERALDS PnL | TOMATOES PnL | Total |
|---|---|---|---|---|
| v3 (old_trader.py) | Passive bb+1/ba-1, size 4/3 | 777 | 1,147 | 1,924 |
| v4 | Same structure, size 8/5 | 1,050 | 1,468 | 2,518 |
| v5 (current) | Same structure, size 12/9 | TBD | TBD | TBD |

## Log Analysis Methodology

When analysing a Prosperity log (JSON + LOG files):

### 1. Parse activitiesLog from JSON
```python
# Fields: day;timestamp;product;bid_price_1;bid_volume_1;...;mid_price;profit_and_loss
lines = data['activitiesLog'].strip().split('\n')[1:]
```

### 2. Extract fills from LOG file
```python
# Regex for trade records at end of log file
pattern = r'\{"timestamp":(\d+),"buyer":"([^"]*)","seller":"([^"]*)","symbol":"([^"]+)","currency":"[^"]+","price":([\d.]+),"quantity":(\d+)\}'
# Filter for buyer="SUBMISSION" or seller="SUBMISSION"
```

### 3. Key metrics to compute
- **Fill rate**: unique timestamps with fills / total ticks
- **Entry edge**: (mid - fill_price) for buys, (fill_price - mid) for sells
- **Next-tick edge** (adverse selection test): same but using mid at t+100ms
- **Fill size distribution**: Counter of fill quantities — check for cap saturation
- **Per-product PnL**: from activitiesLog last row per product

### 4. Decision framework
- If next-tick edge is positive → no adverse selection → safe to increase size
- If fill size distribution shows >15% at the cap → bot appetite exceeds our quote → increase size
- If fill rate doesn't change between runs → bot aggression is rate-limited → don't tighten quotes
- If both momentum and fade lose → series is near random walk → only earn the spread passively

## Inventory Management Parameters

```python
PARAMS = {
    "EMERALDS": {
        "make_size": 12,    # lots per passive quote
        "soft_cap": 40,     # stop quoting the adding side
        "hard_cap": 70,     # only quote the unloading side
    },
    "TOMATOES": {
        "make_size": 9,
        "soft_cap": 25,
        "hard_cap": 55,
    },
}
```

## Future Optimization Ideas (Not Yet Tested)

1. **Directional tilt on TOMATOES**: bias ask-size up when fast EMA < slow EMA to capture slow mid drift
2. **Second-level quotes**: post smaller order at bb+2/ba-2 behind main quote to capture large bot sweeps
3. **Raise soft/hard caps**: both runs ended well under caps; may help on trending days
4. **Round 2 considerations**: `bid()` method for sealed-bid auction; `conversions` for arbitrage via ConversionObservation channel (transport + tariff costs)

## Debugging

- `print()` inside `run()` appears in the log file
- Each submission gets a UUID + runID — include when asking IMC staff questions
- Upload runs 1,000 iterations on a sample day (different from final scoring day)
- Log file contains activitiesLog (book snapshots) + trade records (your fills)
