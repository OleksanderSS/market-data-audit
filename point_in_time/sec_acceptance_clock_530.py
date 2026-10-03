"""#530: when does a stored SEC filing become knowable, and how far ahead of
that does `CorporateFilingsEnricher` show it? Read-only, the database only.

The enricher dates a filing by `filingDate` floored to the day, and a backward
as-of join hands it to every bar of that day -- from 00:00, so to the 13:30 UTC
open bar and to the daily bar of that day (the entry of a close-to-next-close
target) -- whatever hour EDGAR accepted it. The table also carries
`acceptanceDateTime` on all 614,936 rows (schema read 03.10 before this file).

Q1. WHICH CLOCK `acceptanceDateTime` is on. The strings end in `Z`. Two readings:
  A  literal UTC: convert to New York time.
  B  New York wall time with a `Z` stuck on: read the digits as New York time.
  KNOWN ANSWER that decides it: EDGAR accepts filings 06:00-22:00 New York
  time. Under the right reading almost no acceptance falls outside that
  window; under the wrong one, a 4-5 hour shift pushes a block of them out
  (06:00-10:00 under B becomes 01:00-06:00 under A, or 18:00-22:00 under A
  becomes 22:00-03:00 under B).
  RULE: the reading with no more than 1% of acceptances outside 06:00-22:00
  New York is the clock; if both or neither pass, STOPPED -- no fix is written
  on a clock that is not known.
  PREDICTION: B passes (under 1% outside), A fails (5% or more outside).

Q2. THE SIZE OF THE LEAK under the clock Q1 picks, every row with both fields:
  intraday -- accepted at or after 09:30 New York on its own filingDate: the
    old code shows it to that day's 15m bars from the open, before it exists;
  daily -- accepted at or after 16:00 New York on its own filingDate: the old
    code shows it to that day's daily bar, whose target starts at that close.
  RULE: #530 is CONFIRMED if the daily share is 1% or more (a share below that
  is still a defect in the code, but not the one Codex described at scale).
  PREDICTION (a guess, no pilot: nobody has read these hours before): intraday
  60-85%, daily 15-35%. Printed per form for 8-K, 10-Q, 10-K and 4 -- printed,
  not the verdict.

Attempt 1 of 1. Rule and prediction committed before the first run.

RESULT OF ATTEMPT 1 (03.10, commit 008209c2): STOPPED. Outside the window:
A literal UTC 2.08%, B New York wall 25.31%. Neither under 1%; the prediction
(B) was WRONG -- B is the worse reading by a factor of twelve. The 1% is not
moved.

ATTEMPT 2 (written after attempt 1 and before any look at which rows fall
outside; a DIFFERENT known answer, not a looser threshold). EDGAR gives a
filing accepted after 17:30 New York the NEXT business day's filingDate;
Section 16 forms (3, 4, 5 and their amendments) keep the same day until
22:00, so they are left out of this control. Under the right reading, for the
other forms:
  P(filingDate is the acceptance day | accepted 06:00-17:15 NY) >= 95%, and
  P(filingDate is the acceptance day | accepted 17:45-22:00 NY) <= 5%
(15 minutes kept clear on each side of 17:30). RULE: the one reading that
meets both is the clock; otherwise STOPPED. PREDICTION: A meets both, B fails.
Q2 then as above, unchanged. Printed, not the verdict: the rows outside
06:00-22:00 under the chosen clock, by decade of filingDate and by second
(a 00:00:00 acceptance is a date with no hour).

    python -u scripts/diagnostics/sec_acceptance_clock_530.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "trading_data.duckdb"
NY = "America/New_York"
OPEN_H, CLOSE_H = 6, 22          # EDGAR acceptance window, New York
MAX_OUTSIDE = 0.01
CONFIRM_DAILY = 0.01


def load() -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    try:
        df = con.execute(
            "select ticker, form, filingDate, acceptanceDateTime from sec_filings"
        ).fetchdf()
    finally:
        con.close()
    return df


def readings(raw: pd.Series) -> dict[str, pd.Series]:
    """Both readings as New York wall time, tz-naive."""
    literal = pd.to_datetime(raw, errors="coerce", utc=True)
    a = literal.dt.tz_convert(NY).dt.tz_localize(None)
    b = literal.dt.tz_localize(None)     # the digits as written
    return {"A literal UTC": a, "B New York wall": b}


def outside_share(ny: pd.Series) -> float:
    hour = ny.dt.hour + ny.dt.minute / 60
    ok = ny.notna()
    return float(((hour < OPEN_H) | (hour >= CLOSE_H))[ok].mean())


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    df = load()
    filed = pd.to_datetime(df["filingDate"], errors="coerce")
    print(f"rows {len(df):,}; acceptance parsed "
          f"{pd.to_datetime(df['acceptanceDateTime'], errors='coerce', utc=True).notna().sum():,}; "
          f"filingDate parsed {filed.notna().sum():,}")

    form = df["form"].astype(str).str.upper()
    section16 = form.str.replace("/A", "", regex=False).isin(["3", "4", "5"])
    passing = []
    for name, ny in readings(df["acceptanceDateTime"]).items():
        print(f"attempt 1  {name:<18} outside {OPEN_H:02d}:00-{CLOSE_H:02d}:00 NY: "
              f"{outside_share(ny):.2%}")
        minutes = ny.dt.hour * 60 + ny.dt.minute
        same = ny.dt.normalize() == filed
        early = ~section16 & (minutes >= 6 * 60) & (minutes < 17 * 60 + 15)
        late = ~section16 & (minutes >= 17 * 60 + 45) & (minutes < 22 * 60)
        p_early, p_late = float(same[early].mean()), float(same[late].mean())
        ok = p_early >= 0.95 and p_late <= 0.05
        print(f"attempt 2  {name:<18} same-day filingDate | 06:00-17:15 {p_early:.2%} "
              f"(n {int(early.sum()):,}), | 17:45-22:00 {p_late:.2%} (n {int(late.sum()):,})"
              f" -- {'meets both' if ok else 'fails'}")
        if ok:
            passing.append(name)
    if len(passing) != 1:
        print(f"STOPPED: {len(passing)} readings meet the 17:30 rule -- clock unknown")
        return 1
    clock = passing[0]
    print(f"Q1 clock: {clock}   (attempt 2 prediction: A literal UTC)")

    ny = readings(df["acceptanceDateTime"])[clock]
    out = ny.notna() & ((ny.dt.hour < OPEN_H) | (ny.dt.hour >= CLOSE_H))
    midnight = out & (ny.dt.hour == 0) & (ny.dt.minute == 0) & (ny.dt.second == 0)
    print(f"outside the window under {clock}: {int(out.sum()):,}; at exactly 00:00:00 "
          f"{int(midnight.sum()):,}; by decade of filingDate: "
          f"{(filed[out].dt.year // 10 * 10).value_counts().sort_index().to_dict()}")
    raw_midnight = pd.to_datetime(df["acceptanceDateTime"], errors="coerce", utc=True)
    raw_midnight = (raw_midnight.dt.hour == 0) & (raw_midnight.dt.minute == 0) & (raw_midnight.dt.second == 0)
    print(f"raw strings at exactly T00:00:00: {int(raw_midnight.sum()):,}")
    both = ny.notna() & filed.notna()
    same_day = both & (ny.dt.normalize() == filed)
    minutes = ny.dt.hour * 60 + ny.dt.minute
    intraday = same_day & (minutes >= 9 * 60 + 30)
    daily = same_day & (minutes >= 16 * 60)
    n = int(both.sum())
    print(f"\nQ2 rows with both fields {n:,}; accepted on its own filingDate (NY) "
          f"{same_day.sum() / n:.2%}; on a LATER day than filingDate "
          f"{(both & (ny.dt.normalize() > filed)).sum() / n:.2%}; on an EARLIER day "
          f"{(both & (ny.dt.normalize() < filed)).sum() / n:.2%}")
    print(f"Q2 intraday leak (>= 09:30 NY on filingDate): {intraday.sum() / n:.2%}   "
          f"(prediction 60-85%)")
    print(f"Q2 daily leak    (>= 16:00 NY on filingDate): {daily.sum() / n:.2%}   "
          f"(prediction 15-35%)")
    for f in ("8-K", "10-Q", "10-K", "4"):
        m = both & (form == f)
        if m.sum():
            print(f"   form {f:<5} rows {int(m.sum()):>8,}  intraday {intraday[m].mean():.2%}  "
                  f"daily {daily[m].mean():.2%}")
    verdict = "CONFIRMED" if daily.sum() / n >= CONFIRM_DAILY else "NOT CONFIRMED at scale"
    print(f"\n#530 verdict: {verdict} (rule: daily share >= {CONFIRM_DAILY:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
