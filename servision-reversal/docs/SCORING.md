# Scoring & methodology

## The score is not a black box

The reversal score is the **sum of named, signed components**. There is no
hidden model, no opaque weighting. `total = Σ component.points`. The UI renders
each component as a signed bar so you can see exactly what built any score.

Every component, its max weight, and every threshold lives in one file:
`backend/app/scanner/config.py` (`StrategyConfig`). Change a number there, save
it as a new strategy version, and re-backtest.

## Components

| Component | Direction | What it measures |
|---|---|---|
| catalyst | + | earnings (full) or news (partial) trigger present |
| move_magnitude | + | size of the down-move vs previous close, past a floor |
| move_vs_expected | + | move relative to options-implied expected move (needs options data) |
| volume | + | today's volume ÷ average volume, past a floor |
| vwap_extension | + | how stretched **below** VWAP price is (reversion fuel) |
| momentum_exhaustion | + | minutes since the last new intraday low |
| morning_low | + | a morning low has been established |
| higher_low | + | a higher low has formed (structural confirmation) |
| vwap_reclaim | + | price reclaimed VWAP after being below it |
| eps_surprise | ± | EPS beat adds, genuine miss subtracts |
| revenue_surprise | ± | revenue beat adds, miss subtracts |
| guidance | ± | raised adds, lowered subtracts |
| valuation_risk | − | rich forward P/E or P/S penalises (dip may be justified) |
| relative_strength | + | outperforming its sector intraday |

`status`: `SKIP` < `min_score_to_watch` ≤ `WATCH` < `min_score_to_qualify` ≤ `QUALIFIED`.

## Hypotheses being tested (not assumptions being trusted)

The design encodes specific, falsifiable hypotheses. The backtester exists to
confirm or kill each one:

- **H1** A beat-but-sold-off reaction reverts more than a genuine miss.
- **H2** A genuine miss should reduce reversal odds (hence the penalty).
- **H3** Rich valuation + negative catalyst = the drop may be warranted (penalty).
- **H4** A move far larger than the options-implied expected move is more likely
  to be an overreaction.

If a backtest breakdown shows, say, that "miss" trades win as often as "beat"
trades, that's evidence H1/H2 are wrong for this dataset — change the weights.

## No look-ahead — how it's enforced structurally

1. **Indicators**: every "as of time T" function only reads bars with `t <= T`
   (`indicators.py`, the `_as_of` functions and `_bars_up_to` guard).
2. **Fundamentals**: each historical event carries
   `fundamentals_available_at`. The backtester refuses to use earnings numbers
   before that epoch (`engine._candidate_at`).
3. **Outcomes**: a trade's result is computed only from bars **after** entry.
4. **Same code both ways**: the live scanner and the backtester call the *same*
   `score_candidate()`, so historical results can't silently differ from live.

## Conservative outcome assumptions

- Fills are modelled with slippage (`slippage_pct`).
- If a single bar's range spans both the stop and a target, the **stop is
  assumed to hit first** (worst case) so results aren't flattered.

## Anti-overfitting

`backtesting/validation.py` splits events into train / validation /
out-of-sample by year and flags when out-of-sample win rate falls materially
below the development period. Small buckets are flagged `insufficient_sample`
(n < 30) everywhere so you don't over-read noise.

## Estimated paper revenue

The projection on the Statistics page is derived **only** from tracked paper
results: observed expectancy per trade × position size × trades. It always shows
the sample size and a ±95% band that widens as the sample shrinks. It is never a
from-nothing "$X/month" figure, and it is labelled as paper research, not a
forecast of returns.
