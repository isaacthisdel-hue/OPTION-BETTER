# Data & Options Upgrade Roadmap

Parked plan (from the build session) for making the tool fully real, kept here so
it can resurface when wanted. Current build uses the FREE path (Alpha Vantage) for
real intraday stock history. The items below are paid upgrades to layer on later.

## Where we are (free tier)
- Live quotes / earnings: Finnhub free.
- Real intraday history for the backtester + learned reversal model: **Alpha Vantage free**
  (`ALPHAVANTAGE_API_KEY`). ~25 requests/day, ~5/min — enough for a handful of tickers
  over the last week; not a whole-market scan.
- Finnhub free does NOT serve stock candles (403) — that is why the backtester uses
  Alpha Vantage, not Finnhub, for history.

## Upgrade 1 — real intraday for STOCKS at scale
Goal: scan/backtest more than a handful of names, reliably.
- Option A: **Finnhub Market Data "Basic" ~$49.99/mo** — unlocks intraday/historical
  stock candles that the free tier blocks. Fundamentals/estimates are separate add-ons
  (~$50-75/mo each). Enterprise ~$3,000+/mo. (Confirm live at finnhub.io/pricing.)
- Option B: stay free on Alpha Vantage and just accept the daily request cap.

## Upgrade 2 — real OPTIONS (the big one for this strategy)
Goal: turn #4 from an equity-move proxy into a real options tool.
- **Polygon.io / Massive — Options plan, ~$29/mo (Starter)** (Developer ~$79, Advanced ~$199).
  Options is billed as its own asset class, separate from stocks. (Confirm at polygon.io/pricing.)
- What it unlocks in the app:
  - Real option chains: strikes, premiums, implied volatility.
  - The options market's **implied expected move** -> feeds the `move_vs_expected`
    score component (currently dark on free data).
  - Genuine simulated option P/L in paper trades (real premiums), aimed at next Friday's expiry.
- Finnhub also has `/stock/option-chain` but it is premium/enterprise with thin coverage —
  not recommended vs Polygon/Massive for options.

## Recommended sequence
1. (now) Free Alpha Vantage -> real backtest + learned reversal model on real stocks.
2. (later, ~$29/mo) Add Polygon/Massive Options -> real premiums, implied move, option P/L.
3. (optional, ~$50/mo) Finnhub Basic or paid feed if a wider live universe is needed.

Net: $0 to make it real on equities; ~$29/mo to make options real.
