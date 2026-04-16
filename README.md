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

## Constraints

- **Allowed imports**: Python 3.12 stdlib + pandas, NumPy, statistics, math, typing, jsonpickle
- **Runtime**: `run()` must return within 900ms (target <100ms)
- **Position limits**: per-product absolute caps (see `knowledge/` for each round)
- **traderData**: 50,000 char max for persisting state between iterations
