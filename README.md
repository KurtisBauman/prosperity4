# prosperity4

IMC Prosperity 4 — Bayesian Ballistics

## Setup

```bash
# 1. Create a pyenv virtualenv
pyenv virtualenv 3.12 prosperity4
cd path/to/prosperity4
pyenv local prosperity4

# 2. Clone and install the backtester (editable mode)
cd ..
git clone https://github.com/isaack0ng/imc-prosperity-3-backtester.git
cd imc-prosperity-3-backtester
pip install -e .
cd ../prosperity4
```

## Repo Structure

```
trader.py              # THE submission file — upload this to IMC
datamodel.py           # IMC-provided data model (do not edit)
requirements.txt       # Python dependencies

knowledge/             # Round descriptions, strategy notes
data/                  # IMC-provided historical market data (committed)
  round_1/
    prices_round_1_day_*.csv
    trades_round_1_day_*.csv

logs/                  # Submission output + code snapshots (committed)
  round_N/
    MMDD-HHMM.json     # activitiesLog + profit summary
    MMDD-HHMM.log      # activitiesLog + trade records
    MMDD-HHMM.py       # code snapshot that produced this run

analysis/              # Log parsing, data visualization, notebooks
```

## Workflow

1. Edit `trader.py`
2. Backtest locally: `prosperity3bt trader.py 1`
3. Upload `trader.py` to IMC
4. Download results into `logs/round_N/` as `MMDD-HHMM.{json,log,py}`

## Modifying the Backtester

The backtester lives outside this repo in `../imc-prosperity-3-backtester/`. Since it's installed in editable mode (`pip install -e .`), any changes you make there take effect immediately — no reinstall needed.

To pull upstream updates:

```bash
cd ../imc-prosperity-3-backtester
git pull
```

## Resources

- [How to actually compete in IMC Prosperity 4](https://www.reddit.com/r/csMajors/comments/1rvnjdb/how_to_actually_compete_in_imc_prosperity_4/) — strategy overview and round-by-round breakdown
- [TimoDiehm/imc-prosperity-3](https://github.com/TimoDiehm/imc-prosperity-3) — P3 solutions and analysis
- [chrispyroberts/imc-prosperity-3](https://github.com/chrispyroberts/imc-prosperity-3) — P3 solutions with Monte Carlo backtester
- [CarterT27/imc-prosperity-3](https://github.com/CarterT27/imc-prosperity-3) — P3 solutions and writeups
- [Prosperity 3 Visualizer](https://jmerle.github.io/imc-prosperity-3-visualizer/) — upload backtest/submission logs to visualize order book, PnL, and position

## Round Archetypes

The products are always the same archetypes:

- **Round 1**: Fixed-fair-value product (pure market making) + mean-reverting product + noisy/volatile product. If you need reps on spread/inventory dynamics, Myntbit is the fastest way to practice before the competition.
- **Round 2**: ETF basket + constituents. Textbook statistical arbitrage. Z-score the spread, trade the divergence.
- **Round 3**: Options. Black-Scholes. Implied volatility. Smile fitting. The Frankfurt Hedgehogs generated 200k+ SeaShells/day here by going completely unhedged. Understanding why that works is the difference between a top-10 and top-500 finish. Khan Academy's options section and Myntbit's derivatives practice will get you up to speed if you're rusty.
- **Round 4**: Cross-exchange / location arbitrage with conversion costs. Read the problem statement twice — there's almost always a hidden mechanic in the fee structure.
- **Round 5**: Trader IDs get revealed. Someone in the simulation is an insider. Find them. Copy them. Go to max position. This is not a joke.

## What Kills Good Teams

- Hardcoding to last year's data without a fallback (it got teams banned in P3)
- Overfitting backtest parameters to historical rounds. The live bots are not your backtest
- Touching Squid Ink (or whatever the noisy Round 1 product is) too aggressively. Many teams lost more here than they made everywhere else
- AWS Lambda execution errors from verbose logging. Minimize your `print()` calls before you submit
- Not building your environment until Round 1 drops. By then it's too late

## Constraints

- **Allowed imports**: Python 3.12 stdlib + pandas, NumPy, statistics, math, typing, jsonpickle
- **Runtime**: `run()` must return within 900ms (target <100ms)
- **Position limits**: per-product absolute caps (see `knowledge/` for each round)
- **traderData**: 50,000 char max for persisting state between iterations
