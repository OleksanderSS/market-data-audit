"""Corporate filings as events, not as sentiment.

`sec_filings` was classified as a news source and fed into the news frame,
where it died: the table names its date column `filingDate` while the news
path's alias list said `filing_date`, so 24,365 dated, ticker-tagged filings
were discarded every run over the capital D. They were counted into a single
warning about 762,436 "lost news records", which hid which source they came
from.

Renaming the column would have been the wrong fix. What a filing carries is
`form`, `primaryDocDescription`, `accessionNumber` -- codes like "10-Q" and
"8-K", not prose. Handing those to the sentiment model would manufacture a
reading rather than recover one: FinBERT will return a number for the string
"10-Q" and it will be noise wearing the label of sentiment.

What a filing actually is: a company told the regulator something on a date.
That is an event, and events are measured by when they happen, how often, and
what kind -- which is what this builds.

Point in time: `acceptanceDateTime`, the second EDGAR accepted the filing.
The table also carries `reportDate`, the period the filing covers, which is
always earlier and is never what the market knew. Using it would date a June
disclosure to March. And `filingDate` alone is not enough either (#530): it is
a day with no hour, and a filing dated d floored to 00:00 reached every bar of
day d -- 42.86% of the 614,936 stored filings were accepted at or after 16:00
New York on their filingDate, so the daily bar of d, whose target starts at
that close, read them before they existed (8-K 44.70%, Form 4 67.41%).
`acceptanceDateTime` is true UTC despite looking like it might be New York
time with a `Z`: the EDGAR rule "accepted after 17:30 New York -> next
business day's filingDate" holds under the UTC reading (same day 98.86% before
17:15, 3.14% after 17:45) and fails under the other (96.88% after 17:45) --
`scripts/diagnostics/sec_acceptance_clock_530.py`. Where there is no hour (no
column, unparseable, or exactly 00:00:00 New York, which 11,816 old rows carry
as a bare date) the filing is known from `filingDate` plus
`filing_date_lag_days`, as for insider filings (#523).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from .base import BaseEnricher

logger = logging.getLogger(__name__)

#: Forms that announce something unscheduled -- an acquisition, a resignation,
#: a material agreement. These are the ones with news value.
MATERIAL_FORMS = ("8-K",)

#: Scheduled periodic reports. Their timing is known in advance, so their
#: information is in the content rather than the arrival.
PERIODIC_FORMS = ("10-K", "10-Q", "20-F", "40-F")

#: The second EDGAR accepted the filing, in true UTC (#530).
ACCEPTANCE_COLUMN = "acceptanceDateTime"
#: EDGAR's own clock, used only to recognise a bare date stored as midnight.
EDGAR_TZ = "America/New_York"


class CorporateFilingsEnricher(BaseEnricher):
    """Counts and recency of regulatory filings, per ticker, as of each bar."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__()
        self.config = config or {}
        self.window_days = int(self.config.get("window_days", 30))
        # Only for a filing with no acceptance hour: `filingDate` is a day,
        # and 42.86% of stored filings were accepted after that day's close
        # (#530), so the first bar that can know a filing dated d is d+1.
        self.filing_date_lag_days = int(self.config.get("filing_date_lag_days", 1))

    @property
    def name(self) -> str:
        return "corporate_filings"

    @property
    def priority(self) -> int:
        return 30  # after economic_calendar (29): both are date-keyed events

    def get_feature_names(self) -> list[str]:
        return [
            "filing_days_since_last",
            f"filing_count_{self.window_days}d",
            f"filing_material_{self.window_days}d",
            f"filing_periodic_{self.window_days}d",
            "filing_data_available",
        ]

    # ------------------------------------------------------------------ #

    def _enrich_impl(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if df.empty:
            return df

        filings = self._filings(kwargs)
        if filings is None or filings.empty:
            logger.warning(
                "No corporate filings available; filing event features not added."
            )
            return df

        frame = df.copy()
        restore_index = False
        if "datetime" not in frame.columns:
            if isinstance(frame.index, pd.DatetimeIndex):
                frame = frame.reset_index()
                if "index" in frame.columns and "datetime" not in frame.columns:
                    frame = frame.rename(columns={"index": "datetime"})
                restore_index = True
            else:
                logger.error(
                    "No 'datetime' column or DatetimeIndex; filings cannot be "
                    "placed in time. Bars returned unchanged."
                )
                return df

        if "ticker" not in frame.columns:
            logger.error(
                "No 'ticker' column; a filing belongs to one company and "
                "cannot be attached market-wide. Bars returned unchanged."
            )
            return df

        try:
            daily = self._cumulative_by_ticker(filings)
        except (ValueError, TypeError, KeyError) as exc:
            logger.error("Could not aggregate filings: %s", exc)
            return df
        if daily.empty:
            logger.warning("No filing carried both a ticker and a filing date.")
            return df

        bar_time = pd.to_datetime(frame["datetime"], errors="coerce")
        if getattr(bar_time.dt, "tz", None) is not None:
            # UTC, the clock of the acceptance times; dropping the zone without
            # converting would read a New York bar's wall time as UTC.
            bar_time = bar_time.dt.tz_convert("UTC").dt.tz_localize(None)

        counted = self._as_of_counts(bar_time, frame["ticker"], daily)

        window = self.window_days
        frame["filing_days_since_last"] = counted["days_since"].to_numpy()
        frame[f"filing_count_{window}d"] = counted["count"].to_numpy()
        frame[f"filing_material_{window}d"] = counted["material"].to_numpy()
        frame[f"filing_periodic_{window}d"] = counted["periodic"].to_numpy()
        # Absent is absent. A ticker with no filing on record is not a ticker
        # that has been quiet for zero days, and the two must not share a
        # number -- that is the mistake that put a neutral 0.0 in front of
        # every gate in this system.
        frame["filing_data_available"] = (
            counted["days_since"].notna().astype(int).to_numpy()
        )

        covered = int(frame["filing_data_available"].sum())
        logger.info(
            "Filing events attached to %d of %d bars (%.1f%%) across %d "
            "tickers; %d filings in the source spanning %s to %s.",
            covered, len(frame), 100 * covered / max(1, len(frame)),
            int(daily["ticker"].nunique()), int(daily["filings"].sum()),
            daily["_at"].min().date(), daily["_at"].max().date(),
        )
        if restore_index:
            frame = frame.set_index("datetime")
        return frame

    # ------------------------------------------------------------------ #

    def _filings(self, kwargs: dict) -> pd.DataFrame | None:
        """The stage hands its sources in; nothing is fetched here."""
        for key in ("sec_filings", "corporate_filings", "filings"):
            value = kwargs.get(key)
            if isinstance(value, pd.DataFrame) and not value.empty:
                return value
        return None

    def _cumulative_by_ticker(self, filings: pd.DataFrame) -> pd.DataFrame:
        """One row per (ticker, instant the filing became known) with running totals.

        Running totals make a window a subtraction: filings in the last N days
        is the total as of the bar minus the total as of N days earlier, and
        both are one backward as-of lookup.
        """
        date_col = self._date_column(filings)
        if date_col is None and ACCEPTANCE_COLUMN not in filings.columns:
            raise KeyError(
                f"filings carry no filing date; columns are {sorted(filings.columns)}"
            )
        if "ticker" not in filings.columns:
            raise KeyError("filings carry no ticker")

        table = filings.copy()
        table["_at"] = self._known_at(table, date_col)
        table["ticker"] = table["ticker"].astype(str).str.strip().str.upper()
        table = table.dropna(subset=["_at"])
        table = table[table["ticker"].ne("") & table["ticker"].ne("NAN")]
        if table.empty:
            return pd.DataFrame(columns=["ticker", "_at", "filings"])

        form = table.get("form", pd.Series("", index=table.index)).astype(str).str.upper()
        table["_material"] = form.str.startswith(MATERIAL_FORMS).astype(int)
        table["_periodic"] = form.str.startswith(PERIODIC_FORMS).astype(int)

        daily = (
            table.groupby(["ticker", "_at"])
            .agg(filings=("_at", "size"),
                 material=("_material", "sum"),
                 periodic=("_periodic", "sum"))
            .reset_index()
            .sort_values(["ticker", "_at"])
        )
        for column in ("filings", "material", "periodic"):
            daily[f"cum_{column}"] = daily.groupby("ticker")[column].cumsum()
        return daily

    def _known_at(self, table: pd.DataFrame, date_col: str | None) -> pd.Series:
        """The first instant a filing may be used, tz-naive UTC.

        The acceptance second where there is one; otherwise the filing day
        plus `filing_date_lag_days`. A bar at or after this instant sees it.
        """
        known = pd.Series(pd.NaT, index=table.index, dtype="datetime64[ns]")
        if ACCEPTANCE_COLUMN in table.columns:
            accepted = pd.to_datetime(table[ACCEPTANCE_COLUMN], errors="coerce", utc=True)
            local = accepted.dt.tz_convert(EDGAR_TZ)
            bare_date = (local.dt.hour == 0) & (local.dt.minute == 0) & (local.dt.second == 0)
            known = accepted.dt.tz_localize(None).where(~bare_date).astype("datetime64[ns]")
        if date_col is not None:
            day = pd.to_datetime(table[date_col], errors="coerce", utc=True)
            fallback = (day.dt.tz_localize(None).dt.floor("D")
                        + pd.Timedelta(days=self.filing_date_lag_days))
            known = known.fillna(fallback.astype("datetime64[ns]"))
        return known

    @staticmethod
    def _date_column(filings: pd.DataFrame) -> str | None:
        """`filingDate` is when it became public. `reportDate` is not.

        The period a filing covers is always earlier than the day it was filed,
        so reading it as the event time backdates every disclosure and lets a
        model see a June statement in March.
        """
        for candidate in ("filingDate", "filing_date", "filed_at", "published_at"):
            if candidate in filings.columns:
                return candidate
        return None

    def _as_of_counts(
        self,
        bar_time: pd.Series,
        tickers: pd.Series,
        daily: pd.DataFrame,
    ) -> pd.DataFrame:
        """Totals known at each bar, and the same totals a window earlier."""
        left = pd.DataFrame({
            "_bar": bar_time.to_numpy().astype("datetime64[ns]"),
            "ticker": tickers.astype(str).str.strip().str.upper().to_numpy(),
        })
        left["_pos"] = np.arange(len(left))
        left = left.dropna(subset=["_bar"])

        right = daily.copy()
        right["_at"] = right["_at"].to_numpy().astype("datetime64[ns]")
        right = right.sort_values("_at")

        cum_cols = ["cum_filings", "cum_material", "cum_periodic"]
        # unbounded-on-purpose: these are CUMULATIVE counters (`cumsum` above),
        # not levels. Carrying a running total forward is not a stale reading:
        # if no filing happened since March, March's total IS today's total,
        # and a `tolerance=` here would blank the count for every quiet company
        # instead of reporting the truth that nothing was filed.
        now = pd.merge_asof(
            left.sort_values("_bar"), right[["ticker", "_at", *cum_cols]],
            left_on="_bar", right_on="_at", by="ticker", direction="backward",
        )

        earlier_left = left.copy()
        earlier_left["_bar"] = earlier_left["_bar"] - pd.Timedelta(days=self.window_days)
        # unbounded-on-purpose: the same cumulative counters, read at an
        # earlier bar so the pair gives the count WITHIN the window by
        # subtraction. Bounding this leg and not the other would make the
        # difference between them meaningless.
        earlier = pd.merge_asof(
            earlier_left.sort_values("_bar"), right[["ticker", "_at", *cum_cols]],
            left_on="_bar", right_on="_at", by="ticker", direction="backward",
        )
        earlier = earlier.set_index("_pos").reindex(now["_pos"].to_numpy())

        out = pd.DataFrame(
            index=range(len(bar_time)),
            columns=["days_since", "count", "material", "periodic"],
            dtype=float,
        )
        positions = now["_pos"].to_numpy()

        # A ticker with no filing at or before the bar has nothing to report;
        # NaN here becomes filing_data_available = 0 rather than a zero count.
        seen = now["cum_filings"].notna().to_numpy()
        days_since = (now["_bar"] - now["_at"]).dt.days.to_numpy(dtype="float64")

        # No filing a window ago means nothing had happened yet: zero is the
        # right baseline there, unlike in the "never filed" case above.
        before = {c: np.nan_to_num(earlier[c].to_numpy(dtype="float64"), nan=0.0)
                  for c in cum_cols}

        out.loc[positions, "days_since"] = np.where(seen, days_since, np.nan)
        for name, column in (("count", "cum_filings"),
                             ("material", "cum_material"),
                             ("periodic", "cum_periodic")):
            delta = now[column].to_numpy(dtype="float64") - before[column]
            out.loc[positions, name] = np.where(seen, delta, np.nan)
        return out
