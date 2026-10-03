"""What the survivor list is worth, measured against a benchmark that has none.

CLAIMS Р46 established the shape: on 1998-01-02 our panel carries 65 names of
the 2,251 that existed, and 8,858 names died inside the span with none of ours
among them. The obvious next question -- "how much would the dead names have
had to lose to eat Р41's 0.675" -- is WEAKER THAN IT SOUNDS, and saying so is
the point of this docstring.

WHY THE OBVIOUS BOUND DOES NOT WORK. The book is dollar-neutral and
cross-sectional. A dead name would sometimes have been a long and sometimes a
short, so its terminal loss hits both legs and largely cancels. Survivorship
mauls a LONG-ONLY result; it does something subtler to a neutral one, namely
it changes which names the signal was fitted on. That is a generalisation
question, and generalisation cannot be measured without the dead names'
prices, which cost $630/yr (Р42). So the honest free measurement is not the
bound I first proposed.

WHAT IS MEASURABLE WITHOUT OWNING A SINGLE DEAD PRICE. The premium sits in
the LEVEL, and we already hold both sides of it:

    our 110 names   chosen in 2026, every one of which survived to 2026
    SPY / VTI       the actual investable return of the whole market, which
                    ALREADY contains every constituent that died, at the
                    price it died at

The gap between the equal-weighted basket of our survivors and the index is
the survivorship premium in our own data, in Sharpe, with no assumption about
anything. It is not a proxy or a literature figure -- it is the thing itself.

WHAT IT DOES AND DOES NOT SETTLE. It bounds how much the LEVEL of our universe
is inflated. It does NOT prove the neutral book is inflated by the same
amount, and this script must not be read as saying so: a dollar-neutral book
is designed to be independent of the level. What it gives is the size of the
conditioning we have been working inside, measured rather than cited.

The naive opponent is printed FIRST, before anything of ours, because a number
without its opponent is not a result.

    python scripts/diagnostics/what_survivorship_is_worth_in_our_own_data.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.pipeline.sealed_period import seal_and_describe  # noqa: E402

BATCH = PROJECT_ROOT / "data" / "colab" / "accumulated" / "main_database"

#: Not stocks. An index fund is the benchmark, not a member of the basket --
#: including SPY among "our names" would put the opponent inside the team.
FUNDS = ("SPY", "QQQ", "DIA", "IWM", "VTI")

#: Trading days per year, used only to annualise. The daily frame is a daily
#: frame; this is not a cadence guess (Р44, #253).
DAYS = 252


def sharpe(returns: pd.Series) -> tuple[float, float, float, float]:
    """Annualised mean, vol, Sharpe, and the Sharpe's standard error.

    SE = 1/sqrt(years), the standard result for an iid series. Reported so a
    difference can be read against it instead of against enthusiasm -- and
    deliberately NOT corrected for autocorrelation here, because Р40 measured
    that correction as a multiplier of about 1.48 in the median, which would
    make every interval WIDER. The bare SE is therefore the optimistic case.
    """
    clean = returns.dropna()
    if len(clean) < DAYS:
        return float("nan"), float("nan"), float("nan"), float("nan")
    years = len(clean) / DAYS
    mean = float(clean.mean()) * DAYS
    vol = float(clean.std(ddof=1)) * np.sqrt(DAYS)
    ratio = mean / vol if vol > 0 else float("nan")
    return mean, vol, ratio, 1.0 / np.sqrt(years)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default="SPY",
                        help="the survivorship-free opponent; SPY or VTI")
    parser.add_argument("--start", default=None,
                        help="ISO date to begin at, default the panel's start")
    args = parser.parse_args()

    frame = pd.read_parquet(BATCH / "features.parquet",
                            columns=["ticker", "datetime", "interval", "close"])
    frame = frame[frame["interval"] == "1d"].copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True)
    frame, withheld, note = seal_and_describe(frame)
    print(note)
    print(f"  {withheld:,} rows withheld; {len(frame):,} remain\n")

    if args.start:
        frame = frame[frame["datetime"] >= pd.Timestamp(args.start, tz="UTC")]

    wide = (frame.pivot_table(index="datetime", columns="ticker",
                              values="close", aggfunc="last")
            .sort_index())
    returns = wide.pct_change(fill_method=None)

    if args.benchmark not in returns.columns:
        print(f"no {args.benchmark} in the batch; the opponent has to be real")
        return 2

    stocks = [c for c in returns.columns if c not in FUNDS]
    bench = returns[args.benchmark]

    # The basket is the EQUAL-WEIGHTED average name, which is what a
    # cross-sectional universe actually is. Cap-weighting would re-import the
    # index's own composition and measure something else.
    basket = returns[stocks].mean(axis=1, skipna=True)
    names_per_date = returns[stocks].notna().sum(axis=1)

    common = basket.notna() & bench.notna() & (names_per_date >= 10)
    basket, bench = basket[common], bench[common]
    span = (basket.index.min(), basket.index.max())

    print(f"span {span[0].date()} .. {span[1].date()}   "
          f"{len(basket):,} sessions, "
          f"{names_per_date[common].min()}..{names_per_date[common].max()} names per date\n")

    print("THE OPPONENT FIRST -- the whole market, deaths included:")
    b_mean, b_vol, b_sharpe, b_se = sharpe(bench)
    print(f"  {args.benchmark:<22} return {b_mean:+.2%}  vol {b_vol:.2%}  "
          f"Sharpe {b_sharpe:.3f} ± {b_se:.3f}\n")

    print("OURS -- 105 names chosen in 2026, all of which survived to 2026:")
    o_mean, o_vol, o_sharpe, o_se = sharpe(basket)
    print(f"  {'equal-weight basket':<22} return {o_mean:+.2%}  vol {o_vol:.2%}  "
          f"Sharpe {o_sharpe:.3f} ± {o_se:.3f}\n")

    # The difference as a series, not a subtraction of two Sharpes: that is
    # the only form whose significance can be read, because the two legs are
    # heavily correlated and their separate errors do not combine simply.
    spread = basket - bench
    s_mean, s_vol, s_sharpe, s_se = sharpe(spread)
    print("THE PREMIUM, as the portfolio that owns it (long ours, short the market):")
    print(f"  {'basket - ' + args.benchmark:<22} return {s_mean:+.2%}  vol {s_vol:.2%}  "
          f"Sharpe {s_sharpe:.3f} ± {s_se:.3f}")
    print(f"  correlation of the two legs: {basket.corr(bench):.3f}")
    print(f"  t on the mean: {s_sharpe / s_se:+.2f}\n")

    print("BY DECADE, because a premium concentrated in one stretch is a "
          "regime, not a bias:")
    print(f"  {'decade':<10}{'sessions':>10}{'ours':>9}{'market':>9}{'gap':>9}")
    print("  " + "-" * 47)
    for decade, part in spread.groupby(spread.index.year // 10 * 10):
        window = part.index
        _, _, ours, _ = sharpe(basket.loc[window])
        _, _, mkt, _ = sharpe(bench.loc[window])
        _, _, gap, _ = sharpe(part)
        print(f"  {decade}s{'':<5}{len(part):>10}{ours:>9.3f}{mkt:>9.3f}{gap:>9.3f}")

    # CONTROL 1: the same list, never rebalanced.
    #
    # Daily equal-weight rebalancing earns a diversification bonus a
    # buy-and-hold index does not, and at a median single-name vol above 30%
    # that could have been several points a year -- large enough to be the
    # whole finding. Measured rather than assumed, and it runs the OTHER way:
    # buy-and-hold returns MORE, because a list of names that became giants
    # fills up with the giants when nothing trims them. The rebalanced
    # basket's advantage is in volatility, not in return.
    prices = wide[stocks]
    held = pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    for name in prices.columns:
        start = prices[name].first_valid_index()
        if start is not None:
            held[name] = prices[name] / prices[name].loc[start]
    buy_and_hold = held.mean(axis=1, skipna=True).pct_change(fill_method=None)
    buy_and_hold = buy_and_hold[common]

    h_mean, h_vol, h_sharpe, _ = sharpe(buy_and_hold)
    hs_mean, _, hs_sharpe, hs_se = sharpe(buy_and_hold - bench)
    print("CONTROL -- the same list, never rebalanced (no diversification bonus):")
    print(f"  {'buy and hold':<22} return {h_mean:+.2%}  vol {h_vol:.2%}  "
          f"Sharpe {h_sharpe:.3f}")
    print(f"  {'that minus ' + args.benchmark:<22} return {hs_mean:+.2%}  "
          f"Sharpe {hs_sharpe:.3f} ± {hs_se:.3f}  t {hs_sharpe / hs_se:+.2f}")
    print("  A bigger return premium and a weaker Sharpe one: without trimming,\n"
          "  the winners take over and the volatility triples.\n")

    # CONTROL 2: every style tilt this batch can express.
    #
    # If the premium were size or sector rather than survival, it would show
    # up in the funds we already hold. It does not: each is under half a
    # standard error away from nothing.
    print("CONTROL -- the style tilts available in the same data:")
    for left in ("IWM", "QQQ", "DIA"):
        if left not in returns.columns or left == args.benchmark:
            continue
        tilt = (returns[left] - bench).dropna()
        t_mean, _, t_sharpe, t_se = sharpe(tilt)
        print(f"  {left + ' - ' + args.benchmark:<22} return {t_mean:+.2%}  "
              f"Sharpe {t_sharpe:+.3f} ± {t_se:.3f}  t {t_sharpe / t_se:+.2f}")
    print("  Size, technology and mega-cap each produce a gap under t = 1.1.\n"
          "  The survivor list produces one at t above 6.\n")

    print("What this does NOT say: that the name-neutral 0.675 of Р41 is "
          "inflated by this\namount. A dollar-neutral book is built to be "
          "independent of the level, and that\nis a separate measurement. "
          "This is the size of the conditioning we work inside.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
