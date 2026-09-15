"""loaded_level_scalp.py — the Loaded Level setup as a SCALP: timeframes 5m to 1h, near targets, two
exits, picked on explore data by a rule fixed before any result was seen, then ONE test on months
the pick never saw.

A STUDY on `loaded_level_study.py` — same detector, same fills, same costs, same single position
slot, no Pine twin, so every number is a lab finding. What it changes it changes in the open, for
this process only:
  TIMEFRAME  5m and 15m read their own bars; 30m and 1h are resampled UP from 15m. The study's time
             constants are rescaled to mean the same HOURS on every timeframe — sweep look-back 2h,
             setup expiry 3 days, max hold 2 days, pool age 3 days (the study holds 4 days on 5m).
  TARGET     adds "half": halfway from the entry to "4".
  EXIT       "fixed" is the study's own walk. "half@0.5R+BE" closes half at +0.5R and moves the rest
             to breakeven. Same bar order as the study: stop, then target, then the arm, and an
             armed stop counts only from the NEXT bar.

THE PROCEDURE — the order is the point:
  explore  the grid on bars before HOLDOUT only; one CSV per timeframe.
  pick     eligible = >= 30 trades in EACH half and positive in both; ranked by the WORSE half;
           kept only if most one-setting neighbours are positive too (a plateau, not a spike).
  check    shortlisted cells, still before HOLDOUT, against random entries matched on direction,
           stop distance, target distance and exit. The pick is the highest-ranked plateau cell
           that beats them at z >= 2.
  holdout  that ONE cell, trades from HOLDOUT on.
🔴 THE HOLDOUT WAS SPENT ON 2026-09-14 and the pick lost on it (docs/DAVINCI_MODEL_SPEC.md →
   "Scalp sweet spot"). Running `holdout` on another cell now is not a test: every extra look
   turns those months into in-sample data.

Usage:
  python backtest/tools/loaded_level_scalp.py explore --tf 5      # and --tf 15, 30, 60
  python backtest/tools/loaded_level_scalp.py pick
  python backtest/tools/loaded_level_scalp.py check --tf 5 --cells '[{"dir": "both", ...}, ...]'
  python backtest/tools/loaded_level_scalp.py holdout --tf 5 --cells '{"dir": "both", ...}'
A cell names dir, target, floor, min_risk, min_range, touches, need_sos and exit (default "fixed").
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loaded_level_study as S  # noqa: E402

HOLDOUT = pd.Timestamp("2025-09-01")
TIMEFRAMES = (5, 15, 30, 60)
EXITS = {"fixed": {"mode": "fixed"}, "half@0.5R+BE": {"mode": "part", "at": 0.5, "frac": 0.5}}
GRID = {
    "target": ("4", "named", "half"),
    "floor": (0.0, 0.5, 1.0),
    "touches": (1, 2),
    "need_sos": (False, True),
    "min_range": (0.0, 10.0),
    "min_risk": (0.0, 2.0),
    "dir": ("both", "short", "long"),
}
KEY = ["tf", "exit", *GRID]
CELL_KEYS = {"dir", "entry", "target", "floor", "min_risk", "min_range", "touches", "need_sos"}
MIN_PER_HALF = 30
Z_TO_BEAT = 2.0

RULE: dict = dict(EXITS["fixed"])
_NEVER = 10**9


def _first(mask: np.ndarray, off: int = 0) -> int:
    idx = np.flatnonzero(mask)
    return off + int(idx[0]) if len(idx) else _NEVER


def walk(self, i, entry, stop, target, force=False):
    """The study's walk with RULE's exit on top. Replaces `S.Book.walk` in THIS process only, so
    the random-entry control walks under the same exit as the setup it is matched to."""
    if not force and self.H[i] < entry + self.en:
        return None
    end = min(i + S.MAX_HOLD, self.n - 1)
    ex, risk = self.ex, stop - entry
    H_, L_, O_ = self.H[i : end + 1], self.L[i : end + 1], self.O[i : end + 1]
    t0 = 0 if force else 1

    def fill(j, lvl):  # a stop the bar opened through fills at that open
        return O_[j] + ex if (force or j > 0) and O_[j] + ex > lvl else lvl

    js, jt = _first(H_ >= stop - ex), _first(L_[t0:] <= target - ex, t0)
    armed = RULE["mode"] != "fixed"
    ja = _first(L_[t0:] <= entry - RULE["at"] * risk - ex, t0) if armed else _NEVER
    if js < _NEVER and js <= min(jt, ja):
        return i + js, (entry - fill(js, stop)) / risk, "stop"
    if jt < _NEVER and jt <= ja:
        return i + jt, (entry - min(target, O_[jt] + ex)) / risk, "target"
    if ja < _NEVER:
        part = RULE["mode"] == "part"
        locked, rest = (RULE["frac"] * RULE["at"], 1 - RULE["frac"]) if part else (0.0, 1.0)
        a1 = ja + 1
        if a1 <= len(H_) - 1:
            j2s, j2t = _first(H_[a1:] >= entry - ex, a1), _first(L_[a1:] <= target - ex, a1)
            if j2s < _NEVER and j2s <= j2t:
                return i + j2s, locked + rest * (entry - fill(j2s, entry)) / risk, "be"
            if j2t < _NEVER:
                return i + j2t, locked + rest * (entry - min(target, O_[j2t] + ex)) / risk, "target"
        return end, locked + rest * (entry - (self.C[end] + ex)) / risk, "time"
    return end, (entry - (self.C[end] + ex)) / risk, "time"


_study_targets = S.targets


def targets(side, mode: str):
    """The study's targets plus "half": halfway from the entry to "4"."""
    if mode == "half":
        return (side.c["entry"] + side.c["low4"]) / 2
    return _study_targets(side, mode)


S.Book.walk = walk
S.targets = targets


def load(tf: int, a: argparse.Namespace) -> pd.DataFrame:
    base = "M5" if tf == 5 else "M15"
    path = S.ROOT / "backtest" / "cache" / a.server_dir / f"{a.symbol}__{base}.csv"
    df = pd.read_csv(path, parse_dates=["time"]).set_index("time")
    df = df[df.index >= a.start][["open", "high", "low", "close"]].astype(float)
    if tf in (30, 60):
        agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
        df = df.resample(f"{tf}min", label="left", closed="left").agg(agg).dropna()
    return df if a.mode == "holdout" else df[df.index < HOLDOUT]


def build(tf: int, raw: pd.DataFrame, profile: str) -> tuple[dict, dict]:
    per_hour = 60 // tf
    S.SWEEP_LB, S.EXPIRY, S.MAX_HOLD, S.POOL_AGE = (
        2 * per_hour,
        72 * per_hour,
        48 * per_hour,
        72 * per_hour,
    )
    clean, _ = S.clean_reopens(raw)
    prof = S.PROFILES[profile]
    sw = prof.swap
    costs = dict(
        comm_rt=2 * prof.commission_per_side_per_lot,
        contract=prof.contract_size,
        swap_long=sw.swap_long_points,
        swap_short=sw.swap_short_points,
        t=raw.index.to_numpy(),
    )
    costs["roll"], costs["cum"] = S.rollovers(raw.index, sw.triple_weekday)
    short = S.build_side("short", clean, raw, prof.spread)
    long_ = S.build_side("long", S.mirror(clean), S.mirror(raw), prof.spread)
    return {"short": [short], "long": [long_], "both": [short, long_]}, costs


def explore(tf: int, raw: pd.DataFrame, sides: dict, costs: dict, out: Path) -> None:
    split, months = len(raw) // 2, (raw.index[-1] - raw.index[0]).days / 30.44
    rows = []
    for exit_name, rule in EXITS.items():
        RULE.clear()
        RULE.update(rule)
        cache: dict = {}
        for combo in itertools.product(*GRID.values()):
            cell = dict(entry="stab", **dict(zip(GRID, combo)))
            st = S.stats(S.simulate(sides[cell["dir"]], cell, costs, cache), split, months)
            rows.append(dict(tf=tf, exit=exit_name, **cell, **st))
    res = pd.DataFrame(rows)
    path = out / f"scalp_{tf}.csv"
    res.to_csv(path, index=False)
    ok = res[(res.n1 >= MIN_PER_HALF) & (res.n2 >= MIN_PER_HALF)]
    print(
        f"{tf}m explore {raw.index[0]:%Y-%m-%d} -> {raw.index[-1]:%Y-%m-%d}: {len(res)} cells, "
        f"{int(((ok.h1 > 0) & (ok.h2 > 0)).sum())} positive in both halves with "
        f">= {MIN_PER_HALF} trades each -> {path}"
    )


def _neighbours(r: pd.Series, axes: dict):
    for ax, vals in axes.items():
        for v in vals:
            if v != r[ax]:
                yield tuple(v if c == ax else r[c] for c in KEY)


def pick(out: Path, top: int = 12) -> None:
    files = sorted(out.glob("scalp_*.csv"))
    if not files:
        raise SystemExit(f"no explore results in {out} - run `explore --tf N` first")
    df = pd.concat([pd.read_csv(f, dtype={"target": str}) for f in files], ignore_index=True)
    tot = df.set_index(KEY)["tot"]
    axes = {"exit": list(EXITS), **{k: list(v) for k, v in GRID.items()}}
    for tf, g in df.groupby("tf"):
        ok = g[(g.n1 >= MIN_PER_HALF) & (g.n2 >= MIN_PER_HALF)]
        print(
            f"{tf:>3}m: {len(g)} cells, {len(ok)} with >= {MIN_PER_HALF} trades a half, "
            f"{int(((ok.h1 > 0) & (ok.h2 > 0)).sum())} positive in both halves"
        )
    elig = df[(df.n1 >= MIN_PER_HALF) & (df.n2 >= MIN_PER_HALF) & (df.h1 > 0) & (df.h2 > 0)]
    elig = elig.assign(worse=elig[["h1", "h2"]].min(axis=1)).sort_values("worse", ascending=False)
    print(f"\nTOP {top} BY THE WORSE HALF — plateau = most one-setting neighbours positive too")
    for _, r in elig.head(top).iterrows():
        nb = [tot.loc[k] for k in _neighbours(r, axes) if k in tot.index]
        pos = sum(x > 0 for x in nb)
        shape = "plateau" if pos * 2 > len(nb) else "spike  "
        print(
            f"{int(r.tf):>3}m {r.exit:<13} {S.label(r):<44} | n {int(r.n):>4} ({r.pm:.1f}/mo) "
            f"win {r.win:5.1f}% RR {r.rr:.2f} net {r.avg:+.3f}R total {r.tot:+6.1f}R "
            f"halves {r.h1:+.1f}/{r.h2:+.1f} t {r.t_stat:+.2f} | {shape} {pos}/{len(nb)}"
        )
    print("\nNext: `check` the plateau cells in this order; the first at z >= 2 is the pick.")


def matched_control(side_list: list, trades: list, reps: int = 20, seed: int = 7):
    """`S.control`, returning every draw so the comparison carries its own error bar. Matched on
    direction, stop distance, target distance and — the walk being RULE's — exit."""
    rng = np.random.default_rng(seed)
    by = {s.name: s for s in side_list}
    rs, hit = [], []
    for t in trades:
        b = by[t["side"]].book
        risk, reward = t["stop"] - t["entry"], t["entry"] - t["target"]
        for _ in range(reps):
            j = int(rng.integers(60, b.n - S.MAX_HOLD - 2))
            e = b.C[j] - b.en
            _, r, how = b.walk(j + 1, e, e + risk, e - reward, force=True)
            rs.append(r)
            hit.append(how == "target")
    return np.array(rs), float(np.mean(hit) * 100)


def score(tf: int, raw: pd.DataFrame, sides: dict, costs: dict, cells: list, mode: str) -> None:
    if mode == "holdout":
        print(
            "🔴 THE HOLDOUT WAS SPENT ON 2026-09-14 — read the docstring before calling this a test"
        )
        split, months = len(raw), (raw.index[-1] - HOLDOUT).days / 30.44
    else:
        split, months = len(raw) // 2, (raw.index[-1] - raw.index[0]).days / 30.44
    for spec in cells:
        RULE.clear()
        RULE.update(EXITS[spec.get("exit", "fixed")])
        cell = {k: v for k, v in spec.items() if k != "exit"}
        trades = S.simulate(sides[cell["dir"]], cell, costs, {})
        if mode == "holdout":
            trades = [t for t in trades if raw.index[t["bar"]] >= HOLDOUT]
        name = f"{tf}m {spec.get('exit', 'fixed')} {S.label(cell)}"
        if len(trades) < 2:
            print(f"\n{name}: {len(trades)} trades — nothing to score")
            continue
        st = S.stats(trades, split, months)
        g = np.array([t["r_gross"] for t in trades])
        rs, rand_win = matched_control(sides[cell["dir"]], trades)
        z = (g.mean() - rs.mean()) / np.sqrt(g.var(ddof=1) / len(g) + rs.var(ddof=1) / len(rs))
        halves = f" halves {st['h1']:+.1f}/{st['h2']:+.1f}" if mode == "check" else ""
        years = pd.Series([t["r"] for t in trades], index=raw.index[[t["bar"] for t in trades]])
        years = years.groupby(years.index.year).agg(["count", "sum"])
        print(
            f"\n{name}\n  {st['n']} trades ({st['pm']:.1f}/mo) win {st['win']:.1f}% "
            f"RR {st['rr']:.2f} net {st['avg']:+.3f}R total {st['tot']:+.1f}R{halves} "
            f"maxDD {st['dd']:.1f}R t {st['t_stat']:+.2f}"
        )
        print(
            f"  gross {g.mean():+.3f}R against matched random {rs.mean():+.3f}R "
            f"(random target hits {rand_win:.1f}%) -> edge {g.mean() - rs.mean():+.3f}R, "
            f"z {z:+.2f}: {'BEATS' if z >= Z_TO_BEAT else 'does NOT beat'} random at z >= {Z_TO_BEAT:g}"
        )
        print(
            "  by year, trades/net R: "
            + "  ".join(f"{y} {int(c)}/{s:+.1f}" for y, (c, s) in years.iterrows())
        )


def _cells(text: str) -> list:
    parsed = json.loads(text)
    cells = parsed if isinstance(parsed, list) else [parsed]
    for c in cells:
        c.setdefault("entry", "stab")
        missing, extra = CELL_KEYS - set(c), set(c) - CELL_KEYS - {"exit"}
        if missing or extra:
            raise SystemExit(f"cell {c}: missing {sorted(missing)}, unknown {sorted(extra)}")
        if c.get("exit", "fixed") not in EXITS:
            raise SystemExit(f"cell {c}: exit must be one of {list(EXITS)}")
    return cells


def main() -> None:
    ap = argparse.ArgumentParser(
        description="The Loaded Level setup as a scalp — see the docstring."
    )
    ap.add_argument("mode", choices=("explore", "pick", "check", "holdout"))
    ap.add_argument("--tf", type=int, choices=TIMEFRAMES, help="minutes; explore / check / holdout")
    ap.add_argument("--cells", help="one JSON cell or a JSON list of them; check / holdout")
    ap.add_argument("--server-dir", default="PUPrime_Demo")
    ap.add_argument("--symbol", default="XAUUSD_p")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--profile", default="puprime_ecn")
    ap.add_argument("--out", default="backtest/reports/loaded_level_scalp")
    a = ap.parse_args()
    out = Path(a.out) if Path(a.out).is_absolute() else S.ROOT / a.out
    if a.mode == "pick":
        pick(out)
        return
    if a.tf is None:
        ap.error(f"{a.mode} needs --tf")
    if a.mode != "explore" and not a.cells:
        ap.error(f"{a.mode} needs --cells")
    cells = _cells(a.cells) if a.mode != "explore" else []
    raw = load(a.tf, a)
    sides, costs = build(a.tf, raw, a.profile)
    if a.mode == "explore":
        out.mkdir(parents=True, exist_ok=True)
        explore(a.tf, raw, sides, costs, out)
    else:
        score(a.tf, raw, sides, costs, cells, a.mode)


if __name__ == "__main__":
    main()
