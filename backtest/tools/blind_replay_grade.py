"""blind_replay_grade.py — grade a finished blind replay against what actually happened.

The counterpart to `blind_replay.py`, and deliberately the only place the two halves meet: the
page never carries an outcome, so the marks and the outcomes only ever join HERE, after the
person has finished. Strategy-agnostic — it needs a folder of mark documents and an outcomes CSV,
nothing about loaded levels.

THE QUESTION IT ANSWERS: does the discretionary filter BEAT taking every setup? A hand-picked
subset that makes more R than the whole deck has proved nothing on its own — picking 24 of 60 at
random moves the number too. So every verdict here is stated against a permutation control: the
same count of setups drawn at random from the same deck, many times, and the share of those draws
that beat the person's own pick. That share IS the p-value, and it is the headline.

🔴 A setup marked TAKE whose entry never filled is R = 0, not a missing row. Dropping it would
   grade the person on trades they could not have been in and flatter every entry that is fussy
   about filling. Rule 3 — never record what you asked for as what you got.

Marks: one JSON file per setup, as `ArtifactData` saves them — {"id", "data": {...}} or the bare
document. Outcomes: the CSV written beside the deck, with `<CODE>_r` / `<CODE>_outcome` columns.

Usage:
  python backtest/tools/blind_replay_grade.py MARKS_DIR OUTCOMES.csv [--entry E0] [--draws 100000]
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def load_marks(folder: Path) -> dict[str, dict]:
    """Every mark document under `folder`, keyed by setup id."""
    out: dict[str, dict] = {}
    for p in sorted(folder.rglob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        body = doc.get("data", doc)
        sid = body.get("id") or doc.get("id") or p.stem
        out[sid] = body
    if not out:
        raise SystemExit(f"no mark documents under {folder}")
    return out


def load_outcomes(path: Path) -> tuple[dict[str, dict], list[str]]:
    """The outcome rows keyed by setup id, and the entry codes the CSV carries."""
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        raise SystemExit(f"no rows in {path}")
    codes = sorted({k[:-2] for k in rows[0] if k.endswith("_r")})
    return {r["id"]: r for r in rows}, codes


def r_of(row: dict, code: str) -> float:
    """This setup's R on `code` — 0.0 when the entry never filled, which is a real no-trade."""
    raw = (row.get(f"{code}_r") or "").strip()
    return float(raw) if raw else 0.0


def filled(row: dict, code: str) -> bool:
    return bool((row.get(f"{code}_r") or "").strip())


def block(name: str, r: np.ndarray, hit: np.ndarray, fills: np.ndarray) -> str:
    n = len(r)
    if not n:
        return f"  {name:<22} (none)"
    took = int(fills.sum())
    wr = 100.0 * hit[fills].mean() if took else 0.0
    return (
        f"  {name:<22} {n:>3} marked  {took:>3} filled  "
        f"win {wr:>5.1f}%  avg {r.mean():+.3f}R  total {r.sum():+7.2f}R"
    )


def permute(all_r: np.ndarray, k: int, draws: int, seed: int) -> tuple[np.ndarray, float]:
    """`draws` random picks of k setups. Returns their totals and the deck-wide mean R."""
    rng = np.random.default_rng(seed)
    n = len(all_r)
    idx = np.argsort(rng.random((draws, n)), axis=1)[:, :k]
    return all_r[idx].sum(axis=1), float(all_r.mean())


def main() -> None:
    ap = argparse.ArgumentParser(description="Grade a blind replay — see the docstring.")
    ap.add_argument("marks", type=Path)
    ap.add_argument("outcomes", type=Path)
    ap.add_argument("--entry", default="", help="entry code to grade on (default: every code)")
    ap.add_argument("--draws", type=int, default=100_000)
    ap.add_argument("--seed", type=int, default=20260919)
    a = ap.parse_args()

    marks = load_marks(a.marks)
    outcomes, codes = load_outcomes(a.outcomes)
    if a.entry:
        codes = [a.entry]

    ids = [s for s in outcomes if s in marks]
    missing = sorted(set(outcomes) - set(marks))
    unmarked = [s for s in ids if not (marks[s].get("decision") or "").strip()]
    print(f"deck: {len(outcomes)} setups, {len(ids)} marked, {len(missing)} with no mark document")
    if missing:
        print(f"  no mark: {', '.join(missing)}")
    if unmarked:
        print(f"  mark document with no decision: {', '.join(unmarked)}")
    ids = [s for s in ids if s not in unmarked]

    take = np.array([(marks[s]["decision"] == "take") for s in ids])
    print(f"  his call: {int(take.sum())} take, {int((~take).sum())} skip\n")

    for code in codes:
        all_r = np.array([r_of(outcomes[s], code) for s in ids])
        fills = np.array([filled(outcomes[s], code) for s in ids])
        hit = all_r > 0
        print(f"{code} — R is cost-free; an unfilled entry counts as a flat no-trade")
        print(block("every setup", all_r, hit, fills))
        print(block("he took", all_r[take], hit[take], fills[take]))
        print(block("he skipped", all_r[~take], hit[~take], fills[~take]))

        k = int(take.sum())
        if 0 < k < len(ids):
            totals, deck_mean = permute(all_r, k, a.draws, a.seed)
            his = float(all_r[take].sum())
            beat = float((totals >= his).mean())
            print(
                f"  control: {a.draws:,} random picks of {k} from the same deck — "
                f"{beat * 100:.1f}% of them made {his:+.2f}R or more"
            )
            print(
                f"           random pick averages {deck_mean * k:+.2f}R, "
                f"his edge over it {his - deck_mean * k:+.2f}R"
            )
        print()

    # Which stated reason went with which result, on the first entry code only.
    code = codes[0]
    tally: dict[str, list[float]] = {}
    for s in ids:
        for why in marks[s].get("reasons") or []:
            tally.setdefault(why, []).append(r_of(outcomes[s], code))
    if tally:
        print(f"what he said decided it — {code} R of the setups carrying each reason")
        for why, rs in sorted(tally.items(), key=lambda kv: -np.mean(kv[1])):
            arr = np.array(rs)
            print(f"  {why:<38} {len(arr):>3}  avg {arr.mean():+.3f}R  total {arr.sum():+7.2f}R")
        print()

    # Did "wait for the SOS" beat "at 2" on the setups where he asked for it?
    pref = {s: (marks[s].get("entry") or "") for s in ids if marks[s]["decision"] == "take"}
    pairs = [c for c in ("E0", "E3", "E4") if c in set().union(*[set(codes), set(codes)])]
    if len(pairs) > 1:
        print("his entry preference, on the setups he took")
        for want, label in (("at2", "he wanted at 2"), ("sos", "he wanted the SOS")):
            sel = [s for s, v in pref.items() if v == want]
            if not sel:
                continue
            bits = [f"{c} {np.mean([r_of(outcomes[s], c) for s in sel]):+.3f}R" for c in pairs]
            print(f"  {label:<22} {len(sel):>3} setups   " + "   ".join(bits))


if __name__ == "__main__":
    main()
