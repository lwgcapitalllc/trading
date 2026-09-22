"""blind_replay.py — build a BLIND take/skip replay page from a replay-setups JSON.

Strategy-agnostic: any study that writes the shape below gets the same page. Each setup's chart stops
at its DECISION bar, and the page never carries an outcome — the outcomes live in a separate file
that only the study reads, after the marks come back. That separation is the whole point: a person
who can see what happened next cannot tell you what they would have done.

THE SHAPE (one JSON object):
  {"generated": ISO8601, "tf": "5m", "symbol": "...", "tz": "America/New_York",
   "setups": [{"id", "direction": "short"|"long", "decision_ny": "YYYY-MM-DD HH:MM",
     "bars": [[t, o, h, l, c], ...],                    # t = unix seconds UTC, bar open
     "marks": {"1": {"t","p"}, "2": {...}, ...},        # any keys; drawn as labels
     "swings": [{"t","p","label","scale"}], "breaks": [{"t","t_from","p","label","dir","scale"}],
     "levels": [{"name","p","t_from","t_taken"}], "sweep": {"name","p","t"},
     "facts": [{"label","value"}],                      # optional extra rows under "The setup"
     "plan": {"entry","stop","target","rr"}}],
   "page": {...}}                                       # optional — the deck's own wording

  A mark may carry "label" (drawn instead of its key) and "pos" ("above" | "below"; without it the
  Loaded Level rule places 1 and 2 on the setup's side). `page` (added 2026-09-21 for the FFT deck)
  may set: intro, legend_marks, legend_marks_text, legend_entry, plan_title, entry_line,
  entry_question, entries ([{value, label}]; [] hides the question), reasons ([...]), marks
  ([{key, long, short}] — the fact rows), level_mark (the mark whose line runs to the decision; null
  for none), no_sweep (the row shown when a setup has no sweep). ⚠ Every default is the Loaded Level
  deck's wording, so a deck without `page` renders exactly as it did before.

🔴 The build REFUSES a setup that leaks the future: any bar, mark, swing, break, level or sweep time
   after its last bar, or any outcome-looking key on a setup. A blind page that is not blind looks
   exactly like one that is.

Marks are saved by the published page (claude.ai artifact `db` capability) under
`decks/<generated>/marks/<setup id>`; the page falls back to the viewer's browser when it cannot.

Usage:
  python backtest/tools/blind_replay.py SETUPS.json --title "Loaded Level Blind Replay" --out PAGE.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("blind_replay_page.html")
OUTCOME_KEYS = {"outcome", "outcomes", "result", "results", "r", "r_gross", "exit", "exit_t", "win"}


def leaks(setup: dict) -> list[str]:
    """Every reason this setup would show the viewer something from after its decision bar."""
    bars = setup.get("bars") or []
    if not bars:
        return ["no bars"]
    last = bars[-1][0]
    problems = []
    if any(bars[k][0] >= bars[k + 1][0] for k in range(len(bars) - 1)):
        problems.append("bar times are not strictly increasing")
    times = [(f"mark {k}", m["t"]) for k, m in (setup.get("marks") or {}).items() if m]
    times += [("swing", w["t"]) for w in setup.get("swings") or []]
    times += [("break", b["t"]) for b in setup.get("breaks") or []]
    for lv in setup.get("levels") or []:
        times += [("level " + lv["name"], t) for t in (lv.get("t_from"), lv.get("t_taken")) if t]
    if setup.get("sweep"):
        times.append(("sweep", setup["sweep"]["t"]))
    problems += [f"{what} at {t} is after the decision bar {last}" for what, t in times if t > last]
    problems += [f"outcome-looking key '{k}'" for k in OUTCOME_KEYS & set(setup)]
    problems += [
        f"outcome-looking key 'plan.{k}'" for k in OUTCOME_KEYS & set(setup.get("plan") or {})
    ]
    problems += [
        f"outcome-looking fact '{x.get('label')}'"
        for x in setup.get("facts") or []
        if str(x.get("label", "")).strip().lower() in OUTCOME_KEYS
    ]
    return problems


def build(data: dict, title: str) -> str:
    bad = {s.get("id", "?"): leaks(s) for s in data.get("setups", [])}
    bad = {k: v for k, v in bad.items() if v}
    if bad:
        lines = [f"  {k}: {'; '.join(v[:3])}" for k, v in list(bad.items())[:10]]
        raise SystemExit("refusing to build a page that leaks the outcome:\n" + "\n".join(lines))
    if not data.get("setups"):
        raise SystemExit("no setups in the file")
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    for token in ("__TITLE__", "/*__DECK_JSON__*/"):
        if token not in html:
            raise SystemExit(f"template is missing {token}")
    return html.replace("__TITLE__", title).replace("/*__DECK_JSON__*/", payload)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build a blind take/skip replay page — see the docstring."
    )
    ap.add_argument("setups", type=Path)
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    data = json.loads(a.setups.read_text(encoding="utf-8"))
    html = build(data, a.title)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(html, encoding="utf-8")
    n = len(data["setups"])
    print(f"{a.out}: {n} setups, {len(html) / 1e6:.2f} MB, deck {data.get('generated')}")


if __name__ == "__main__":
    main()
