# Long shots are overpriced in prediction markets — on play money and on real money

*A calibration study of two prediction markets with one pre-registered rule. The question is the one a
bookmaker's risk desk asks about its own prices: when the market says 6%, does the event happen 6% of the time?*

## The rule (committed before any data was fetched)

- **Moment of judgement:** T = the market's close minus 7 days; the price at T is the last trade (Manifold) or
  the last hourly price point (Polymarket) **before** T. A price after T is never used — a control counts it.
- **Long shots:** contracts priced 0.02–0.15 at T. **Bias** B = mean price − share that resolved YES.
- **Verdict:** B > 0 with z ≥ 1.645; a z within 0.10 of the line counts as *not passed*. On Polymarket the z is
  clustered by event (candidates of one event are mutually exclusive), declared as the headline before the run.
- **Guard before looking at outcomes:** the minimum detectable effect, computed from prices alone, must be
  ≤ 0.030, else the test is not run.

## Result

| | Manifold (play money) | Polymarket (real money) |
|---|---|---|
| Markets with a price at T | 3,734 resolved YES/NO, ≥ 20 traders | 4,474 resolved YES/NO, volume ≥ $10,000, opened from 01.2024 |
| Long shots 0.02–0.15 | 1,180 | 1,102 (647 events) |
| Mean price → share YES | 0.0645 → 0.0508 | 0.0618 → 0.0499 |
| **Bias B** | **+1.37 points**, z +1.93 | **+1.19 points**, clustered z +1.92 (binomial z +1.66) |
| Favourites 0.85–0.98: share YES − price | +1.18 points | +2.38 points |
| Minimum detectable effect | 0.020 | 0.020 |

**Long shots win less often than their price says, by about the same amount on both platforms**: below 15 cents
the price overstates the event by a factor of ~1.2–1.3, below 10 cents by ~1.4. Favourites are underpriced by
1–2.4 points. This is the favourite–longshot bias known from betting markets; that it is the same size with
play money and real money says it is not an artefact of free money.

Calibration by price bucket, Polymarket: 0.0–0.1 priced 0.019 / happened 0.014 (2,949 markets); 0.1–0.7 within
2 points; 0.7–0.8 priced 0.748 / happened 0.798; 0.9–1.0 priced 0.969 / happened 0.982.

## Controls (each with a known answer, all run before the verdict)

| | Manifold | Polymarket |
|---|---|---|
| **K1** outcomes redrawn as Bernoulli(price) — a perfectly calibrated world: false "yes" ≤ 10% | 4% | 7% |
| **K2** a planted bias of −0.05 on long shots must be found in ≥ 80% of redraws | 100% | 100% |
| **K3** coin-flip bucket 0.45–0.55: share YES within 0.40–0.60 | 0.521 | 0.505 |
| **K4** price points after T used | — | 0 |

## Forecasts, scored

Before the runs I wrote down ranges for each number. Manifold: 6 of 6 right. Polymarket: 7 of 9 — the two misses
were the number of events (647 against a forecast of 150–500: markets split into events more finely than I
assumed) and the favourites' gap (+0.024 against 0–0.02).

## Limits, stated before reading the result

- One horizon (a week before close); other horizons are not measured.
- Polymarket is selected by final volume (pulls B down) and priced from history points, not trades (may push B up).
- The sample is the oldest 10,000 Polymarket markets opened from January 2024, tilted towards politics. One-sided p ≈ 0.03 on each platform — moderate strength.
- **This is a description of the price as a forecaster, not a trading strategy.** 1.2 points per contract a week
  before close is before spread and the cost of capital; trading was not measured and is not proposed.

## Why it matters

A market price is a forecast with a known defect. Anyone who uses market odds as a baseline — a risk analyst
comparing their own prices, a model scored against the market — should correct for it: below ~15% the market
is too generous to the outsider, above ~85% too stingy to the favourite.

## Files

- `manifold_longshot_587.py` — the Manifold instrument, unchanged.
- `polymarket_longshot_592.py` — the Polymarket instrument; one local networking workaround (fixed host
  addresses for this machine) is removed, nothing else changed.

Both store the raw API responses before any computation and run the analysis only from what was stored.
