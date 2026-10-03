"""Codex 02.10, «SEC fundamentals: filed date дає causal ordering по днях, але
не intraday доступність» -- the shape of #523 and #530 in a third enricher.
Read-only, the database only.

`FundamentalsEnricher` reads `filed` (a day, stored as midnight) and joins
facts to bars with a backward `merge_asof` on it, so a fact filed on day d
reaches every bar of d from 00:00 -- the daily bar of d, entry of a
close-to-next-close target, and the 13:30 UTC open bar -- whatever hour EDGAR
accepted the filing (code read 03.10 before this file). `sec_fundamentals`
carries `accession`; `sec_filings` carries `accessionNumber` and
`acceptanceDateTime`, true UTC (#530, measured against EDGAR's 17:30 rule).

RULE. Distinct (accession, filed) pairs of `sec_fundamentals`, joined to
`sec_filings` on the accession. Acceptance read as UTC, converted to New York;
a bare date (exactly 00:00:00 New York) counts as no hour and is left out.
  daily leak    -- accepted at or after 16:00 New York on the `filed` day;
  intraday leak -- accepted at or after 09:30 New York on the `filed` day.
  CONFIRMED if the daily share is 1% or more of the joined pairs.
  The join itself is reported: if under 50% of pairs find an acceptance time,
  STOPPED -- the shares would describe a minority.
PREDICTION, derived from #530's per-form numbers, not guessed: the facts come
from 10-Q and 10-K filings, whose shares there were daily 37.71% / 42.02% and
intraday 66.11% / 67.54%; 10-Qs are three of every four periodic filings, so
daily 35-45%, intraday 60-70%. Join coverage: 90% or more (same companies,
same EDGAR, `sec_filings` reaches back to 1996). Attempt 1 of 1.

CONTROL WITH A KNOWN ANSWER: `filed` and the acceptance day agree for a
filing accepted before 17:30 New York (EDGAR dates it that day) -- among pairs
accepted 06:00-17:15 New York, the acceptance day equals `filed` in 95% or more,
the same check that settled the clock in #530. Fail -> STOPPED.

    python -u scripts/diagnostics/fundamentals_filed_clock_535.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "trading_data.duckdb"
NY = "America/New_York"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    con = duckdb.connect(str(DB), read_only=True)
    try:
        pairs = con.execute(
            "select distinct f.accession, f.filed, f.form, s.acceptanceDateTime "
            "from sec_fundamentals f left join (select distinct accessionNumber, acceptanceDateTime "
            "from sec_filings) s on s.accessionNumber = f.accession"
        ).fetchdf()
    finally:
        con.close()
    n_all = len(pairs)
    accepted = pd.to_datetime(pairs["acceptanceDateTime"], errors="coerce", utc=True)
    local = accepted.dt.tz_convert(NY).dt.tz_localize(None)
    bare = (local.dt.hour == 0) & (local.dt.minute == 0) & (local.dt.second == 0)
    ok = local.notna() & ~bare
    filed = pd.to_datetime(pairs["filed"], errors="coerce").dt.normalize()
    joined = int(ok.sum())
    print(f"distinct (accession, filed) pairs {n_all:,}; with an acceptance hour {joined:,} "
          f"({joined / max(1, n_all):.2%}); bare dates {int((local.notna() & bare).sum()):,}   (prediction >= 90%)")
    if joined / max(1, n_all) < 0.5:
        print("STOPPED: under 50% of pairs found an acceptance time")
        return 1

    minutes = local.dt.hour * 60 + local.dt.minute
    same = ok & (local.dt.normalize() == filed)
    early = ok & (minutes >= 6 * 60) & (minutes < 17 * 60 + 15)
    p_ctrl = float(same[early].mean())
    print(f"control: acceptance day == filed | accepted 06:00-17:15 NY: {p_ctrl:.2%} (n {int(early.sum()):,}) "
          f"-- {'pass' if p_ctrl >= 0.95 else 'FAIL'}")
    if p_ctrl < 0.95:
        print("STOPPED: control failed")
        return 1

    daily = same & (minutes >= 16 * 60)
    intraday = same & (minutes >= 9 * 60 + 30)
    print(f"daily leak    (>= 16:00 NY on filed): {daily.sum() / joined:.2%}   (prediction 35-45%)")
    print(f"intraday leak (>= 09:30 NY on filed): {intraday.sum() / joined:.2%}   (prediction 60-70%)")
    form = pairs["form"].astype(str).str.upper()
    for f in sorted(form[ok].value_counts().head(4).index):
        m = ok & (form == f)
        print(f"   form {f:<8} pairs {int(m.sum()):>6,}  daily {daily[m].mean():.2%}  intraday {intraday[m].mean():.2%}")
    print(f"\nverdict: {'CONFIRMED' if daily.sum() / joined >= 0.01 else 'NOT CONFIRMED at scale'} "
          f"(rule: daily share >= 1%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
