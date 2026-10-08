"""Are long shots overpriced on Manifold (play money)? (#587, attempt 1 of 2)

Pre-registered in `docs/preregistration/2026-10-07_manifold_longshot_587.md`, committed before
this instrument and before any fetch (c6421bb9). Raw responses are stored BEFORE any computation:

    --fetch     search-markets pages (resolved, BINARY, newest, 1 000 a page via beforeTime, up to 20 000;
                amendment of the pre-registration, 07.10) and,
                for every market that passes the filters, the last bet before T = min(close, resolution)
                - 7 days -> data/diagnostic_fetches/manifold_587/<stamp>/
    (default)   analysis from the latest saved fetch, no network

Filters: resolution YES or NO; uniqueBettorCount >= 20; T >= created + 1 day; a bet before T exists.
Long-shot bin p in [0.02, 0.15): B = mean p - share YES; z = B / (sqrt(sum p(1-p)) / N); rule z >= 1.645
(within 0.10 -> not passed). Guard first, from prices only: MDE = 2.80 sqrt(mean p(1-p) / N) > 0.030 -> stop.
K1 outcomes ~ Bernoulli(p), 200 draws: z >= 1.645 in <= 10%. K2 long shots ~ Bernoulli(p - 0.05): found in >= 80%.
K3 bin [0.45, 0.55]: share YES in [0.40, 0.60]. Mirror: favourites (0.85, 0.98], share YES - mean p (described).

    python -u scripts/diagnostics/manifold_longshot_587.py --fetch
    python -u scripts/diagnostics/manifold_longshot_587.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / "data" / "diagnostic_fetches" / "manifold_587"
API = "https://api.manifold.markets/v0"
DAY_MS = 86_400_000
PAGES, PAGE, PAUSE = 20, 1000, 0.15
LONG, FAV, MID = (0.02, 0.15), (0.85, 0.98), (0.45, 0.55)
MDE_MAX, Z_RULE, Z_EDGE, SEED = 0.030, 1.645, 0.10, 587


def get(url: str):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research"}), timeout=60) as r:
                return r.read()
        except Exception:  # noqa: BLE001 -- retried, then raised
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def eligible(m: dict) -> int | None:
    if m.get("resolution") not in ("YES", "NO") or (m.get("uniqueBettorCount") or 0) < 20:
        return None
    end = min(x for x in (m.get("closeTime"), m.get("resolutionTime")) if x)
    T = int(end) - 7 * DAY_MS
    return T if T >= int(m["createdTime"]) + DAY_MS else None


def fetch() -> None:
    out = HOME / time.strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True)
    markets = []
    before = ""
    for k in range(PAGES):
        raw = get(f"{API}/search-markets?term=&filter=resolved&contractType=BINARY&sort=newest"
                  f"&limit={PAGE}{before}")
        (out / f"search_{k:02d}.json").write_bytes(raw)
        page = json.loads(raw)
        markets += page
        print(f"  page {k}: {len(page)}", flush=True)
        time.sleep(PAUSE)
        if len(page) < PAGE:
            break
        before = f"&beforeTime={min(int(m['createdTime']) for m in page)}"
    bets = out / "bets"
    bets.mkdir()
    todo = [(m["id"], eligible(m)) for m in markets if eligible(m)]
    print(f"markets {len(markets)}, eligible before the price {len(todo)}", flush=True)
    for n, (cid, T) in enumerate(todo, 1):
        (bets / f"{cid}.json").write_bytes(get(f"{API}/bets?contractId={cid}&beforeTime={T}&limit=1"))
        time.sleep(PAUSE)
        if n % 250 == 0:
            print(f"  bets {n}/{len(todo)}", flush=True)
    print(f"saved -> {out.relative_to(ROOT)}")


def z_of(p: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    B = p.mean() - y.mean()
    return B, B / (np.sqrt((p * (1 - p)).sum()) / len(p))


def analyse() -> int:
    src = sorted(d for d in HOME.iterdir() if d.is_dir() and (d / "bets").exists())[-1]
    markets = [m for f in sorted(src.glob("search_*.json")) for m in json.loads(f.read_bytes())]
    rows, no_bet = [], 0
    for m in markets:
        T = eligible(m)
        f = src / "bets" / f"{m['id']}.json"
        if not T or not f.exists():
            continue
        b = json.loads(f.read_bytes())
        if not b:
            no_bet += 1
            continue
        rows.append({"id": m["id"], "creator": m.get("creatorId"), "p": float(b[0]["probAfter"]),
                     "yes": 1.0 if m["resolution"] == "YES" else 0.0})
    df = pd.DataFrame(rows)
    print(f"source {src.relative_to(ROOT)}; markets {len(markets)}, with a price at T {len(df)}, no bet before T {no_bet}")
    lo = df[(df["p"] >= LONG[0]) & (df["p"] < LONG[1])]
    p, y = lo["p"].to_numpy(), lo["yes"].to_numpy()
    mde = 2.80 * np.sqrt((p * (1 - p)).mean() / len(p))
    print(f"long-shot bin {LONG}: N {len(p)}, MDE {mde:.4f}")
    if mde > MDE_MAX:
        print(f"GUARD: MDE {mde:.4f} > {MDE_MAX} -> НЕДОСТАТНЯ СИЛА; B not computed")
        return 2
    rng = np.random.default_rng(SEED)
    k1 = np.mean([z_of(p, (rng.random(len(p)) < p).astype(float))[1] >= Z_RULE for _ in range(200)])
    k2 = np.mean([z_of(p, (rng.random(len(p)) < np.clip(p - 0.05, 0, 1)).astype(float))[1] >= Z_RULE for _ in range(200)])
    mid = df[(df["p"] >= MID[0]) & (df["p"] <= MID[1])]
    k3 = mid["yes"].mean()
    print(f"K1 null: z >= {Z_RULE} in {k1:.0%} -> {'PASS' if k1 <= 0.10 else 'FAIL'}")
    print(f"K2 planted -0.05: found in {k2:.0%} -> {'PASS' if k2 >= 0.80 else 'FAIL'}")
    print(f"K3 bin {MID}: N {len(mid)}, share YES {k3:.3f} -> {'PASS' if 0.40 <= k3 <= 0.60 else 'FAIL'}")

    B, z = z_of(p, y)
    g = lo.assign(r=lo["p"] - lo["yes"]).groupby("creator")["r"].agg(["sum", "count"])
    se_cl = np.sqrt(((g["sum"] - g["count"] * B) ** 2).sum()) / len(p)
    print(f"\nLONG SHOTS: mean p {p.mean():.4f}, share YES {y.mean():.4f}, B {B:+.4f}, z {z:+.2f} "
          f"(creator-clustered z {B / se_cl:+.2f}, {len(g)} creators)")
    fav = df[(df["p"] > FAV[0]) & (df["p"] <= FAV[1])]
    print(f"MIRROR favourites {FAV}: N {len(fav)}, mean p {fav['p'].mean():.4f}, share YES {fav['yes'].mean():.4f}, "
          f"YES - p {fav['yes'].mean() - fav['p'].mean():+.4f}")
    print("calibration (bins of 0.1):")
    df["bin"] = np.minimum((df["p"] * 10).astype(int), 9)
    for bn, gg in df.groupby("bin"):
        print(f"  {bn / 10:.1f}-{(bn + 1) / 10:.1f}: N {len(gg):5d}  mean p {gg['p'].mean():.3f}  share YES {gg['yes'].mean():.3f}")
    if abs(z - Z_RULE) <= Z_EDGE:
        verdict = "НЕ ПРОЙДЕНО (впритул)"
    else:
        verdict = "ТАК: аутсайдери переоцінені" if z >= Z_RULE else "НІ: переоцінки аутсайдерів не видно"
    print(f"VERDICT: {verdict} (B {B:+.4f}, z {z:+.2f}, MDE {mde:.4f})")
    df.to_csv(ROOT / "diagnostic_reports" / "manifold_longshot_587.csv", index=False)
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    if ap.parse_args().fetch:
        fetch()
        return 0
    return analyse()


if __name__ == "__main__":
    sys.exit(main())
