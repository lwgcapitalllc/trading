"""study_vs_lab.py — line a study's trades up against a lab run, trade by trade.

🔴 **Why it exists (2026-09-28).** A study said the 1-minute SOS-then-BOS entry on SOS Fade Generic
made +0.26R a trade on GBPJPY; the lab made -0.06R on the same idea. Matching the two trade lists
found the cause in one pass: 108 trades both took (same outcome on 107), 105 only the lab took
(-0.34R each, 100 of them entered before the study started watching), 76 only the study took. A
total can hide that; a match-up cannot. **No study number is quoted until it has been through
this, or it is labelled "not reconciled"** — `backtest/CLAUDE.md`.

INPUT — a study writes one JSON file:

    {"label": "...",
     "trades": [{"entry_ms": int, "dir": 1|-1, "r": float, "setup": str,
                 "start_ms": int, "note": str (optional)}, ...],
     "setups": [{"setup": str, "dir": 1|-1, "sos_ms": int, "start_ms": int}, ...]}

  entry_ms   when the position opened — the lab books a market fill at the next bar's OPEN, so a
             study entering "at the close of bar k" writes the open of bar k+1.
  setup      the setup's identity (the setup key, e.g. "SosFadeGenericStrategy:L:t1578...").
  start_ms   when the study started watching that setup for an entry.
  setups     every setup the study watched, traded or not — what lets a lab-only trade be tied to
             the setup it came from and to the study's start point for it.

LAB — `GET /backtests/runs/{id}` → `equity_curve` (entry_ms, exit_ms, direction, r).

MATCH — same direction, entry within `--tol-min` minutes (default 0: the same minute), nearest first,
each trade used once. Every matched pair prints its gap, so a tolerance is never hiding one.

EXPLAIN — each unmatched trade gets the reason this tool can SEE, never a guess:
  study only  "lab was holding a position" (a lab trade spans the entry), or "lab was flat"
  lab only    the study setup it came from (same direction, latest SOS at or before the entry) and
              whether the lab entered BEFORE or AFTER the study's start point for it; "no study
              setup" if the study never watched one.
Anything left as "lab was flat" or "no study setup" is UNEXPLAINED, and is the finding.

Usage: python3 backtest/tools/study_vs_lab.py study.json 8bcf06ffa418 [--tol-min 0] [--list 20]
"""

from __future__ import annotations

import argparse
import bisect
import json
import statistics
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional

LAB = "http://localhost:8000"


def lab_trades(run_id: str, base: str = LAB) -> List[dict]:
    with urllib.request.urlopen(f"{base}/backtests/runs/{run_id}") as r:
        run = json.load(r)
    out = []
    for t in run.get("equity_curve") or []:
        if t.get("r") is None or t.get("entry_ms") is None:
            continue
        d = str(t["direction"]).lower()
        if d not in ("long", "short"):
            raise ValueError(f"lab trade direction {t['direction']!r} is neither Long nor Short")
        out.append(
            dict(
                entry_ms=int(t["entry_ms"]),
                exit_ms=int(t["exit_ms"]),
                dir=1 if d == "long" else -1,
                r=float(t["r"]),
            )
        )
    if not out:
        raise SystemExit(f"lab run {run_id} has no trades with an R — nothing to reconcile")
    return out


def match(study: List[dict], lab: List[dict], tol_ms: int):
    """Greedy nearest-first pairing on (direction, entry time). Returns (pairs, study_only,
    lab_only) where a pair is (study_trade, lab_trade, gap_ms)."""
    cands = []
    for i, s in enumerate(study):
        for j, x in enumerate(lab):
            if s["dir"] == x["dir"]:
                gap = abs(s["entry_ms"] - x["entry_ms"])
                if gap <= tol_ms:
                    cands.append((gap, i, j))
    cands.sort()
    used_s, used_l, pairs = set(), set(), []
    for gap, i, j in cands:
        if i in used_s or j in used_l:
            continue
        used_s.add(i)
        used_l.add(j)
        pairs.append((study[i], lab[j], gap))
    pairs.sort(key=lambda p: p[1]["entry_ms"])
    return (
        pairs,
        [s for i, s in enumerate(study) if i not in used_s],
        [x for j, x in enumerate(lab) if j not in used_l],
    )


def lab_holding(lab: List[dict], t_ms: int) -> Optional[dict]:
    """The lab trade open at `t_ms`, if any (entered before it, not yet exited)."""
    for x in lab:
        if x["entry_ms"] < t_ms < x["exit_ms"]:
            return x
    return None


def source_setup(setups: List[dict], x: dict) -> Optional[dict]:
    """The study setup a lab trade came from: same direction, latest SOS at or before the entry."""
    side = sorted((s for s in setups if s["dir"] == x["dir"]), key=lambda s: s["sos_ms"])
    i = bisect.bisect_right([s["sos_ms"] for s in side], x["entry_ms"]) - 1
    return side[i] if i >= 0 else None


def explain(study_only, lab_only, lab, setups):
    for s in study_only:
        h = lab_holding(lab, s["entry_ms"])
        s["why"] = (
            f"lab was holding a position (opened {fmt(h['entry_ms'])})" if h else "lab was flat"
        )
    for x in lab_only:
        src = source_setup(setups, x)
        if src is None:
            x["why"], x["setup"] = "no study setup", None
        else:
            x["setup"] = src["setup"]
            x["why"] = (
                "entered BEFORE the study's start point"
                if x["entry_ms"] < src["start_ms"]
                else "entered AFTER the study's start point"
            )


def fmt(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def stats(rs: List[float]) -> str:
    if not rs:
        return f"{0:4d} trades"
    return f"{len(rs):4d} trades   mean {statistics.mean(rs):+.3f}R   sum {sum(rs):+8.2f}R"


def report(label, run_id, pairs, study_only, lab_only, tol_ms, n_list):
    print(
        f"\n== {label}  vs  lab run {run_id}   (match: same direction, entry within "
        f"{tol_ms // 60_000} min)"
    )
    print(f"  both        {stats([p[1]['r'] for p in pairs])}   (lab R)")
    print(f"              {stats([p[0]['r'] for p in pairs])}   (study R)")
    print(f"  study only  {stats([s['r'] for s in study_only])}")
    print(f"  lab only    {stats([x['r'] for x in lab_only])}")
    if pairs:
        same = sum((p[0]["r"] > 0) == (p[1]["r"] > 0) for p in pairs)
        gaps = Counter(p[2] // 60_000 for p in pairs)
        print(
            f"  same outcome on {same} of {len(pairs)} matched ({100 * same / len(pairs):.1f}%)"
            f"   entry gaps (min: count) {dict(sorted(gaps.items()))}"
        )
    for name, group in (("study only", study_only), ("lab only", lab_only)):
        if not group:
            continue
        why = Counter(g["why"].split(" (")[0] for g in group)
        print(f"  {name} — why:")
        for w, n in why.most_common():
            rs = [g["r"] for g in group if g["why"].startswith(w)]
            print(f"    {w:45s} {stats(rs)}")
    for name, group in (("STUDY ONLY", study_only), ("LAB ONLY", lab_only)):
        for g in group[:n_list]:
            print(
                f"    {name:10s} {fmt(g['entry_ms'])}  {'L' if g['dir'] > 0 else 'S'}  "
                f"{g['r']:+6.2f}R  {g['why']}  [{g.get('setup')}]"
                + (f"  {g['note']}" if g.get("note") else "")
            )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("study", help="the study's trade file (JSON, schema in this docstring)")
    ap.add_argument("run_id")
    ap.add_argument("--tol-min", type=int, default=0)
    ap.add_argument("--list", type=int, default=15, help="unmatched trades to print per group")
    ap.add_argument("--lab", default=LAB)
    a = ap.parse_args(argv)
    doc = json.load(open(a.study))
    study, setups = doc["trades"], doc.get("setups") or []
    if not setups:
        print("⚠ the study file lists no setups, so no lab-only trade can be tied to one")
    lab = lab_trades(a.run_id, a.lab)
    tol = a.tol_min * 60_000
    pairs, s_only, l_only = match(study, lab, tol)
    explain(s_only, l_only, lab, setups)
    report(doc.get("label", a.study), a.run_id, pairs, s_only, l_only, tol, a.list)
    return 0


if __name__ == "__main__":
    sys.exit(main())
