"""structure_patterns.py — is there ANY sequence of market-structure events on gold with a real,
tradeable edge once the number of sequences tried has been paid for?

A STUDY, not a strategy: single-position books and real costs, no Pine twin, no parity gate, so
every number it prints is a lab finding. It is built ON `loaded_level_study.py` — same reopen-spike
cleaning (detection only), same mirrored-bar longs, same bid/ask walk, same ECN costs, same scoring
and the same matched random-entry control — and imports them rather than copying them.

THE QUESTION
  The user trades by market structure and wants "the one pattern that wins the most", to look for
  it on other timeframes afterwards. Every 2- and 3-event sequence is traded long and short with a
  1R and a 2R target under ONE rule, and a winner must beat the best result the SAME search throws
  up on random entries. The protocol was fixed before any result existed: the best of 3,456 cells
  of another setup (`loaded_level_scalp.py`) looked great in-sample and lost on new data.

THE ALPHABET — 12 tokens, every one read off the canonical engines, none re-detected here
  HH LH HL LL        external swing labels, stamped on the bar the structure engine CLASSIFIES the
                     swing (its break bar) — never the swing's own bar. "ASH"/"ASL" means "not yet
                     classified" and is not a token.
  BOS_up BOS_dn      external break that continues the trend
  CHoCH_up CHoCH_dn  external break that flips the trend (the engine's "SOS"). The engine raises its
                     BOS flag on that bar too; a flip is a CHoCH token and never ALSO a BOS token.
  iBRK_up iBRK_dn    any internal break, internal BOS and internal CHoCH merged per direction
  SWEEP_H SWEEP_L    a named liquidity level taken — session / previous day / H4 / previous week —
                     by the liquidity engine's own rules (a wick; weekly levels need a close)
  SAME BAR: swing labels, then the external break, then internal breaks (up before down), then
  sweeps (high before low). Two swing labels on one bar go in the order the swings themselves
  formed (older first; a tie, high first). A token type appears at most once per bar, so three
  named highs taken by one candle are ONE sweep token.
  ⚠ Stamped at the close of the bar the engine emits it, on bars with reopen spikes clipped
  (`clean_reopens`); nothing reads a later bar. `explore` re-runs the top strategies with the
  same-bar order REVERSED only to measure how much a result leans on that order — reported, never
  searched.

PATTERNS: the last 2 or the last 3 tokens of the stream, read at the bar the last one is stamped.
  Every window position is an occurrence. Each pattern is 4 strategies (long / short x 1R / 2R),
  each its own single-position book: a signal while its own trade is open is skipped.

THE TRADE RULE — one rule, no per-pattern tuning
  ENTRY   market at the OPEN of the bar after the signal bar; a long pays the spread (bars are bid).
  STOP    long: the structure engine's last CONFIRMED swing low (the latest HL/LL) as of the signal
          bar's close, minus 0.25 x ATR(50); short: its last confirmed swing high plus 0.25 x ATR.
          ATR(50) is Wilder's, on the cleaned bars, at the signal bar.
  SKIP    a stop closer than 1 x ATR or further than 8 x ATR from the fill (or on the wrong side).
          Swap in R scales with 1/stop, so R on a tiny stop measures the stop, not the pattern.
  TARGET  1R or 2R from the fill. TIME EXIT 48 hours of bars (576 on 5m), then out at market.
  WALK    the study's own: stop before target on the same bar, a gap through the stop fills at the
          open, a gap through the target fills better. Fills on RAW bars, never the cleaned ones.
  COSTS   `puprime_ecn`: spread 0.12, $1/side/lot, measured swap with a triple Wednesday, charged
          term for term as the study's `simulate` charges them. `explore` PROVES that on real trades
          by pushing them through `simulate` itself and printing both net R figures.

DATA WINDOWS — hard rules, and `explore` refuses a gold window that breaks them
  EXPLORE  2020-01-01 -> 2025-08-31 inclusive. Every selection decision is made on these bars only.
  🔴 TEST  2018-09-14 -> 2019-12-31 is UNTOUCHED. It is run ONCE, only on strategies that pass all
           three gates, with `test` — which this tool's author never ran. Every extra look turns
           those months into in-sample data. No gold bar before 2020-01-01 is loaded by `explore`.
  SPENT    2025-09-01 onward was used by another test and is never loaded.

GATES — fixed, applied in this order
  1 SAMPLE  >= 25 trades in EACH half of explore (split at the bar-count midpoint, as `stats`
            splits) and net R positive in BOTH halves.
  2 LUCK    the WHOLE search is re-run with every real trade's entry moved to a uniformly random bar
            of explore — same direction, same stop distance IN ATR, same target in R, same walk and
            costs — and the best t (net R per trade) of any strategy meeting gate 1 is recorded.
            200 runs (never fewer than 100). A strategy must beat the 95th percentile of those.
            ⚠ Exact shortcut: a null run keeps each strategy's trade count, so one with fewer than
            50 real trades can never meet gate 1 there and is not re-drawn.
            ⚠ Each trade is re-drawn independently, which breaks the overlap between strategies
            that share signals. That makes the bar STRICTER than a perfectly correlated null would.
  3 ENTRY   its entries beat the study-style matched random-entry control — same direction, same
            stop and target distance in price, entered at a random bar's close — on GROSS R,
            20 draws per trade, at z >= 2.

Usage (from the repo root, with command-center/backend/.venv/bin/python):
  python backtest/tools/structure_patterns.py explore                  # 5m, everything reported
  python backtest/tools/structure_patterns.py explore --null-runs 100  # only if runtime forces it
  python backtest/tools/structure_patterns.py test --strategies 'HH>BOS_up|long|2R' \\
      --server-dir <folder holding 2018-19 bars> --spend-test-set      # ONCE, gate survivors only
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loaded_level_study as S  # noqa: E402

EXPLORE = ("2020-01-01", "2025-09-01")  # [start, end)
TEST_SET = ("2018-09-14", "2020-01-01")  # [start, end) — untouched; `test` only
TIMEFRAMES = (5, 15, 60)
HOLD_HOURS = 48
BUFFER_ATR = 0.25
STOP_ATR = (1.0, 8.0)
TARGETS_R = (1, 2)
LENGTHS = (2, 3)
DIRS = ("long", "short")
MIN_PER_HALF = 25
NULL_RUNS, MIN_NULL_RUNS, NULL_Q = 200, 100, 0.95
CONTROL_REPS, Z_TO_BEAT = 20, 2.0
SEED = 20260914
TOP = 20

TOKENS = (
    "HH", "LH", "HL", "LL", "BOS_up", "BOS_dn", "CHoCH_up", "CHoCH_dn",
    "iBRK_up", "iBRK_dn", "SWEEP_H", "SWEEP_L",
)  # fmt: skip
TOK = {name: k for k, name in enumerate(TOKENS)}
# Same-bar rank of each category: swing label, external break, internal break, sweep.
ORDERS = {"canonical": (0, 1, 2, 3), "reversed": (3, 2, 1, 0)}
OUTCOME = ("stop", "target", "time")


# ─────────────────────────────── bars ───────────────────────────────


def load(server_dir: str, symbol: str, tf: int, start: str, end: str) -> pd.DataFrame:
    """Cached bars in [start, end). 5m and 15m read their own file; 1h is resampled UP from 15m
    (label and closed left). Rows outside the window are dropped at read, before anything sees them."""
    base = "M5" if tf == 5 else "M15"
    path = S.ROOT / "backtest" / "cache" / server_dir / f"{symbol}__{base}.csv"
    if not path.exists():
        sys.exit(f"no cached bars at {path}")
    df = pd.read_csv(path, parse_dates=["time"]).set_index("time")
    df = df[(df.index >= start) & (df.index < end)][["open", "high", "low", "close"]].astype(float)
    if tf == 60:
        agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
        df = df.resample("60min", label="left", closed="left").agg(agg).dropna()
    if df.empty:
        sys.exit(f"{path} holds no bars in [{start}, {end})")
    return df


def guard_explore(symbol: str, start: str, end: str) -> None:
    """The gold windows are hard rules: nothing before 2020, nothing from 2025-09-01."""
    if not symbol.upper().startswith("XAUUSD"):
        return
    if pd.Timestamp(start) < pd.Timestamp(EXPLORE[0]) or pd.Timestamp(end) > pd.Timestamp(
        EXPLORE[1]
    ):
        sys.exit(
            f"refused: explore on gold must stay inside [{EXPLORE[0]}, {EXPLORE[1]}). Before it is "
            f"the untouched test set; from {EXPLORE[1]} the months were spent on another test."
        )


# ─────────────────────────────── tokens ───────────────────────────────


def tokenize(clean: pd.DataFrame):
    """Run the canonical structure + liquidity engines once over the cleaned bars.

    Returns token rows (bar, category, same-bar order, token) and, per bar, the engine's last
    confirmed swing low / high as they stand at that bar's close (NaN before the first one)."""
    cfg = S.EngineConfig(
        fib=False, sniper=False, macro=False, internal=False, fvg=False,
        rsi=False, sessions=False, liquidity=True,
    )  # fmt: skip
    stack = S.EngineStack(cfg)
    n = len(clean)
    lo_ref, hi_ref = np.full(n, np.nan), np.full(n, np.nan)
    rows = []
    for bar in S.iter_bars(clean):
        st = stack.step(bar)
        i = bar.index
        x, it = st.structure.external, st.structure.internal
        swings = []
        if x.broken_high_label in ("HH", "LH"):
            swings.append((x.broken_high_index, 0, TOK[x.broken_high_label]))
        if x.broken_low_label in ("HL", "LL"):
            swings.append((x.broken_low_index, 1, TOK[x.broken_low_label]))
        for w, (_, _, tk) in enumerate(sorted(swings)):
            rows.append((i, 0, w, tk))
        if x.bull_bos:
            rows.append((i, 1, 0, TOK["CHoCH_up" if x.bull_sos else "BOS_up"]))
        if x.bear_bos:
            rows.append((i, 1, 1, TOK["CHoCH_dn" if x.bear_sos else "BOS_dn"]))
        if it.bull_bos or it.bull_sos:
            rows.append((i, 2, 0, TOK["iBRK_up"]))
        if it.bear_bos or it.bear_sos:
            rows.append((i, 2, 1, TOK["iBRK_dn"]))
        taken = {lv.side for lv in st.liquidity.mitigated}
        if "high" in taken:
            rows.append((i, 3, 0, TOK["SWEEP_H"]))
        if "low" in taken:
            rows.append((i, 3, 1, TOK["SWEEP_L"]))
        lc, hc = stack.structure.last_confirmed_low, stack.structure.last_confirmed_high
        if lc is not None:
            lo_ref[i] = lc.price
        if hc is not None:
            hi_ref[i] = hc.price
    return np.array(rows, dtype=np.int64).reshape(-1, 4), lo_ref, hi_ref


def stream(rows: np.ndarray, order: str):
    """The token stream: by bar, then the same-bar category rank, then the within-category order."""
    rank = np.array(ORDERS[order])[rows[:, 1]]
    o = np.lexsort((rows[:, 2], rank, rows[:, 0]))
    return rows[o, 3], rows[o, 0]


def occurrences(tok: np.ndarray, tbar: np.ndarray) -> dict:
    """pattern (token-id tuple) -> rows of (signal bar, bar of its FIRST token), in time order."""
    occ: dict = {}
    t, b = tok.tolist(), tbar.tolist()
    for length in LENGTHS:
        for p in range(length - 1, len(t)):
            key = tuple(t[p - length + 1 : p + 1])
            occ.setdefault(key, []).append((b[p], b[p - length + 1]))
    return {k: np.array(v, dtype=np.int64) for k, v in occ.items()}


def pname(key: tuple) -> str:
    return ">".join(TOKENS[t] for t in key)


def sname(key: tuple) -> str:
    pat, side, m = key
    return f"{pname(pat)}|{side}|{m}R"


def parse_sname(text: str) -> tuple:
    try:
        pat, side, tgt = text.split("|")
        key = tuple(TOK[t] for t in pat.split(">"))
        m = int(tgt.rstrip("R"))
    except (ValueError, KeyError):
        sys.exit(f"cannot read strategy {text!r}: want e.g. 'HH>BOS_up|long|2R'")
    if len(key) not in LENGTHS or side not in DIRS or m not in TARGETS_R:
        sys.exit(f"strategy {text!r} is outside the searched space")
    return key, side, m


# ─────────────────────────────── the walk, many at once ───────────────────────────────


def _sparse(x: np.ndarray, op, pad: float, levels: int) -> list:
    """table[p][j] = op over x[j : j + 2**p]; padded where the block runs off the end."""
    out = [np.asarray(x, dtype=float)]
    for p in range(1, levels):
        h, prev = 1 << (p - 1), out[-1]
        cur = np.full(len(prev), pad)
        if len(prev) > h:
            cur[:-h] = op(prev[:-h], prev[h:])
        out.append(cur)
    return out


class FastWalk:
    """The study's `Book.walk(force=True)` for MANY trades at once — what makes 200 null searches
    affordable. First passage is found by jumping over power-of-two blocks whose max (min) is still
    short of the level, so it reads the same bars with the same `>=` / `<=` the study reads.
    🔴 NOT TRUSTED ON ARGUMENT: `walk_signals` runs every real trade through BOTH walks and raises
    on any difference in exit bar, outcome or R. A null measured on a different walk is no null."""

    def __init__(self, book, hold: int) -> None:
        self.b, self.hold = book, hold
        self.levels = (hold + 1).bit_length()  # 2**levels - 1 >= the longest window
        self.hmax = _sparse(book.H, np.maximum, np.inf, self.levels)
        self.lmin = _sparse(book.L, np.minimum, -np.inf, self.levels)

    def _first(self, table: list, k, end, level, rising: bool):
        pos = k.copy()
        for p in range(self.levels - 1, -1, -1):
            step = 1 << p
            can = pos + (step - 1) <= end
            v = table[p][np.where(can, pos, 0)]
            clear = (v < level) if rising else (v > level)
            pos += np.where(can & clear, step, 0)
        return pos  # end + 1 = never reached

    def walk(self, k, entry, stop, target):
        b = self.b
        end = np.minimum(k + self.hold, b.n - 1)
        js = self._first(self.hmax, k, end, stop - b.ex, True)
        jt = self._first(self.lmin, k, end, target - b.ex, False)
        hit_s, hit_t = js <= end, jt <= end
        is_stop = hit_s & (~hit_t | (js <= jt))
        is_tgt = ~is_stop & hit_t
        o_s = b.O[np.where(hit_s, js, 0)] + b.ex
        px = np.where(
            is_stop,
            np.where(o_s > stop, o_s, stop),
            np.where(
                is_tgt, np.minimum(target, b.O[np.where(hit_t, jt, 0)] + b.ex), b.C[end] + b.ex
            ),
        )
        r = (entry - px) / (stop - entry)
        xbar = np.where(is_stop, js, np.where(is_tgt, jt, end))
        return xbar, r, np.where(is_stop, 0, np.where(is_tgt, 1, 2)).astype(np.int8)


def net_r(costs: dict, side: str, ebar, xbar, risk, r_gross):
    """`simulate`'s cost arithmetic term for term: nights between the entry and exit bars' opens
    (x3 on the triple day), swap in points per lot, a round-turn commission per lot."""
    t, roll, cum = costs["t"], costs["roll"], costs["cum"]
    nights = (
        cum[np.searchsorted(roll, t[xbar], "right")] - cum[np.searchsorted(roll, t[ebar], "right")]
    )
    pts = costs["swap_short"] if side == "short" else costs["swap_long"]
    swap_r = nights * pts * S.POINT / risk
    comm_r = costs["comm_rt"] / (risk * costs["contract"])
    return r_gross - comm_r + swap_r, swap_r, nights


# ─────────────────────────────── market ───────────────────────────────


@dataclass
class Market:
    tf: int
    raw: pd.DataFrame
    atr: np.ndarray
    rows: np.ndarray
    lo_ref: np.ndarray
    hi_ref: np.ndarray
    hold: int
    books: dict
    fast: dict
    costs: dict
    split: int
    months: float
    clipped: int


def use(mkt: Market) -> None:
    """The study's walk and control read the time exit from a module global. Every path that
    reaches them sets it first, so a 1h market can never walk with a 5m hold."""
    S.MAX_HOLD = mkt.hold


def build_market(raw: pd.DataFrame, tf: int, profile: str) -> Market:
    t0 = time.time()
    clean, fixed = S.clean_reopens(raw)
    prof = S.PROFILES[profile]
    sw = prof.swap
    spread = prof.spread_or_refuse()
    costs = dict(
        comm_rt=2 * prof.commission_per_side_per_lot, contract=prof.contract_size,
        swap_long=sw.swap_long_points, swap_short=sw.swap_short_points, t=raw.index.to_numpy(),
    )  # fmt: skip
    costs["roll"], costs["cum"] = S.rollovers(raw.index, sw.triple_weekday)
    atr = S.wilder_atr(*(clean[k].to_numpy() for k in ("high", "low", "close")))
    rows, lo_ref, hi_ref = tokenize(clean)
    books = {"short": S.Book(raw, "short", spread), "long": S.Book(S.mirror(raw), "long", spread)}
    hold = HOLD_HOURS * 60 // tf
    mkt = Market(
        tf=tf, raw=raw, atr=atr, rows=rows, lo_ref=lo_ref, hi_ref=hi_ref, hold=hold, books=books,
        fast={k: FastWalk(b, hold) for k, b in books.items()}, costs=costs, split=len(raw) // 2,
        months=(raw.index[-1] - raw.index[0]).days / 30.44, clipped=len(fixed),
    )  # fmt: skip
    print(
        f"{tf}m: {len(raw):,} bars {raw.index[0]:%Y-%m-%d %H:%M} -> {raw.index[-1]:%Y-%m-%d %H:%M}"
        f", {len(rows):,} tokens, {len(fixed)} reopen spikes clipped for detection, time exit "
        f"{hold} bars ({time.time() - t0:.0f}s)"
    )
    return mkt


# ─────────────────────────────── trades ───────────────────────────────


def walk_signals(mkt: Market, bars) -> tuple:
    """One trade per signal bar per (side, target), walked by the STUDY's own `Book.walk` — the
    ground truth — and again by `FastWalk`, which must agree exactly or this raises.

    A leg holds compact arrays over its valid signals plus `pos`: bar -> row (-1 = no trade)."""
    use(mkt)
    n = len(mkt.raw)
    bars = np.unique(np.asarray(bars, dtype=np.int64))
    bars = bars[bars + 1 < n]
    legs, checked, worst = {}, 0, 0.0
    for side in DIRS:
        b = mkt.books[side]
        ref = mkt.hi_ref if side == "short" else -mkt.lo_ref
        a, k = mkt.atr[bars], bars + 1
        entry = b.O[k] - b.en
        stop = ref[bars] + BUFFER_ATR * a
        risk = stop - entry
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = risk / a
        ok = np.isfinite(ratio) & (ratio >= STOP_ATR[0]) & (ratio <= STOP_ATR[1])
        sig, kk, en, sp, rk, ra = (v[ok] for v in (bars, k, entry, stop, risk, ratio))
        for m in TARGETS_R:
            tg = en - m * rk
            xbar, rg = np.empty(len(sig), np.int64), np.empty(len(sig))
            how = np.empty(len(sig), np.int8)
            for q in range(len(sig)):
                x, r, o = b.walk(int(kk[q]), float(en[q]), float(sp[q]), float(tg[q]), force=True)
                xbar[q], rg[q], how[q] = x, r, OUTCOME.index(o)
            fx, fr, fo = mkt.fast[side].walk(kk, en, sp, tg)
            bad = int(np.sum(fx != xbar) + np.sum(fo != how))
            dr = float(np.max(np.abs(fr - rg), initial=0.0))
            if bad or dr > 1e-12:
                raise RuntimeError(
                    f"the fast walk disagrees with the study's on {side} {m}R: {bad} exits "
                    f"differ, max |dR| {dr} — the luck bar would measure a different walk"
                )
            worst, checked = max(worst, dr), checked + len(sig)
            r, swap, nights = net_r(mkt.costs, side, kk, xbar, rk, rg)
            pos = np.full(n, -1, np.int64)
            pos[sig] = np.arange(len(sig))
            legs[(side, m)] = dict(
                side=side, m=m, pos=pos, sig=sig, k=kk, entry=en, stop=sp, target=tg, risk=rk,
                ratio=ra, xbar=xbar, r_gross=rg, out=how, r=r, swap_r=swap, nights=nights,
            )  # fmt: skip
    return legs, checked, worst


def search(occ: dict, legs: dict, pats=None) -> dict:
    """Every strategy is its own single-position book: a signal is taken only when its entry bar
    comes after the exit bar of that strategy's previous trade. -> strategy -> rows in its leg."""
    res = {}
    use_occ = occ if pats is None else {p: occ[p] for p in pats if p in occ}
    for (side, m), leg in legs.items():
        pos, kl, xl = leg["pos"], leg["k"].tolist(), leg["xbar"].tolist()
        for pat, arr in use_occ.items():
            q = pos[arr[:, 0]]
            free, keep = -1, []
            for j in q[q >= 0].tolist():
                if kl[j] > free:
                    keep.append(j)
                    free = xl[j]
            res[(pat, side, m)] = np.array(keep, dtype=np.int64)
    return res


def trade_dicts(leg: dict, q) -> list:
    """Rows of a leg in the study's trade shape, so `stats` and `control` read them unchanged."""
    return [
        dict(
            side=leg["side"],
            sig=int(leg["sig"][j]),
            bar=int(leg["k"][j]),
            xbar=int(leg["xbar"][j]),
            entry=float(leg["entry"][j]),
            stop=float(leg["stop"][j]),
            target=float(leg["target"][j]),
            rr=float(leg["m"]),
            r_gross=float(leg["r_gross"][j]),
            r=float(leg["r"][j]),
            swap_r=float(leg["swap_r"][j]),
            outcome=OUTCOME[leg["out"][j]],
            risk_atr=float(leg["ratio"][j]),
        )  # fmt: skip
        for j in q
    ]


def score(mkt: Market, legs: dict, key: tuple, q) -> tuple:
    pat, side, m = key
    tr = trade_dicts(legs[(side, m)], q)
    st = S.stats(tr, mkt.split, mkt.months)
    r = np.array([t["r"] for t in tr])
    win, loss = r[r > 0], r[r < 0]
    payoff = float(win.mean() / -loss.mean()) if len(win) and len(loss) else math.nan
    row = dict(strategy=sname(key), pattern=pname(pat), length=len(pat), dir=side, target=f"{m}R")
    row.update(st, payoff=payoff)
    row["sample_ok"] = st["n1"] >= MIN_PER_HALF and st["n2"] >= MIN_PER_HALF
    row["gate1"] = row["sample_ok"] and st["h1"] > 0 and st["h2"] > 0
    return row, tr


# ─────────────────────────────── gate 2: the luck bar ───────────────────────────────


def luck_bar(mkt: Market, legs: dict, res: dict, runs: int, seed: int) -> dict:
    """The whole search again on random entries: every real trade keeps its direction, its stop
    distance IN ATR and its target in R, and moves to a uniformly random bar. Records the best t of
    any strategy that meets gate 1 in each run."""
    groups = [(key, q) for key, q in res.items() if len(q) >= 2 * MIN_PER_HALF]
    if not groups:  # nothing can meet gate 1 in any run: every run's best is "none"
        return dict(
            best=np.full(runs, -np.inf), npass=np.zeros(runs, np.int64), strategies=0, trades=0
        )
    sid, is_long, ratio, mult = [], [], [], []
    for g, ((_, side, m), q) in enumerate(groups):
        sid.append(np.full(len(q), g))
        is_long.append(np.full(len(q), side == "long"))
        ratio.append(legs[(side, m)]["ratio"][q])
        mult.append(np.full(len(q), float(m)))
    sid, is_long = np.concatenate(sid), np.concatenate(is_long)
    ratio, mult = np.concatenate(ratio), np.concatenate(mult)
    ns, total = len(groups), len(sid)
    rng = np.random.default_rng(seed)
    lo, hi = 61, len(mkt.raw) - mkt.hold - 1  # entry bar; the control's close bar is one before
    best, npass = np.full(runs, -np.inf), np.zeros(runs, np.int64)
    net = np.empty(total)
    t0 = time.time()
    for run in range(runs):
        k = rng.integers(lo, hi, size=total)
        for side, sel in (("short", ~is_long), ("long", is_long)):
            b, kk = mkt.books[side], k[sel]
            e = b.O[kk] - b.en
            stop = e + ratio[sel] * mkt.atr[kk - 1]
            risk = stop - e
            xb, rg, _ = mkt.fast[side].walk(kk, e, stop, e - mult[sel] * risk)
            net[sel] = net_r(mkt.costs, side, kk, xb, risk, rg)[0]
        first = k < mkt.split
        cnt = np.bincount(sid, minlength=ns)
        n1 = np.bincount(sid[first], minlength=ns)
        h1 = np.bincount(sid[first], weights=net[first], minlength=ns)
        h2 = np.bincount(sid[~first], weights=net[~first], minlength=ns)
        mean = np.bincount(sid, weights=net, minlength=ns) / cnt
        sd = np.sqrt(np.bincount(sid, weights=(net - mean[sid]) ** 2, minlength=ns) / (cnt - 1))
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(sd > 0, mean / (sd / np.sqrt(cnt)), 0.0)
        ok = (n1 >= MIN_PER_HALF) & (cnt - n1 >= MIN_PER_HALF) & (h1 > 0) & (h2 > 0)
        npass[run] = int(ok.sum())
        if ok.any():
            best[run] = float(t[ok].max())
        if (run + 1) % 25 == 0:
            print(f"  null run {run + 1}/{runs}  ({time.time() - t0:.0f}s)")
    return dict(best=best, npass=npass, strategies=ns, trades=total)


# ─────────────────────────────── gate 3 + the proofs ───────────────────────────────


def matched_control(mkt: Market, trades: list, reps: int = CONTROL_REPS, seed: int = 7) -> tuple:
    """`S.control`'s draws — same seed, same draw range, same entry at a random bar's close walked
    from the next bar — returned whole so the comparison carries its own error bar, as
    `loaded_level_scalp.py` does. Matched on direction, stop and target distance in price; GROSS R."""
    use(mkt)
    rng = np.random.default_rng(seed)
    rs = []
    for t in trades:
        b = mkt.books[t["side"]]
        risk, reward = t["stop"] - t["entry"], t["entry"] - t["target"]
        for _ in range(reps):
            j = int(rng.integers(60, b.n - S.MAX_HOLD - 2))
            e = b.C[j] - b.en
            rs.append(b.walk(j + 1, e, e + risk, e - reward, force=True)[1])
    rs = np.array(rs)
    g = np.array([t["r_gross"] for t in trades])
    z = (g.mean() - rs.mean()) / math.sqrt(g.var(ddof=1) / len(g) + rs.var(ddof=1) / len(rs))
    return float(z), float(g.mean()), float(rs.mean())


def prove_costs(mkt: Market, legs: dict) -> list:
    """Push real trades through the STUDY's own `simulate` and compare its net R with this tool's.
    Each trade becomes a one-candidate side whose resting order sits at this trade's fill, with the
    stop and target this trade uses (ATR 1.0 keeps the study's stop buffer exact in binary). Picked:
    per leg, the first trade holding no swap night and the first holding three or more, whose walk
    cannot differ (the study's resting fill cannot book a target on its own fill bar)."""
    use(mkt)
    cell = dict(
        target="4", floor=0.0, entry="stab", min_risk=0.0, min_range=0.0, touches=1,
        need_sos=False,
    )  # fmt: skip
    rows = []
    for leg in legs.values():
        for want in (lambda nt: nt == 0, lambda nt: nt >= 3):
            cand = [
                j
                for j in range(len(leg["sig"]))
                if want(leg["nights"][j]) and leg["xbar"][j] > leg["k"][j]
            ]
            if not cand:
                continue
            j = cand[0]
            c = dict(
                bar=np.array([leg["k"][j]]), entry=np.array([leg["entry"][j]]),
                setup=np.array([0]), atr=np.array([1.0]), induced=np.array([True]),
                touches=np.array([1]), sos=np.array([False]), low4=np.array([leg["target"][j]]),
                pool=np.array([np.nan]), named=np.array([np.nan]),
            )  # fmt: skip
            side = S.Side(
                leg["side"], [], c, mkt.books[leg["side"]],
                top=np.array([leg["stop"][j] - S.BUFFER * 1.0]), range_atr=np.array([0.0]),
            )  # fmt: skip
            got = S.simulate([side], cell, mkt.costs, {})
            if (
                len(got) != 1
                or got[0]["xbar"] != leg["xbar"][j]
                or got[0]["stop"] != leg["stop"][j]
            ):
                raise RuntimeError(
                    f"the study's simulate did not replay trade {j} as the same trade"
                )
            rows.append(
                dict(
                    side=leg["side"],
                    target=f"{leg['m']}R",
                    entry_time=mkt.raw.index[leg["k"][j]],
                    exit_time=mkt.raw.index[leg["xbar"][j]],
                    outcome=OUTCOME[leg["out"][j]],
                    nights=int(leg["nights"][j]),
                    r_gross=float(leg["r_gross"][j]),
                    r_here=float(leg["r"][j]),
                    r_study=float(got[0]["r"]),
                    diff=abs(float(leg["r"][j]) - float(got[0]["r"])),
                )  # fmt: skip
            )
    return rows


def concentration(mkt: Market, tr: list, occ_arr: np.ndarray, bar_sets: dict, pat: set) -> dict:
    """What could make a good-looking strategy one event counted many times."""
    idx = mkt.raw.index
    months = pd.Series([t["r"] for t in tr], index=idx[[t["bar"] for t in tr]].to_period("M"))
    by_month = months.groupby(level=0).agg(["count", "sum"])
    sig = np.array([t["sig"] for t in tr])
    first = occ_arr[np.searchsorted(occ_arr[:, 0], sig), 1]
    tot = float(months.sum())
    shared = np.array([bool(bar_sets[s] - pat) for s in sig], dtype=bool)
    return dict(
        one_bar=float(np.mean(first == sig)) * 100,
        top_month_trades=float(by_month["count"].max() / len(tr)) * 100,
        top_month_r=float(by_month["sum"].max() / tot) * 100 if tot > 0 else math.nan,
        top_month=str(by_month["sum"].idxmax()),
        # The signal bar also printed a token type outside the pattern, so the same-bar order
        # decided whether this pattern formed at all.
        shared=float(np.mean(shared)) * 100,
        shared_r=float(np.sum(np.array([t["r"] for t in tr])[shared])),
    )


# ─────────────────────────────── report ───────────────────────────────

HEAD = (
    f"{'#':>2} {'strategy':<36} {'n':>4} {'/mo':>4} {'win%':>5} {'RR':>4} {'net/tr':>7} "
    f"{'total':>7} {'1st½':>6} {'2nd½':>6} {'maxDD':>6} {'t':>5}  G1 G2 G3   z"
)


def fmt(i, r: dict) -> str:
    def yn(v):
        return "Y " if v else ("- " if v is not None else "? ")

    z = r.get("z")
    return (
        f"{i:>2} {r['strategy']:<36} {r['n']:>4} {r['pm']:>4.1f} {r['win']:>5.1f} "
        f"{r['payoff']:>4.2f} {r['avg']:>+7.3f} {r['tot']:>+7.1f} {r['h1']:>+6.1f} {r['h2']:>+6.1f} "
        f"{r['dd']:>6.1f} {r['t_stat']:>+5.2f}  {yn(r['gate1'])} {yn(r.get('beats_luck'))} "
        f"{yn(r.get('gate3'))} {'' if z is None else f'{z:+.2f}'}"
    )


def write_csv(path: Path, rows: list) -> None:
    if not rows:
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))  # later rows may carry more columns
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(rows)


def export_trade(raw: pd.DataFrame, strategy: str, t: dict) -> dict:
    """A trade in REAL prices: a long is walked on mirrored bars, so its prices come back negated."""
    sign = -1.0 if t["side"] == "long" else 1.0
    return dict(
        strategy=strategy, side=t["side"], entry_time=raw.index[t["bar"]],
        exit_time=raw.index[t["xbar"]], entry=sign * t["entry"], stop=sign * t["stop"],
        target=sign * t["target"], outcome=t["outcome"], r_gross=t["r_gross"],
        swap_r=t["swap_r"], r=t["r"], risk_atr=t["risk_atr"],
    )  # fmt: skip


def by_year(mkt: Market, tr: list) -> str:
    s = pd.Series([t["r"] for t in tr], index=mkt.raw.index[[t["bar"] for t in tr]].year)
    g = s.groupby(level=0).agg(["count", "sum"])
    return "  ".join(f"{y} {int(c)}/{v:+.1f}" for y, (c, v) in g.iterrows())


def other_timeframes(a, keys: list) -> list:
    """The top strategies on the other timeframes, same explore window, nothing re-tuned — the
    time exit stays 48 hours, so the bar count rescales. Reported, never a gate."""
    out = []
    pats = {k[0] for k in keys}
    for tf in TIMEFRAMES:
        if tf == a.tf:
            continue
        mkt = build_market(load(a.server_dir, a.symbol, tf, a.start, a.end), tf, a.profile)
        occ = occurrences(*stream(mkt.rows, "canonical"))
        bars = [occ[p][:, 0] for p in pats if p in occ]
        legs, checked, _ = walk_signals(mkt, np.concatenate(bars) if bars else [])
        res = search(occ, legs, pats)
        print(f"  {tf}m: fast walk matched the study's on {checked:,} signal walks")
        for key in keys:
            row, _ = score(mkt, legs, key, res.get(key, np.array([], dtype=np.int64)))
            out.append(dict(tf=f"{tf}m", **row))
    return out


def explore(a) -> None:
    guard_explore(a.symbol, a.start, a.end)
    if a.null_runs < MIN_NULL_RUNS:
        sys.exit(f"refused: the luck bar needs at least {MIN_NULL_RUNS} null runs")
    out = Path(a.out) if Path(a.out).is_absolute() else S.ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    tag, t_all = f"{a.tf}m", time.time()
    prof = S.PROFILES[a.profile]
    print(
        f"profile {a.profile}: spread {prof.spread_or_refuse()}, commission "
        f"{prof.commission_per_side_per_lot}/side/lot, swap {prof.swap.swap_long_points}/"
        f"{prof.swap.swap_short_points} pts long/short, triple weekday {prof.swap.triple_weekday}"
        f"; window [{a.start}, {a.end}); seed {a.seed}"
    )
    mkt = build_market(load(a.server_dir, a.symbol, a.tf, a.start, a.end), a.tf, a.profile)
    raw = mkt.raw
    print(f"halves split at bar {mkt.split:,} = {raw.index[mkt.split]:%Y-%m-%d %H:%M}")

    tok, tbar = stream(mkt.rows, "canonical")
    occ = occurrences(tok, tbar)
    legs, checked, worst = walk_signals(mkt, tbar)
    print(
        f"\nCHECK 1 — the fast walk the luck bar uses matched the study's own walk on all "
        f"{checked:,} real signal walks: exit bar, outcome and gross R (max |dR| {worst:.1e})"
    )
    proof = prove_costs(mkt, legs)
    print(
        "CHECK 2 — real trades pushed through the study's own simulate: net R here vs there\n"
        f"  {'side':<5} {'tgt':<3} {'entry (UTC)':<16} {'exit (UTC)':<16} {'out':<6} "
        f"{'nights':>6} {'gross R':>8} {'net here':>9} {'net study':>9} {'|diff|':>8}"
    )
    for p in proof:
        print(
            f"  {p['side']:<5} {p['target']:<3} {p['entry_time']:%Y-%m-%d %H:%M} "
            f"{p['exit_time']:%Y-%m-%d %H:%M} {p['outcome']:<6} {p['nights']:>6} "
            f"{p['r_gross']:>+8.4f} {p['r_here']:>+9.4f} {p['r_study']:>+9.4f} {p['diff']:>8.1e}"
        )
    write_csv(out / f"cost_proof_{tag}.csv", proof)

    counts = np.bincount(tok, minlength=len(TOKENS))
    per_bar = np.bincount(tbar)
    print(
        f"\nTOKENS over explore ({tag}): {len(tok):,} on {int((per_bar > 0).sum()):,} bars, at most "
        f"{int(per_bar.max())} on one bar\n  "
        + "  ".join(f"{TOKENS[k]} {counts[k]:,}" for k in range(len(TOKENS)))
    )
    write_csv(
        out / f"tokens_{tag}.csv",
        [dict(time=raw.index[b], bar=int(b), token=TOKENS[t]) for t, b in zip(tok, tbar)],
    )

    t0 = time.time()
    res = search(occ, legs)
    rows, key_of = [], {}
    for key, q in res.items():
        row, _ = score(mkt, legs, key, q)
        rows.append(row)
        key_of[row["strategy"]] = key
    n2 = sum(len(p) == 2 for p in occ)
    n3 = len(occ) - n2
    n_sample = sum(r["sample_ok"] for r in rows)
    n_g1 = sum(r["gate1"] for r in rows)
    # Tokens printed together make different patterns trade the SAME list: count the distinct ones.
    sig_of = {
        sname(key): (key[1], key[2], tuple(legs[key[1:]]["k"][q].tolist()))
        for key, q in res.items()
    }
    distinct = len(set(sig_of.values()))
    distinct_s = len({sig_of[r["strategy"]] for r in rows if r["sample_ok"]})
    print(
        f"\nPATTERNS seen: {n2} of 144 two-token, {n3} of 1,728 three-token -> {len(rows):,} "
        f"strategies ({time.time() - t0:.0f}s)\n  {n_sample:,} have >= {MIN_PER_HALF} trades in "
        f"each half; {n_g1:,} also positive in both halves = GATE 1\n  distinct trade lists: "
        f"{distinct:,} of {len(rows):,} strategies; {distinct_s:,} of the {n_sample:,} with the sample"
    )

    print(f"\nLUCK BAR — {a.null_runs} random-entry re-runs of the whole search (seed {a.seed})")
    luck = luck_bar(mkt, legs, res, a.null_runs, a.seed)
    best = luck["best"]
    with np.errstate(invalid="ignore"):  # a run where nothing met gate 1 records -inf
        q95, med = float(np.quantile(best, NULL_Q)), float(np.median(best))
    if math.isnan(q95):  # the 95th percentile landed between two "nothing" runs
        q95 = -math.inf
    print(
        f"  re-drawn: {luck['strategies']:,} strategies with >= {2 * MIN_PER_HALF} trades, "
        f"{luck['trades']:,} trades a run; runs with no strategy through gate 1: "
        f"{int((luck['npass'] == 0).sum())}; strategies through gate 1 per run: median "
        f"{int(np.median(luck['npass']))}\n  best t per run: median {med:+.2f}, 95th percentile "
        f"{q95:+.2f}, max {best.max():+.2f}  ->  THE BAR: t > {q95:.2f}"
    )
    real_best = max((r["t_stat"] for r in rows if r["gate1"]), default=-math.inf)
    print(
        f"  the real search's best gate-1 t {real_best:+.2f} is matched or beaten by the best of "
        f"{np.mean(best >= real_best) * 100:.1f}% of the random runs"
    )
    write_csv(
        out / f"null_{tag}.csv",
        [
            dict(run=i, best_t=float(b), n_gate1=int(n))
            for i, (b, n) in enumerate(zip(best, luck["npass"]))
        ],
    )
    for r in rows:
        r["beats_luck"] = r["t_stat"] > q95

    ranked = sorted((r for r in rows if r["sample_ok"]), key=lambda r: -r["t_stat"])
    top = ranked[:TOP]
    top_ids = {id(r) for r in top}
    need_z = [r for r in rows if id(r) in top_ids or (r["gate1"] and r["beats_luck"])]
    for r in need_z:
        key = key_of[r["strategy"]]
        tr = trade_dicts(legs[key[1:]], res[key])
        r["z"], r["ctrl_gross"], r["ctrl_random"] = matched_control(mkt, tr)
        r["gate3"] = r["z"] >= Z_TO_BEAT
    if top:
        key = key_of[top[0]["strategy"]]
        tr = trade_dicts(legs[key[1:]], res[key])
        sides = [SimpleNamespace(name=s, book=mkt.books[s]) for s in DIRS]
        use(mkt)
        study = S.control(sides, tr)["avg"]
        print(
            f"\nCHECK 3 — matched control for #1: random gross {top[0]['ctrl_random']:+.6f}R here, "
            f"{study:+.6f}R from the study's own control (same seed, same draws)"
        )

    print(
        f"\nTOP {TOP} BY EXPLORE t (among strategies with >= {MIN_PER_HALF} trades in each half)\n"
        f"  RR = realised avg win / avg loss (net); win% = target hits; R net of every cost; "
        f"G1 sample+halves, G2 t above the luck bar, G3 matched control z >= {Z_TO_BEAT:g}"
    )
    print(HEAD)
    for i, r in enumerate(top, 1):
        print(fmt(i, r))
    same: dict = {}
    for r in top:
        same.setdefault(sig_of[r["strategy"]], []).append(r["strategy"])
    for names in same.values():
        if len(names) > 1:
            print(f"  SAME TRADE LIST (one event counted {len(names)}x): {', '.join(names)}")

    survivors = [r for r in rows if r["gate1"] and r["beats_luck"] and r.get("gate3")]
    above = [r for r in rows if r["gate1"] and r["beats_luck"]]
    print(
        f"\nSURVIVORS OF ALL THREE GATES: {len(survivors)}  ({len(above)} of {n_g1:,} gate-1 "
        f"strategies beat the luck bar)"
    )
    for r in survivors:
        print(f"  {r['strategy']}  t {r['t_stat']:+.2f}  z {r['z']:+.2f}")
    if not above:
        print("  NOTHING BEATS THE LUCK BAR — no strategy's t is outside what random entries give")

    tok_r, tbar_r = stream(mkt.rows, "reversed")
    occ_r = occurrences(tok_r, tbar_r)
    res_r = search(occ_r, legs, {key_of[r["strategy"]][0] for r in top})
    rev_top = {
        r["strategy"]
        for r in sorted(
            (score(mkt, legs, k, q)[0] for k, q in search(occ_r, legs).items()),
            key=lambda r: -r["t_stat"] if r["sample_ok"] else math.inf,
        )[:TOP]
    }
    print(
        "\nSUSPICIOUS? one-bar% = trades whose whole pattern printed on ONE bar; busiest month's "
        "share of trades; best month's share of net R; t with the same-bar order reversed"
    )
    bar_sets: dict = {}
    for b, tk in mkt.rows[:, [0, 3]].tolist():
        bar_sets.setdefault(b, set()).add(tk)
    top_trades = []
    for i, r in enumerate(top, 1):
        key = key_of[r["strategy"]]
        tr = trade_dicts(legs[key[1:]], res[key])
        c = concentration(mkt, tr, occ[key[0]], bar_sets, set(key[0]))
        q_r = res_r.get(key)
        t_r = score(mkt, legs, key, q_r)[0] if q_r is not None and len(q_r) else None
        r.update(c, t_reversed=t_r["t_stat"] if t_r else math.nan)
        print(
            f"  {i:>2} {r['strategy']:<36} one-bar {c['one_bar']:5.1f}%  month {c['top_month_trades']:4.1f}% "
            f"of trades, {c['top_month_r']:5.1f}% of R ({c['top_month']})  reversed "
            + (f"t {t_r['t_stat']:+.2f} n {t_r['n']}" if t_r else "pattern never forms")
        )
        print(
            f"      same-bar exposure: {c['shared']:.1f}% of trades fired on a bar that also "
            f"printed a token outside the pattern, carrying {c['shared_r']:+.1f}R of {r['tot']:+.1f}R"
        )
        if i <= 5:
            print(f"      by year (trades/net R): {by_year(mkt, tr)}")
        top_trades += [export_trade(raw, r["strategy"], t) for t in tr]
    print(
        f"  {len(rev_top & {r['strategy'] for r in top})} of the top {TOP} are still top {TOP} with the order reversed"
    )
    write_csv(out / f"top_trades_{tag}.csv", top_trades)
    write_csv(out / f"strategies_{tag}.csv", sorted(rows, key=lambda r: -r["t_stat"]))

    print("\nTOP 5 ON THE OTHER TIMEFRAMES — same explore window, same rule, 48-hour time exit")
    other = other_timeframes(a, [key_of[r["strategy"]] for r in top[:5]])
    print(HEAD.replace(" #", "tf", 1))
    for r in other:
        print(fmt(r["tf"], r))
    write_csv(out / "other_tf_top5.csv", other)
    print(
        f"\nwrote {out}/ (strategies, null, tokens, top_trades, cost_proof, "
        f"other_tf_top5) in {time.time() - t_all:.0f}s"
    )


# ─────────────────────────────── test — the one look at untouched months ───────────────────────


def test(a) -> None:
    """Named strategies on a window nobody has selected on. For gold that is ONLY the reserved
    2018-09-14 -> 2019-12-31 set, run ONCE, on strategies that passed all three explore gates."""
    if not a.spend_test_set:
        sys.exit(
            "refused: `test` spends the untouched test set, and a second look makes it in-sample. "
            "Run it once, only on strategies that passed all three explore gates, with "
            "--spend-test-set."
        )
    if a.symbol.upper().startswith("XAUUSD") and (
        pd.Timestamp(a.start) < pd.Timestamp(TEST_SET[0])
        or pd.Timestamp(a.end) > pd.Timestamp(TEST_SET[1])
    ):
        sys.exit(f"refused: a gold test window must sit inside [{TEST_SET[0]}, {TEST_SET[1]})")
    keys = [parse_sname(s) for s in a.strategies]
    raw = load(a.server_dir, a.symbol, a.tf, a.start, a.end)
    slack = pd.Timedelta(days=4)
    if raw.index[0] > pd.Timestamp(a.start) + slack or raw.index[-1] < pd.Timestamp(a.end) - slack:
        sys.exit(
            f"refused: the cache holds {raw.index[0]} -> {raw.index[-1]}, which is not the window "
            f"asked for [{a.start}, {a.end}). Fill the cache first; never score a shorter window."
        )
    mkt = build_market(raw, a.tf, a.profile)
    trade_from = int(raw.index.searchsorted(raw.index[0] + pd.Timedelta(days=a.warmup_days)))
    mkt.split = trade_from + (len(raw) - trade_from) // 2
    mkt.months = (raw.index[-1] - raw.index[trade_from]).days / 30.44
    print(
        f"engines warm for {a.warmup_days:g} days; trades from {raw.index[trade_from]:%Y-%m-%d %H:%M}"
        f", halves split at {raw.index[mkt.split]:%Y-%m-%d}"
    )
    occ = occurrences(*stream(mkt.rows, "canonical"))
    pats = {k[0] for k in keys}
    bars = np.concatenate([occ[p][:, 0] for p in pats if p in occ] or [np.array([], np.int64)])
    legs, checked, _ = walk_signals(mkt, bars[bars >= trade_from])
    res = search(occ, legs, pats)
    print(f"fast walk matched the study's on {checked:,} signal walks\n{HEAD}")
    rows = []
    for i, key in enumerate(keys, 1):
        row, tr = score(mkt, legs, key, res.get(key, np.array([], dtype=np.int64)))
        if len(tr) >= 2:
            row["z"], row["ctrl_gross"], row["ctrl_random"] = matched_control(mkt, tr)
            row["gate3"] = row["z"] >= Z_TO_BEAT
        print(fmt(i, row))
        if tr:
            print(f"      by year (trades/net R): {by_year(mkt, tr)}")
        rows += [export_trade(raw, row["strategy"], t) for t in tr]
    out = Path(a.out) if Path(a.out).is_absolute() else S.ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / f"test_trades_{a.tf}m.csv", rows)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Structure-event patterns on gold — see the docstring."
    )
    ap.add_argument("mode", choices=("explore", "test"))
    ap.add_argument("--tf", type=int, choices=TIMEFRAMES, default=5, help="minutes")
    ap.add_argument("--server-dir", default="PUPrime_Demo")
    ap.add_argument("--symbol", default="XAUUSD_p")
    ap.add_argument("--profile", default="puprime_ecn")
    ap.add_argument("--start", help="window start (inclusive); defaults to the mode's window")
    ap.add_argument("--end", help="window end (exclusive); defaults to the mode's window")
    ap.add_argument("--null-runs", type=int, default=NULL_RUNS)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", default="backtest/reports/structure_patterns")
    ap.add_argument("--strategies", nargs="+", help="test: e.g. 'HH>BOS_up|long|2R'")
    ap.add_argument(
        "--warmup-days", type=float, default=7.0, help="test: engine warm-up, no trades"
    )
    ap.add_argument("--spend-test-set", action="store_true", help="test: I have read the docstring")
    a = ap.parse_args()
    window = EXPLORE if a.mode == "explore" else TEST_SET
    a.start, a.end = a.start or window[0], a.end or window[1]
    if a.mode == "explore":
        explore(a)
    else:
        if not a.strategies:
            ap.error("test needs --strategies")
        test(a)


if __name__ == "__main__":
    main()
