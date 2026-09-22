#!/usr/bin/env python3
"""fft_blind_deck.py — a BLIND take/skip deck of past FFT version-1 trades, for the user's eye.

The question (the user, 2026-09-21): about 55 filters on the losers found nothing the numbers can
see, but the user says they would have skipped some trades on sight — an overextended 15m, liquidity
sitting above the stop, a trend line. Is that eye an edge? Only a BLIND test can say: every chart
stops the moment price first touches the 61.8, the outcome is written to a separate file, and
`blind_replay_grade.py` compares the user's takes against random picks of the same size.

  pool     every version-1 trade (first leg, all gates, 61.8 limit, stop 1.0, TP2) the study counts
           in 2020-02 -> 2025-08. The 20 recent trades the user checked on the chart (2026) are
           outside it by construction.
  draw     60, seeded, at least 7 days apart so no chart shows another setup's outcome; then shuffled.
  chart    PU Prime 5m (reopen spikes clipped, the bars the engines saw): 720 bars before the
           decision bar, then the decision bar CUT at the touch — its minutes up to the touch, the
           touch minute drawn from its open to the fill only.
  shown    the 5m leg's 1.0 and 0.0, the engines' structure breaks and swings (external and
           internal), session / day / 4-hour levels live or taken by the touch, the sweep (a level
           on the pullback's side taken between the leg's extreme and the touch, or "none"), and the
           15m trend's BOS count since its shift. The plan: entry 61.8, stop 1.0, target 38.2.
  hidden   the outcome — in outcomes.csv only (`FFT_r` is the cost-free R to TP2).

⚠ The sweep here is judged on the CUT bar, so it can differ from the study's A+ label, which reads
the touch minute's whole low; the build prints how often the two agree.

Usage:
  python backtest/tools/fft_blind_deck.py [--out backtest/reports/fft_blind]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SEED = 20260921
N = 60
GAP_DAYS = 7
BARS = 720  # 5m bars before the decision bar (2.5 days)
POOL = ("2020-01-01", "2025-09-01")
NS_MIN = 60 * 10**9

PAGE = {
    "intro": "Every chart stops the moment price first touches the 61.8 — nothing after that is on "
    "this page. Decide as you would live: take it or skip it.",
    "legend_marks": "1.0 0.0",
    "legend_marks_text": "the 5m leg",
    "legend_entry": "entry at the 61.8",
    "plan_title": "The plan",
    "entry_line": "Entry 61.8",
    "entries": [],
    "level_mark": None,
    "marks": [
        {"key": "1.0", "long": "1.0 · leg low", "short": "1.0 · leg high"},
        {"key": "0.0", "long": "0.0 · leg high", "short": "0.0 · leg low"},
    ],
    "no_sweep": "none before the entry",
    "reasons": [
        "Clean first leg",
        "Liquidity swept first",
        "Fresh 15m trend",
        "Good time of day",
        "15m overextended",
        "No sweep",
        "Liquidity sitting behind the stop",
        "Deep or messy pullback",
        "Looks like a reversal",
        "Wrong time of day / news",
    ],
}


def _p(x: float) -> float:
    return round(float(x), 2)


def main() -> int:
    import fft_first_touch_study as S
    from blind_replay import build, leaks
    from chart_context import ChartContext
    from loaded_level_study import clean_reopens

    from backtest.data.resample import resample_up

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "backtest" / "reports" / "fft_blind")
    a = ap.parse_args()

    touches, _, raw, _ = S.run(*POOL)
    clean, _ = clean_reopens(raw)
    df5 = resample_up(clean, 5, 1)
    t1 = clean.index.to_numpy().astype("datetime64[ns]").astype(np.int64)
    t5 = df5.index.to_numpy().astype("datetime64[ns]").astype(np.int64)
    cO, cH, cL = (clean[k].to_numpy() for k in ("open", "high", "low"))
    rH, rL = raw["high"].to_numpy(), raw["low"].to_numpy()
    c5 = [
        [int(t // 10**9), _p(o), _p(h), _p(lo), _p(c)]
        for t, o, h, lo, c in zip(
            t5, *(df5[k].to_numpy() for k in ("open", "high", "low", "close"))
        )
    ]

    # The study's 5m switches (`five_minute_run`), so the structure drawn is the structure traded.
    ctx = ChartContext()
    stack = S.EngineStack(S.EngineConfig(macro=False, internal=False, rsi=False))
    for i, bar in enumerate(S.iter_bars(df5)):
        ctx.record(i, stack.step(bar))

    pool = []
    for t in touches:
        if t["kind"] != "first" or not S.gated(t, max_bos=0):
            continue
        lv = t["lv"]
        w = S.walk(rH, rL, t["m"], t["d"], lv["1.0"], lv["TP2"], t["open_fill"])
        if w is None or (lv["TP2"] - t["fill"]) * t["d"] <= 0:
            continue
        pool.append((t, w))
    rng = np.random.default_rng(SEED)
    chosen = []
    for q in rng.permutation(len(pool)):
        t = pool[q][0]
        if all(abs(t1[t["m"]] - t1[x[0]["m"]]) >= GAP_DAYS * 86400 * 10**9 for x in chosen):
            chosen.append(pool[q])
        if len(chosen) == N:
            break
    if len(chosen) < N:
        sys.exit(
            f"refused: only {len(chosen)} setups {GAP_DAYS} days apart in the pool of {len(pool)}"
        )
    order = rng.permutation(len(chosen))

    setups, outcomes, agree = [], [], 0
    for n_id, q in enumerate(order, start=1):
        t, w = chosen[q]
        rid = f"F{n_id:02d}"
        d, lv, m = t["d"], t["lv"], t["m"]
        long_ = d == 1
        k = int(np.searchsorted(t5, t1[m], "right")) - 1
        a0 = k - BARS
        m0 = int(np.searchsorted(t1, t5[k]))
        fill = float(t["fill"])
        hs, ls = cH[m0 : m + 1].copy(), cL[m0 : m + 1].copy()
        om = float(cO[m])  # the touch minute: only its open and the fill are known by the touch
        hs[-1], ls[-1] = max(om, fill), min(om, fill)
        o = float(cO[m0])
        cut = [int(t5[k] // 10**9), _p(o), _p(max(hs.max(), o)), _p(min(ls.min(), o)), _p(fill)]
        last = cut[0]

        def by_touch(px: float, high: bool) -> bool:
            return bool((hs > px).any()) if high else bool((ls < px).any())

        def ts(bar: int) -> int:
            return int(t5[bar] // 10**9)

        origin, ext = int(t["key"][1]), int(t["em"])
        ext5 = int(np.searchsorted(t5, t1[ext], "right")) - 1
        marks = {
            "1.0": {
                "t": ts(origin),
                "p": _p(lv["1.0"]),
                "label": "1.0",
                "pos": "below" if long_ else "above",
            },
            "0.0": {
                "t": ts(ext5),
                "p": _p(lv["TP3"]),
                "label": "0.0",
                "pos": "above" if long_ else "below",
            },
        }
        swings = [
            {"t": ts(at), "p": _p(px), "label": lab, "scale": sc}
            for known, at, px, lab, sc in ctx.swings
            if a0 <= at and known < k
        ]
        breaks = [
            {"t": ts(bar), "t_from": ts(loc), "p": _p(px), "label": lab, "dir": dd, "scale": sc}
            for bar, loc, px, lab, dd, sc in ctx.breaks
            if a0 <= bar < k and a0 <= loc
        ]
        levels, sweep = [], None
        for name, px, made, taken, evicted, rule in ctx.levels.values():
            if made >= k:  # reported at the decision bar's close or later: after the touch
                continue
            high = rule == "sweep_high" or name in ("PDH", "PWH") or name.endswith(" H")
            if taken is not None and taken >= k:
                # Reported at the decision bar's close or later. Known by the touch only if the
                # minutes up to it had reached the level — never for a weekly close-through rule.
                taken = (
                    k if taken == k and rule.startswith("sweep") and by_touch(px, high) else None
                )
            gone = evicted is not None and evicted < k
            if taken is None and gone:
                continue  # removed before the touch without being taken: not on the chart
            if taken is not None and taken < a0:
                continue  # taken before the chart starts
            levels.append(
                {
                    "name": name,
                    "p": _p(px),
                    "t_from": ts(made),
                    "t_taken": None if taken is None else ts(taken),
                }
            )
            # the sweep: a level on the pullback's side, taken after the leg's extreme
            if (
                rule == ("sweep_low" if long_ else "sweep_high")
                and taken is not None
                and taken > ext5
            ):
                if sweep is None or taken >= sweep[0]:
                    sweep = (taken, name, px)
        agree += bool(sweep) == bool(t["swept"])
        n15 = int(t["n15"])
        st = {
            "id": rid,
            "direction": "long" if long_ else "short",
            "decision_ny": pd.Timestamp(int(t1[m]), unit="ns", tz="UTC")
            .tz_convert("America/New_York")
            .strftime("%Y-%m-%d %H:%M"),
            "bars": c5[a0:k] + [cut],
            "marks": marks,
            "swings": swings,
            "breaks": breaks,
            "levels": levels,
            "facts": [
                {"label": "15m trend", "value": f"with the trade, {n15} BOS since it turned"},
                {"label": "5m leg", "value": "first leg after the shift"},
            ],
            "plan": {
                "entry": _p(lv["E1"]),
                "stop": _p(lv["1.0"]),
                "target": _p(lv["TP2"]),
                "rr": round(abs(lv["TP2"] - lv["E1"]) / abs(lv["E1"] - lv["1.0"]), 2),
            },
        }
        if sweep:
            st["sweep"] = {"name": sweep[1], "p": _p(sweep[2]), "t": ts(sweep[0])}
        bad = leaks(st) + (
            [f"last bar {st['bars'][-1][0]} is not the decision bar {last}"]
            if st["bars"][-1][0] != last
            else []
        )
        if bad:
            sys.exit(f"refused: {rid} {bad[:3]}")
        setups.append(st)
        win, _, xm = w
        risk = abs(fill - lv["1.0"])
        outcomes.append(
            {
                "id": rid,
                "direction": st["direction"],
                "decision_ny": st["decision_ny"],
                "FFT_entry": _p(fill),
                "FFT_stop": _p(lv["1.0"]),
                "FFT_target": _p(lv["TP2"]),
                "FFT_outcome": "target" if win else "stop",
                "FFT_r": round(abs(lv["TP2"] - fill) / risk if win else -1.0, 3),
                "FFT_exit": pd.Timestamp(int(t1[xm]), unit="ns", tz="UTC")
                .tz_convert("America/New_York")
                .strftime("%Y-%m-%d %H:%M"),
                "sweep_shown": bool(sweep),
                "study_swept": bool(t["swept"]),
                "bos15": n15,
            }
        )

    doc = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tf": "5m",
        "symbol": "XAUUSD.p PU Prime",
        "tz": "America/New_York",
        "page": PAGE,
        "setups": setups,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "setups.json").write_text(json.dumps(doc, separators=(",", ":")))
    with (a.out / "outcomes.csv").open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(outcomes[0]))
        wr.writeheader()
        wr.writerows(outcomes)
    html = build(doc, "FFT Blind Replay")
    (a.out / "fft_blind_replay.html").write_text(html, encoding="utf-8")
    wins = sum(o["FFT_outcome"] == "target" for o in outcomes)
    print(
        f"\n{len(setups)} setups from a pool of {len(pool)} ({POOL[0]} -> {POOL[1]}), seed {SEED}, "
        f"{GAP_DAYS}+ days apart; {wins} reached TP2 ({wins / len(setups):.0%}), total "
        f"{sum(o['FFT_r'] for o in outcomes):+.2f}R — the take-everything baseline\n"
        f"sweep shown on {sum(o['sweep_shown'] for o in outcomes)}; agrees with the study's A+ label on "
        f"{agree} of {len(setups)}\n"
        f"page {a.out / 'fft_blind_replay.html'} ({len(html) / 1e6:.2f} MB); outcomes in "
        f"{a.out / 'outcomes.csv'} — never open it before the marks are in"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
