"""Which clock `acceptanceDateTime` of an SEC submissions response is on, and the true UTC instant (#668).

WHY. The field ends in `Z`, and #530 (03.10) measured it as true UTC on the stored table. On 10.10 the
EDGAR filing pages (their "Accepted" line is New York time) showed that SEC serves THREE clocks under the
same `Z`, changing from one day to the next:

    utc            the true instant                       Apple 8-K 30.07.2026: 20:30:28Z (EDGAR 16:30:28)
    ny_wall        New York wall time with a Z stuck on   JPM 424B2 14.09.2026: 16:44:21Z (EDGAR 16:44:21)
    utc_plus_ny    the true instant plus New York's       the same Apple 8-K served on 10.10: 00:30:28Z
                   offset (4 h in summer, 5 h in winter)  of the 31st; JPM 14.07 8-K: 14:30:38Z (EDGAR 06:30:38)

`ny_wall` puts a filing 4-5 h EARLY (a 16:44 filing looks like 12:44 New York -- before the close: a leak);
`utc_plus_ny` puts it 4-5 h LATE (an evening filing moves to the next day). In `sec_filings` the rows of
21.09-05.10 were `utc_plus_ny` and some JPM rows of 11-18.09 `ny_wall`.

HOW. One response holds hundreds of filings of one company, and EDGAR accepts filings 06:00-22:00 New York,
never after the filing's own `filingDate`. Under the right reading almost none breaks that; a 4-5 h shift
pushes the morning or the evening block out. `detect` returns the reading that is clean (<= MAX_BAD) and
clearly better than the next one (by MARGIN), or None when a response is too small or too mid-day to tell.
A bare date -- minutes and seconds both zero: EDGAR serves a date without an hour as New York midnight
(04:00Z / 05:00Z) or as 00:00Z -- is excluded from DETECTION (on 10.10 AMGN's 2002 batch had 164 such rows of 186, and counting them as
real hours picked the wrong clock) but CONVERTED with its response's clock: SEC shifts it too (NKE S-3/A
22.04.1999, EDGAR "00:00:00", stored 04:00Z, served on 10.10 as 08:00Z). An undecided response gives no hour
at all (None), bare or not: the enricher then takes the filing day plus one.
"""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

NY = "America/New_York"
READINGS = ("utc", "ny_wall", "utc_plus_ny")
#: Margins, not knife edges: on 10.10 the right reading broke 0.9% (AAPL, 1,001 filings) and 0.03% (JPM);
#: the wrong ones 18-93% -- but for a company that files mid-day the wrong one breaks only its 06-10 or
#: 18-22 filings (GOOGL: 0.0% against 3.1% of 1,000). So the gap is asked in two units: >= MARGIN of the
#: response AND >= MIN_GAP filings.
MIN_N, MAX_BAD, MARGIN, MIN_GAP = 20, 0.03, 0.02, 10
FMT = "%Y-%m-%dT%H:%M:%S.000Z"


def _parse(raw: Sequence) -> pd.Series:
    return pd.to_datetime(pd.Series(list(raw), dtype="object"), errors="coerce", utc=True)


def _bare(t: pd.Series) -> pd.Series:
    return (t.dt.minute == 0) & (t.dt.second == 0)


def truth(raw: Sequence, reading: str) -> pd.Series:
    """True UTC instants (tz-aware) of the raw strings under one reading; NaT where it cannot be read."""
    t = _parse(raw)
    if reading == "utc":
        return t
    if reading == "ny_wall":
        return (t.dt.tz_localize(None).dt.tz_localize(NY, ambiguous="NaT", nonexistent="NaT")
                .dt.tz_convert("UTC"))
    if reading == "utc_plus_ny":
        c4 = t - pd.Timedelta(hours=4)
        summer = c4.dt.tz_convert(NY).apply(
            lambda x: x.utcoffset() == pd.Timedelta(hours=-4) if pd.notna(x) else False)
        return c4.where(summer.astype(bool), t - pd.Timedelta(hours=5))
    raise ValueError(reading)


def bad_share(raw: Sequence, filing_dates: Sequence, reading: str) -> tuple[float, int]:
    """Share of non-bare filings that break EDGAR's window under a reading, and how many were judged."""
    t = _parse(raw)
    keep = t.notna() & ~_bare(t)
    tr = truth(raw, reading)[keep]
    fd = pd.to_datetime(pd.Series(list(filing_dates), dtype="object"), errors="coerce")[keep]
    ny = tr.dt.tz_convert(NY)
    hour = ny.dt.hour + ny.dt.minute / 60
    bad = tr.isna() | (hour < 6) | (hour >= 22) | (ny.dt.tz_localize(None).dt.normalize() > fd)
    n = int(keep.sum())
    return (float(bad.mean()) if n else 1.0), n


def detect(raw: Sequence, filing_dates: Sequence) -> str | None:
    scores = {r: bad_share(raw, filing_dates, r) for r in READINGS}
    n = next(iter(scores.values()))[1]
    if n < MIN_N:
        return None
    ranked = sorted(READINGS, key=lambda r: scores[r][0])
    best, second = scores[ranked[0]][0], scores[ranked[1]][0]
    if best <= MAX_BAD and second - best >= MARGIN and (second - best) * n >= MIN_GAP:
        return ranked[0]
    return None


def to_true_utc(raw: Sequence, reading: str | None) -> list[str | None]:
    """The raw strings rewritten as true UTC under the response's reading; no reading -> None (unknown hour)."""
    if reading is None:
        return [None] * len(list(raw))
    tr = truth(raw, reading)
    return [y.strftime(FMT) if pd.notna(y) else None for y in tr]
