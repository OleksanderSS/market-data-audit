"""Value ratios, each built only from numbers already filed at the bar.

The first features in this system that are not derived from price. Measured on
2026-08-23, all 430 existing ones are: the strongest reaches an out-of-sample
IC of 0.046, no model built from all of them beats it, and 171 of 448 cannot
even vary between names on a date. New information has to come from outside the
price series, and a company's own accounts are the oldest source there is.

Three things decide whether this is honest.

**Availability is `filed`.** A June quarter reaches the SEC in August. Joining
on the period it describes would put it into June's bars -- measured on Apple's
filings, the shortest gap between a period ending and the filing that first
reported it is 25 days, and the median across all repeats is 216. Every join
here is `merge_asof(..., direction="backward")` on the filing date -- and
not on its midnight (#535): `filed` is a day with no hour, and 46.21% of the
5,805 stored (accession, filed) pairs were accepted by EDGAR at or after 16:00
New York on that day, so the daily bar of d read them before they existed
(75.26% for the bars from the open). A fact is known from the second its
filing was accepted -- `acceptanceDateTime` of the same accession in
`sec_filings`, true UTC (#530) -- or, where that is missing, from `filed` plus
`filed_lag_days`.

**The latest view AS OF the bar, not the latest view.** The same quarter is
restated by later filings, and 1,972 of Apple's 2,939 facts are such repeats.
Taking today's number for a bar in 2019 would be reading a correction written
years afterwards. The backward join takes what was on the record then.

**A flow concept is picked by its SPAN.** `NetIncomeLoss` arrives for the
quarter AND for the year to date, both ending the same day, from the same
filing. Mixing them silently multiplies earnings by up to four. Only entries
whose span looks quarterly are used, and the rule is explicit rather than
implied by whichever row happened to sort first.

Ratios needing a price use the bar's own close, which is known at the bar by
definition. Ratios that do not are computed from the accounts alone, so they
survive on a frame with no price at all.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from .base import BaseEnricher

logger = logging.getLogger(__name__)

#: A quarterly span, generously bounded. 10-Q periods run 84 to 98 days; the
#: year-to-date entries that share their end date run 175 to 370, so the two
#: groups do not overlap and the rule needs no tie-breaking.
QUARTER_DAYS = (60, 130)

#: Balance-sheet concepts are instantaneous -- they have no span, so there is
#: nothing to disambiguate.
_INSTANT = (
    "Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent",
    "StockholdersEquity", "LongTermDebtNoncurrent",
    "CashAndCashEquivalentsAtCarryingValue",
)

#: Flow concepts cover a period, and must be filtered by span.
_FLOW = ("NetIncomeLoss", "Revenues", "OperatingIncomeLoss")

#: Share counts, needed to put a balance-sheet figure next to a share price.
_SHARES = ("CommonStockSharesOutstanding",
           "WeightedAverageNumberOfSharesOutstandingBasic")


def _naive_utc(values: "pd.Series") -> "pd.Series":
    """Datetimes as tz-naive UTC, whichever way they arrive.

    The batch stores `datetime` in UTC; every fixture in the tests is naive.
    A step that handles only one of the two passes the whole suite and dies on
    the real frame -- `.astype("datetime64[ns]")` raises on a tz-aware column,
    and `.tz_localize(None)` raises on a naive one. Both mistakes were made
    here on 2026-08-23, and the second of them crashed a two-and-a-half-hour
    rebuild by comparing datetime64[ns] against datetime64[ns, UTC].
    """
    parsed = pd.to_datetime(values, errors="coerce")
    tz = getattr(getattr(parsed, "dt", None), "tz", None)
    if tz is not None:
        parsed = parsed.dt.tz_convert("UTC").dt.tz_localize(None)
    return parsed


class FundamentalsEnricher(BaseEnricher):
    """Point-in-time value ratios from reported SEC figures."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__()
        self.config = config or {}
        # Beyond this the accounts are too old to describe the company. A
        # filing every quarter means a gap over ~200 days is a company that
        # stopped reporting, not one that is merely between filings.
        self.max_staleness_days = int(self.config.get("max_staleness_days", 200))
        # Only for a fact whose filing has no acceptance time (#535).
        self.filed_lag_days = int(self.config.get("filed_lag_days", 1))

    @property
    def name(self) -> str:
        return "fundamentals"

    @property
    def priority(self) -> int:
        # After corporate_filings (30): both key off SEC filing dates, and the
        # counts there are a cheaper answer to a related question.
        return 31

    def get_feature_names(self) -> list[str]:
        return [
            "fund_price_to_book",
            "fund_earnings_yield",
            "fund_current_ratio",
            "fund_debt_to_equity",
            "fund_return_on_equity",
            "fund_days_since_report",
            "fund_data_available",
        ]

    # ------------------------------------------------------------- shaping

    @staticmethod
    def _pick_by_span(facts: pd.DataFrame) -> pd.DataFrame:
        """Keep quarterly spans for flow concepts, everything for instants.

        Without this, `NetIncomeLoss` for the quarter and for the nine months
        both survive -- same end date, same accession, different numbers -- and
        whichever sorts last wins. Earnings would be silently up to four times
        too large, in a direction nothing downstream could detect.
        """
        span = (facts["period_end"] - facts["period_start"]).dt.days
        is_flow = facts["concept"].isin(_FLOW)
        quarterly = span.between(*QUARTER_DAYS)
        # An instantaneous fact has no start; `span` is NaT there, which is
        # exactly the rows that should pass untouched.
        return facts[~is_flow | quarterly.fillna(False)]

    def _known_at(self, facts: pd.DataFrame, filings: Any) -> pd.Series:
        """When each fact became knowable, tz-naive UTC (#535).

        The acceptance second of its filing, matched on the accession; a fact
        with no match, no accession, or a bare date (exactly 00:00:00 New
        York) is known from `filed` plus `filed_lag_days`.
        """
        known = facts["filed"].dt.normalize() + pd.Timedelta(days=self.filed_lag_days)
        if (not isinstance(filings, pd.DataFrame) or filings.empty or "accession" not in facts.columns
                or not {"accessionNumber", "acceptanceDateTime"} <= set(filings.columns)):
            return known
        # Only the accessions the facts name (~6 thousand of ~615 thousand
        # filings): parsing every acceptance time made this step 8 s from 3.
        filings = filings[filings["accessionNumber"].astype(str).isin(set(facts["accession"].astype(str)))]
        accepted = pd.to_datetime(filings["acceptanceDateTime"], errors="coerce", utc=True)
        local = accepted.dt.tz_convert("America/New_York")
        bare = (local.dt.hour == 0) & (local.dt.minute == 0) & (local.dt.second == 0)
        # An accession is one filing; 132 of 614,936 stored rows repeat one, none
        # with a different time (03.10). Should two ever differ, the LATER time
        # wins: it is never earlier than the truth.
        clock = (pd.DataFrame({"accession": filings["accessionNumber"].astype(str),
                               "_accepted": accepted.dt.tz_localize(None).where(~bare)})
                 .dropna().sort_values(["accession", "_accepted"], kind="mergesort")
                 .drop_duplicates("accession", keep="last").set_index("accession")["_accepted"])
        exact = facts["accession"].astype(str).map(clock).astype("datetime64[ns]")
        return exact.fillna(known.astype("datetime64[ns]"))

    def _as_of(self, bars: pd.DataFrame, facts: pd.DataFrame, concept: str,
               total_rows: int) -> np.ndarray:
        """The value on the record for each bar, as a POSITIONAL array.

        Positional, and that is the whole point. Returning a Series indexed by
        bar position while the caller's frame carried its own index made
        `frame[col] - series` align on index instead of position: pandas took
        the UNION, and 29,097 rows became 53,441. The rebuild died on
        "Length of values (53441) does not match length of index (29097)"
        after two and a half hours.

        Every value below is placed by position into an array the length of the
        frame, so nothing can align anything.
        """
        out = np.full(total_rows, np.nan, dtype=float)
        right = facts[facts["concept"].eq(concept)]
        if right.empty or bars.empty:
            return out

        # Sorted by (filed, period_end) so that among rows filed on the SAME
        # day -- a 10-Q states the current quarter and the year-ago comparative
        # together -- the one describing the most recent period wins.
        # `merge_asof` takes the last match, and without period_end in the sort
        # which of the two it took was arbitrary.
        right = (right.sort_values(["filed", "period_end"])
                      .loc[:, ["ticker", "filed", "value"]]
                      .rename(columns={"value": concept}))
        # unbounded-on-purpose: bounded ALREADY, downstream. `max_staleness_
        # days` (200) masks every figure older than that, using the filing age
        # computed by `_latest_filed`. A `tolerance=` here would drop the row
        # before the age could be measured, so the mask would lose the very
        # thing it decides on -- and the last figure a company FILED is what
        # was knowable until it files again, which is the point-in-time answer.
        merged = pd.merge_asof(
            bars.sort_values("_bar"),
            right,
            left_on="_bar", right_on="filed", by="ticker", direction="backward",
        )
        out[merged["_pos"].to_numpy()] = merged[concept].to_numpy(dtype=float)
        return out

    # -------------------------------------------------------------- enrich

    def _enrich_impl(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        frame = df.copy(deep=False)
        for name in self.get_feature_names():
            frame[name] = np.nan
        frame["fund_data_available"] = 0

        facts = kwargs.get("sec_fundamentals")
        if facts is None or getattr(facts, "empty", True):
            logger.warning(
                "FundamentalsEnricher: no sec_fundamentals supplied; the value "
                "ratios will be absent rather than wrong."
            )
            return frame

        required = {"ticker", "concept", "value", "filed", "period_end"}
        missing = required - set(facts.columns)
        if missing:
            logger.error(
                "FundamentalsEnricher: sec_fundamentals is missing %s. This is "
                "a schema break, not empty data.", sorted(missing),
            )
            return frame

        time_column = next(
            (name for name in ("datetime", "timestamp", "date") if name in frame.columns),
            None,
        )
        if time_column is None or "ticker" not in frame.columns:
            logger.error("FundamentalsEnricher: frame has no datetime or ticker.")
            return frame

        facts = facts.copy(deep=False)
        facts["filed"] = _naive_utc(facts["filed"])
        facts["period_end"] = _naive_utc(facts["period_end"])
        facts["period_start"] = _naive_utc(facts.get("period_start"))
        facts = facts.dropna(subset=["filed", "value"])
        facts["filed"] = self._known_at(facts, kwargs.get("sec_filings"))
        facts = self._pick_by_span(facts)
        if facts.empty:
            logger.warning("FundamentalsEnricher: no facts survived the span filter.")
            return frame

        bars = pd.DataFrame({
            "_pos": np.arange(len(frame)),
            "ticker": frame["ticker"].astype(str).to_numpy(),
            "_bar": _naive_utc(frame[time_column]).to_numpy(),
        })
        if bars["_bar"].isna().all():
            logger.error("FundamentalsEnricher: no usable bar timestamps.")
            return frame
        # merge_asof refuses NaT keys, and a bar with no time cannot be placed
        # against a filing date anyway.
        bars = bars.dropna(subset=["_bar"])
        facts["filed"] = _naive_utc(facts["filed"])
        bars["_bar"] = _naive_utc(bars["_bar"])

        # Everything from here is numpy of length len(frame). Nothing is a
        # Series, so nothing can align on an index that is not position.
        rows = len(frame)
        values = {name: self._as_of(bars, facts, name, rows)
                  for name in (*_INSTANT, *_FLOW, *_SHARES)}
        latest_filed = self._latest_filed(bars, facts, rows)

        def positive(array):
            """Keep only values above zero; the rest become NaN."""
            return np.where(array > 0, array, np.nan)

        equity = values["StockholdersEquity"]
        shares = np.where(
            np.isfinite(values["CommonStockSharesOutstanding"]),
            values["CommonStockSharesOutstanding"],
            values["WeightedAverageNumberOfSharesOutstandingBasic"],
        )
        income = values["NetIncomeLoss"]

        # A ratio with a non-positive denominator is not a large number, it is
        # a different situation -- negative equity is distress, and dividing by
        # it produces a figure that ranks as if it were cheap.
        safe_equity = positive(equity)
        safe_shares = positive(shares)

        with np.errstate(divide="ignore", invalid="ignore"):
            assigned = {
                "fund_current_ratio": values["AssetsCurrent"]
                    / positive(values["LiabilitiesCurrent"]),
                "fund_debt_to_equity": values["Liabilities"] / safe_equity,
                "fund_return_on_equity": income / safe_equity,
            }

            close = None
            for candidate in ("close", "Close", "close_1d"):
                if candidate in frame.columns:
                    close = pd.to_numeric(
                        frame[candidate], errors="coerce"
                    ).to_numpy(dtype=float)
                    break
            if close is not None:
                market_cap = close * safe_shares
                assigned["fund_price_to_book"] = market_cap / safe_equity
                assigned["fund_earnings_yield"] = income / positive(market_cap)
            else:
                logger.info(
                    "FundamentalsEnricher: no close column, so the two ratios "
                    "that need a price are left absent; the rest are unaffected."
                )

        bar_times = _naive_utc(frame[time_column]).to_numpy(dtype="datetime64[ns]")
        staleness = (bar_times - latest_filed) / np.timedelta64(1, "D")
        fresh = np.isfinite(staleness) & (staleness >= 0) & (
            staleness <= self.max_staleness_days
        )

        for name, array in assigned.items():
            array = np.asarray(array, dtype=float)
            array = np.where(np.isfinite(array), array, np.nan)
            frame[name] = np.where(fresh, array, np.nan)
        frame["fund_days_since_report"] = np.where(fresh, staleness, np.nan)
        frame["fund_data_available"] = fresh.astype(int)

        covered = int(frame["fund_data_available"].sum())
        logger.info(
            "Fundamentals on %d of %d bars (%.1f%%), %d tickers with filings.",
            covered, len(frame), 100 * covered / max(1, len(frame)),
            facts["ticker"].nunique(),
        )
        return frame

    def _latest_filed(self, bars: pd.DataFrame, facts: pd.DataFrame,
                      total_rows: int) -> np.ndarray:
        """When the newest figure available at each bar was filed, positionally."""
        out = np.full(total_rows, np.datetime64("NaT"), dtype="datetime64[ns]")
        if bars.empty or facts.empty:
            return out
        right = (facts[["ticker", "filed"]]
                 .sort_values("filed")
                 .assign(_filed_at=lambda part: part["filed"]))
        # unbounded-on-purpose: and this one is the reason the other is safe.
        # It answers "how old is the newest filing at this bar", so it MUST
        # reach back however far: bounding it would return NaT for a company
        # that stopped filing, making "never filed" and "filed three years ago"
        # the same answer -- and the staleness mask exists to tell them apart.
        merged = pd.merge_asof(
            bars.sort_values("_bar"), right,
            left_on="_bar", right_on="filed", by="ticker", direction="backward",
        )
        out[merged["_pos"].to_numpy()] = merged["_filed_at"].to_numpy(
            dtype="datetime64[ns]"
        )
        return out
