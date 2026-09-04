#!/usr/bin/env python3
"""Audit a LIVE re-entry trade against the strategy it is supposed to be following.

**Why this exists.** The re-entry went live on 2026-09-02 and had never placed a real order. The
answer to *"did it do the right thing"* must not be a person reading a log — Aaron's instruction,
the same day: *"whenever it happens and whenever it closes, you execute that script and you make
sure it did every single thing according to the strategy."* So this is that script.

**What it reads.** The bot's own decision ledger — the append-only record it writes as it goes.
That file is the only place several of these facts exist at all: a broker statement records the
deals that happened and has no way to say the stop was ratcheted eleven times, or that a rung was
refused, or that the trade was opened by the re-entry rather than the primary.

🔴 **A CHECK THAT CANNOT RUN REPORTS `NOT CHECKED`, NEVER `PASS`.** That is the single rule this
tool is built around, because the failure it is guarding against is a clean report on a trade
nobody actually verified. Every unanswerable question is printed with the reason it could not be
answered, and the summary counts them separately from the passes.

⚠ **It re-derives rather than re-reading wherever it can.** The R multiple is recomputed from the
recorded prices and compared to the stored one; the risk is recomputed from the position's own
size and stop. A metric that reproduces its own arithmetic has been checked against nothing.

⚠ **It audits ONE TRADE against the settings the bot is running TODAY.** If a setting moved
between the trade and the audit, the comparison is wrong in a way nothing here can detect — pass
`--config` a copy of the file as it was, or re-read the config note beside the change.

Usage:
    python3 algos/tools/audit_reentry.py --bot sos_fade_demo
    python3 algos/tools/audit_reentry.py --bot sos_fade_demo --ticket 360712345
    python3 algos/tools/audit_reentry.py --bot sos_fade_demo --date 2026-09-03 --all-legs

Exit codes: 0 every check passed, 1 something FAILED, 2 nothing to audit.
⚠ **A run with unanswered checks still exits 0** — they are not failures — so read the summary
line rather than the exit code alone when that count is non-zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parents[2]

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "NOT CHECKED"


class Report:
    """Findings for one trade. Ordered, and it keeps unanswered questions separate from passes."""

    def __init__(self, ticket, intent: str):
        self.ticket = ticket
        self.intent = intent
        self.rows: list[tuple[str, str, str]] = []

    def check(self, verdict: str, rule: str, detail: str) -> None:
        self.rows.append((verdict, rule, detail))

    def ok(self, rule, detail=""):
        self.check(PASS, rule, detail)

    def bad(self, rule, detail):
        self.check(FAIL, rule, detail)

    def unknown(self, rule, why):
        """⚠ `why` is required. An unanswered check with no stated reason is indistinguishable
        from one nobody wrote, which is the thing this tool exists to prevent."""
        self.check(UNKNOWN, rule, why)

    @property
    def failures(self):
        return [r for r in self.rows if r[0] == FAIL]

    @property
    def unanswered(self):
        return [r for r in self.rows if r[0] == UNKNOWN]


def load_ledger(bot: str, date: Optional[str]) -> list[dict]:
    """Every decision record for a bot, from the committed archive and the live directory both.

    ⚠ **Two locations on purpose.** The archive is what `ledger_sync.py` commits; the live
    directory is what the bot is appending to right now. A trade that closed an hour ago is only
    in the second, and an audit that read the archive alone would report *no trades* for exactly
    the trade somebody is asking about.

    🔴 **ONE FILE PER DAY, AND THE LIVE COPY WINS — IT READ BOTH UNTIL 2026-09-03.**
    `ledger_sync.py` **copies** rather than moves, so a day that has been synced exists in both
    places and every one of its rows was loaded TWICE. MEASURED on the trading box: 25 files in
    both, **2,177 of 4,865 rows duplicated**. The trade records survived it (they are keyed by
    ticket downstream), but the EVENT rows do not — a stop that ratcheted eleven times reported
    twenty-two, and the health record's row count was inflated by nearly half. **A report built
    to be trusted was quietly doubling its own evidence.**

    ⚠ **The live copy wins because the archive is a SNAPSHOT taken at the last sync**, so it can
    only ever be a prefix of the file the bot is still appending to. Preferring the archive would
    silently drop everything since the last sync — which includes the trade somebody is asking
    about.

    ⚠ **A day that exists ONLY in the archive is still read.** The bot's instance directory is
    pruned; the archive is the long history, and this tool has to be able to audit an old trade.
    """
    roots = [
        _REPO / "algos" / "ledger_archive" / bot / "ledger",
        _REPO / "algos" / "markets" / "fx" / "instances" / bot / "ledger",
    ]
    pattern = f"decisions-{date}.jsonl" if date else "decisions-*.jsonl"
    # Keyed on the FILENAME, which is the day. Later roots overwrite earlier ones, so the live
    # directory replaces the archive's copy of the same day rather than adding to it.
    chosen: dict = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob(pattern)):
            chosen[path.name] = path
    rows = []
    for name in sorted(chosen):
        path = chosen[name]
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # A file being appended to can end mid-line. Dropping the torn tail is right;
                # dropping it SILENTLY is not, so say so — it could be the trade in question.
                print(f"  ⚠ torn line ignored in {path.name}", file=sys.stderr)
    if not chosen:
        print(
            f"  ⚠ no ledger files matched {pattern} under {[str(r) for r in roots]}",
            file=sys.stderr,
        )
    return rows


def load_config(bot: str, override: Optional[str]) -> dict:
    path = (
        Path(override)
        if override
        else (_REPO / "algos" / "markets" / "fx" / "instances" / bot / "config.json")
    )
    return json.loads(path.read_text(encoding="utf-8"))


def expected_risk_pct(params: dict, intent: str) -> Optional[float]:
    """What this leg is SUPPOSED to risk, as a % of the sizing basis.

    ⚠ It mirrors `Execution._secondary_pending`: the re-entry's percentage is a fraction OF the
    primary's, never an absolute. An audit is allowed to restate a rule — that is what auditing
    is — but it must restate the right one, so this is the line to re-read if that changes.
    """
    base = params.get("exec_risk_pct")
    if base is None:
        return None
    if intent != "secondary":
        return float(base)
    frac = params.get("exec_sec_risk_pct")
    return None if frac is None else float(base) * float(frac) / 100.0


def audit_trade(opened: dict, closed: Optional[dict], events: list[dict], params: dict) -> Report:
    intent = opened.get("intent", "primary")
    rep = Report(opened.get("ticket"), intent)
    direction = 1 if str(opened.get("dir", "")).upper().startswith("L") else -1
    entry = opened.get("price")
    stop0 = opened.get("stop")

    # ── 1. it is what we think it is ─────────────────────────────────────────
    if intent == "secondary":
        rep.ok("opened by the re-entry", "the record says so")
    else:
        rep.ok(f"opened by the {intent}", "not a re-entry — audited as a primary")

    # ── 2. size ──────────────────────────────────────────────────────────────
    want_pct = expected_risk_pct(params, intent)
    got_pct = opened.get("risk_pct_realised")
    if want_pct is None:
        rep.unknown("risk sized correctly", "the config states no risk percentage for this leg")
    elif got_pct is None:
        rep.unknown(
            "risk sized correctly",
            "the bot could not read the account balance when it opened, so no percentage was "
            "recorded — the dollars are $%s" % opened.get("risk_usd"),
        )
    else:
        # 5% tolerance: the lot step rounds DOWN, so a small shortfall is correct behaviour and
        # any EXCESS is not. Both directions are reported, and only one of them is a defect.
        drift = (got_pct - want_pct) / want_pct * 100.0
        detail = f"risked {got_pct:.3f}% (${opened.get('risk_usd')}), expected {want_pct:.3f}%"
        if got_pct > want_pct * 1.01:
            rep.bad("risk sized correctly", f"{detail} — OVER by {drift:+.1f}%, never allowed")
        elif drift < -5.0:
            rep.bad("risk sized correctly", f"{detail} — UNDER by {drift:.1f}%, more than rounding")
        else:
            rep.ok("risk sized correctly", detail)

    # ── 3. a stop was attached, on the right side ────────────────────────────
    if not stop0:
        rep.bad("stop attached at entry", "no stop on the opening record — the position was naked")
    elif entry is None:
        rep.unknown("stop attached at entry", "no entry price recorded")
    elif (direction > 0 and stop0 >= entry) or (direction < 0 and stop0 <= entry):
        rep.bad("stop attached at entry", f"stop {stop0} is the wrong side of entry {entry}")
    else:
        rep.ok("stop attached at entry", f"{stop0} vs entry {entry}")

    # ── 4. nothing banked at a price, when the settings say nothing should ───
    banks = [e for e in events if e.get("kind") == "event" and e.get("event") == "partial_banked"]
    tp1 = params.get("exec_sec_tp1_pct" if intent == "secondary" else "exec_tp1_pct")
    if tp1 is None:
        rep.unknown("banking matches the settings", "the config states no take-profit for this leg")
    elif float(tp1) == 0.0 and float(params.get("exec_tp2_pct", 0) or 0) == 0.0:
        if banks:
            rep.bad(
                "banking matches the settings",
                f"{len(banks)} partial bank(s) on a leg configured to bank NOTHING",
            )
        else:
            rep.ok("banking matches the settings", "set to bank nothing, and nothing was banked")
    elif banks:
        rep.ok("banking matches the settings", f"{len(banks)} bank(s), take-profit is {tp1}%")
    else:
        rep.bad(
            "banking matches the settings",
            f"take-profit is {tp1}% but nothing was ever banked — the trade rode where the "
            f"backtest scaled out",
        )

    # ── 5. the stop only ever moved in the trade's favour ────────────────────
    moves = [e for e in events if e.get("kind") == "event" and e.get("event") == "stop_moved"]
    widened = [
        m
        for m in moves
        if m.get("was") is not None
        and m.get("now") is not None
        and ((direction > 0 and m["now"] < m["was"]) or (direction < 0 and m["now"] > m["was"]))
    ]
    if widened:
        rep.bad(
            "the stop never widened",
            f"{len(widened)} of {len(moves)} moves went AGAINST the trade, e.g. "
            f"{widened[0].get('was')} → {widened[0].get('now')}",
        )
    elif moves:
        rep.ok("the stop never widened", f"{len(moves)} move(s), all in the trade's favour")
    else:
        rep.ok("the stop never widened", "it never moved")

    # ── 6. the stop was refusing to report, at any point ─────────────────────
    blind = [
        e
        for e in events
        if e.get("kind") == "event" and e.get("event") == "secondary_stop_unreadable"
    ]
    if blind:
        rep.bad(
            "the stop was managed throughout",
            f"{len(blind)} bar(s) where the strategy could not report its stop — the broker's "
            f"stop stood still while the strategy believed it was ratcheting",
        )
    else:
        rep.ok("the stop was managed throughout", "no unreadable-stop records")

    # ── 7. the exit ──────────────────────────────────────────────────────────
    if closed is None:
        rep.unknown("the exit", "the trade is still open, or its closing record is not in range")
        return rep

    reason = closed.get("reason") or ""
    if not reason:
        rep.bad("the exit reason is recorded", "no reason on the closing record")
    else:
        rep.ok("the exit reason is recorded", reason)

    # ── 8. R recomputed from the prices, not read back ───────────────────────
    stored_r = closed.get("r")
    exit_px = closed.get("price")
    if None in (entry, stop0, exit_px) or not stop0:
        rep.unknown("R matches the prices", "a price is missing from the record")
    elif stored_r is None:
        rep.unknown("R matches the prices", "no R was recorded — the risk basis was unknown")
    else:
        risk_dist = abs(entry - stop0)
        derived = (exit_px - entry) * direction / risk_dist if risk_dist else None
        # ⚠ The recorded R is NET of swap and commission and this one is GROSS of them, so they
        # do not have to match exactly — a wide gap is what matters, and costs are usually a
        # few hundredths of an R. This is a sanity check, not an equality.
        if derived is None:
            rep.unknown("R matches the prices", "the stop distance is zero")
        elif abs(derived - stored_r) > 0.25:
            rep.bad(
                "R matches the prices",
                f"recorded {stored_r:+.2f}R, prices imply {derived:+.2f}R gross — a gap this "
                f"wide is not costs",
            )
        else:
            rep.ok(
                "R matches the prices",
                f"recorded {stored_r:+.2f}R net, prices imply {derived:+.2f}R gross",
            )

    # ── 9. the costs are recorded, so the P&L is net ─────────────────────────
    missing = [k for k in ("gross_usd", "swap_usd", "commission_usd") if closed.get(k) is None]
    if missing:
        rep.unknown(
            "costs recorded separately",
            f"the broker could not be asked for {', '.join(missing)} — the P&L may not be net",
        )
    else:
        rep.ok(
            "costs recorded separately",
            f"gross ${closed['gross_usd']}, swap ${closed['swap_usd']}, "
            f"commission ${closed['commission_usd']}, net ${closed.get('pnl_usd')}",
        )

    # ── 10. the time stop, if that is how it ended ───────────────────────────
    hours = params.get("exec_time_stop_hrs")
    if reason and "time" in reason.lower():
        if hours is None:
            rep.unknown("the time stop fired at the right age", "no time-stop setting in config")
        else:
            rep.unknown(
                "the time stop fired at the right age",
                f"the record holds a bar COUNT ({closed.get('held_bars')}) and not a duration; "
                f"converting it needs the clock that opened the trade, which is the "
                f"{'5-minute' if intent == 'secondary' else '15-minute'} one. Setting is {hours}h",
            )

    return rep


def render(rep: Report) -> None:
    head = f"trade {rep.ticket} — opened by the {rep.intent}"
    print(f"\n{head}\n{'-' * len(head)}")
    for verdict, rule, detail in rep.rows:
        mark = {PASS: "ok  ", FAIL: "FAIL", UNKNOWN: "??  "}[verdict]
        print(f"  {mark} {rule}" + (f" — {detail}" if detail else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bot", required=True, help="the bot's key, e.g. sos_fade_demo")
    ap.add_argument("--date", help="YYYY-MM-DD. Default: every day on disk.")
    ap.add_argument("--ticket", type=int, help="audit one trade")
    ap.add_argument("--config", help="a config.json to audit against, if the live one has moved")
    ap.add_argument(
        "--all-legs",
        action="store_true",
        help="audit primaries too. Default is re-entries only, which is what this tool is for.",
    )
    args = ap.parse_args()

    rows = load_ledger(args.bot, args.date)
    params = load_config(args.bot, args.config).get("strategy_params", {})

    trades = [r for r in rows if r.get("kind") == "trade"]
    opens = {t["ticket"]: t for t in trades if t.get("event") == "opened"}
    closes = {t["ticket"]: t for t in trades if t.get("event") == "closed"}

    wanted = [
        t
        for t in opens.values()
        if (args.ticket is None or t["ticket"] == args.ticket)
        and (args.all_legs or t.get("intent") == "secondary")
    ]
    if not wanted:
        which = "re-entry" if not args.all_legs else ""
        print(
            f"No {which} trades to audit for {args.bot}"
            + (f" on {args.date}" if args.date else "")
            + (f", ticket {args.ticket}" if args.ticket else "")
            + "."
        )
        # ⚠ Exit 2, not 0. "Nothing to audit" and "everything passed" must not be the same answer
        # — that is the whole failure mode a clean report is supposed to rule out.
        return 2

    reports = []
    for op in sorted(wanted, key=lambda t: t.get("ts", "")):
        ticket = op["ticket"]
        events = [r for r in rows if r.get("ticket") == ticket and r.get("kind") not in ("trade",)]
        rep = audit_trade(op, closes.get(ticket), events, params)
        reports.append(rep)
        render(rep)

    # ── one re-entry per setup, across the whole range ───────────────────────
    cap = params.get("exec_sec_max_per_setup")
    secondaries = [t for t in opens.values() if t.get("intent") == "secondary"]
    print()
    if cap is not None and len(secondaries) > int(cap):
        print(
            f"  ?? {len(secondaries)} re-entries in this range against a cap of {cap} PER SETUP "
            f"— not a failure on its own, because this range may hold several setups. Check "
            f"they are not the same one."
        )

    failed = sum(len(r.failures) for r in reports)
    unknown = sum(len(r.unanswered) for r in reports)
    passed = sum(len(r.rows) - len(r.failures) - len(r.unanswered) for r in reports)
    print(f"{len(reports)} trade(s): {passed} passed, {failed} FAILED, {unknown} not checked.")
    if unknown:
        print("  ⚠ 'not checked' is not 'passed'. Read each one above before calling this clean.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
