# IMC Prosperity 4 — Claude Code Context

_Last synced with `trader.py` on 2026-04-20._

## Challenge Overview

IMC Prosperity 4 is an algorithmic trading competition. You submit a Python `Trader` class that trades against bots on a simulated exchange to earn **XIRECs** (in-game currency). The simulation runs 1,000 iterations during testing and 10,000 for final scoring. Each iteration, `Trader.run()` is called with a `TradingState` and must return orders.

Round-level goal: reach **≥ 200,000 XIRECs net PnL** by the end of Round 2 to qualify for Phase 2.

## File Structure

- `trader.py` — the submission file containing the `Trader` class (upload this to IMC)
- `datamodel.py` — provided by IMC; defines `TradingState`, `Order`, `OrderDepth`, `Trade`, etc. Do not edit.
- `knowledge/round_N.md` — round briefing copied from the Prosperity site; source of truth for product names, limits, rules
- `knowledge/code_formatting.md` — allowed imports / submission formatting reference
- `logs/round_N/MMDD-HHMM/` — submission artifacts: `.json` (activitiesLog + profit), `.log` (trade records), `.py` (code snapshot at submission)
- `backtests/` — local `prosperity3bt` runs (kept sparse; prune aggressively)
- `analysis/` — notebooks for parsing logs and exploring data

The backtester lives outside this repo at `../imc-prosperity-3-backtester/` and is installed in editable mode (`pip install -e .`), so local edits to the backtester take effect immediately.

## Trader Class Contract

```python
class Trader:
    def bid(self) -> int:
        """Round 2 only. Sealed-bid auction for +25% market access.
        Top 50% of bids (above the median of all submissions) win extra flow;
        winners pay their bid from Round 2 profit. Ignored in other rounds."""
        return 15

    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        """Called every iteration.
        Returns: (orders_dict, conversions_int, traderData_string)
        """
```

### Return values from `run()`:
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
| `observations` | `Observation` | `plainValueObservations` and `conversionObservations` |

## Key Data Classes

```python
Order(symbol: str, price: int, quantity: int)
# quantity > 0 = BUY, quantity < 0 = SELL

class OrderDepth:
    buy_orders: Dict[int, int]   # price -> positive volume
    sell_orders: Dict[int, int]  # price -> NEGATIVE volume
# Buy prices strictly below sell prices.

Trade(symbol, price: int, quantity: int, buyer: str, seller: str, timestamp: int)
# buyer/seller == "SUBMISSION" for our fills, "" otherwise.

ConversionObservation(
    bidPrice, askPrice, transportFees, exportTariff, importTariff,
    sugarPrice, sunlightIndex,
)
```

## Hard Constraints

1. **Libraries**: Python 3.12 stdlib + pandas, NumPy, statistics, math, typing, jsonpickle. No other imports.
2. **Runtime**: `run()` must return within 900 ms. Target ≤ 100 ms.
3. **Stateless container**: AWS Lambda — class/global variables may NOT persist between calls. Use `traderData` for all state.
4. **Position limits**: Per-product absolute caps (long and short). If the aggregated buy (or sell) volume of your orders on a product would breach the limit assuming full fills, **ALL** orders on that side are rejected.
5. **traderData cap**: 50,000 chars; truncated beyond that.
6. **Order execution**: Instantaneous matching against resting bot quotes. Unmatched residual rests until end of iteration (cancelled if no bot hits it).

## Round 1 Products (current)

| Product | Position Limit | Typical Mid | Character |
|---|---|---|---|
| `ASH_COATED_OSMIUM` | 80 | ~10,000 | "Volatile but may follow a hidden pattern" per round brief. Wide book; mean-reverting around the anchor. |
| `INTARIAN_PEPPER_ROOT` | 80 | ~12,000 → ~14,000 | "Hardy, slow-growing root" — slow monotone drift. Backtest-observed drift ≈ +1,000 per day. |

Round 2 re-trades the same two products and adds the Market Access Fee (`bid()`) auction.

## Current Strategy (trader.py)

### ASH_COATED_OSMIUM — hybrid take + make

- **Fair value** = `0.8 * wall_mid + 0.2 * 10000`, where `wall_mid = (deepest bid + deepest ask) / 2`. Anchoring to 10,000 smooths deep-book noise on a product whose long-run mean is stable.
- **Take**: sweep asks below fair, bids above fair. Asymmetric threshold — when short, pay up one extra tick (`ask ≤ fair + 1`) to flatten inventory faster; same logic mirrored on the sell side.
- **Make**: penny-improve the inside (`bb+1`, `ba-1`) with size 12 per side, or join if the spread is already 1.
- **Inventory controls**:
  - `soft_cap=72`: stop quoting the adding side
  - `hard_cap=80`: only quote the unloading side, pricing it passively at `bb` or `ba` to rest

### INTARIAN_PEPPER_ROOT — drift-capture, go max long and hold

- Take every ask up to the position limit, then passive-bid `bb+1` for any residual capacity.
- Rationale: if the product drifts ~+1,000/day, the ~13-tick spread cost is recouped within ~130 ticks. Being late to fill means missing drift.
- No sell-side logic — we never want to be short this product.

### Current PARAMS

```python
PARAMS = {
    "ASH_COATED_OSMIUM":    {"limit": 80, "size": 12, "soft_cap": 72, "hard_cap": 80},
    "INTARIAN_PEPPER_ROOT": {"limit": 80, "size": 12, "soft_cap": 72, "hard_cap": 75},
}
```

(`size` is unused for PEPPER because the logic takes all available asks up to `buy_limit`.)

## Load-Bearing Assumptions (verify before blind-trusting)

- **PEPPER drift ≈ +1,000/day and monotone enough to justify max-long-and-hold.** If live drift is smaller, noisier, or mean-reverts over the round, this strategy has substantial downside. It's responsible for ~80% of backtest PnL — the tail risk here dominates total PnL variance.
- **OSMIUM true fair value ≈ 10,000.** The 20% weight on the 10k anchor silently assumes this. If live fair drifts off 10k, the taking thresholds will be biased.
- **Bot flow is rate-insensitive to our quote aggressiveness.** Validated in Tutorial on EMERALDS/TOMATOES — tighter quotes did not increase fill rate. Worth re-checking on Round 1 products.

## PnL Progression

### Live submissions (Round 1, single-day runs to 100,000 ticks)

| Submission | OSM PnL | PEP PnL | Total | Notes |
|---|---|---|---|---|
| 0415-2330 | 929 | 6,468 | 7,397 | First working version |
| 0416-0220 | 2,338 | 6,468 | 8,806 | OSMIUM tuning |
| 0416-0300 | 2,716 | 7,286 | 10,001 | **Best submitted.** OSM size=15, hard_cap=75; wall_mid un-anchored. |

### Local backtest of current `trader.py` (3 days = 3,000,000 ticks)

| Product | PnL |
|---|---|
| ASH_COATED_OSMIUM | 19,357 |
| INTARIAN_PEPPER_ROOT | 79,211 |
| **Total** | **98,568** |

Current code differs from last submission (0416-0300) on: OSM `size` 15→12, OSM `hard_cap` 75→80, `wall_mid` now blends 20% of a 10,000 anchor, OSMIUM take threshold loosened by 1 tick when short. Not yet re-submitted to IMC as of 2026-04-20.

## What Failed (archived, do not repeat)

| Strategy | Outcome | Why it failed |
|---|---|---|
| Fair-value EMA + mean reversion on TOMATOES (tutorial) | −5,830 | Crossed spread every trade; faded a trending series |
| Fair-value EMA + momentum on TOMATOES (tutorial) | −13,448 | Crossed spread; momentum amplified losses on a near-random walk |
| Tighter quotes (9999/10001 on EMERALDS, tutorial) | ~200 | Fill rate did not increase; gave up ~6 ticks of edge per fill |

**Lesson carried forward**: on a product with a stable fair value and no predictive signal, pennying the inside is strictly dominant over any directional strategy that pays the spread. The OSMIUM logic only takes when the book is *actually* mispriced vs. fair; it never crosses speculatively.

## Log Analysis Methodology

### Parse `activitiesLog` from the submission JSON

```python
# Fields: day;timestamp;product;bid_price_1;bid_volume_1;...;mid_price;profit_and_loss
lines = data["activitiesLog"].strip().split("\n")[1:]
```

### Extract fills from the `.log` trade records

```python
pattern = r'\{"timestamp":(\d+),"buyer":"([^"]*)","seller":"([^"]*)",'
          r'"symbol":"([^"]+)","currency":"[^"]+","price":([\d.]+),"quantity":(\d+)\}'
# Filter for buyer == "SUBMISSION" or seller == "SUBMISSION".
```

For `prosperity3bt` local backtest logs, the activities block is delimited by the markers `Activities log:` and `Trade History:` — split on those before parsing.

### Key metrics

- **Fill rate**: unique timestamps with fills / total ticks
- **Entry edge**: `(mid − fill_price)` for buys, `(fill_price − mid)` for sells
- **Next-tick edge** (adverse selection test): same, but using mid at `t + 100`
- **Fill size distribution**: `Counter` of fill quantities — check whether the cap is the binding constraint
- **Per-product PnL**: last `profit_and_loss` row per product in `activitiesLog`

### Decision rules

- Next-tick edge > 0 → no adverse selection → safe to size up
- > 15% of fills at the size cap → bot appetite exceeds our quote → size up
- Fill rate flat across quote aggressiveness → rate-limited flow → do not tighten
- Both momentum and fade lose → near-random walk → earn the spread passively, nothing else

## Round 2 Preview (not yet implemented)

- `bid()` returns the Market Access Fee bid. Top 50% of bids (above median) get +25% order flow; the bid amount is subtracted from Round 2 PnL. Game-theory problem: beat the median without overpaying. Bid is one-shot and not visible in backtests.
- Manual challenge: allocate a 50,000-XIREC budget across Research (log), Scale (linear), Speed (rank vs. all players). PnL = `Research × Scale × Speed − budget_used`. Speed is a coordination game against the field.

## Debugging Notes

- `print()` inside `run()` appears in the `.log` file from IMC
- Submissions get a UUID + runID — include when asking IMC staff questions
- Live test run is 1,000 iterations on a sample day (different from final scoring day)
- Watch out: excessive logging has caused AWS Lambda execution errors in prior years. Minimise `print()` before submission.
