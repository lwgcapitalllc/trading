#!/usr/bin/env python3
"""Dump the seeded prop-firm ruleset KPIs straight from the live lab.db.

This is the canonical "what does our ruleset engine actually hold right now" query.
Run it before/after editing docs/PROP_RULESET_KPIS.md to confirm the doc matches the DB.

Usage (from anywhere):
    python3 command-center/backend/scripts/prop_kpi_audit.py            # markdown table
    python3 command-center/backend/scripts/prop_kpi_audit.py --json     # raw JSON (one obj per row)

Read-only. Touches nothing. The SQL below is the saved query — keep it and the doc in sync.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "lab.db"

# ── The saved query — core KPIs for every prop challenge, eval + funded ────────
QUERY = """
SELECT
    id,
    name,
    ruleset_type,                 -- prop_eval | prop_funded
    account_tier,                 -- eval | funded
    account_size,
    profit_target,                -- 0 on funded (no target)
    drawdown_type,                -- trailing_eod for all current rows
    max_loss_eod,                 -- the trailing max-loss $ amount (the drawdown)
    mll_lock_balance,             -- balance at which the trailing floor locks (NULL = never / funded)
    drawdown_unit,                -- usd
    consistency_pct,              -- NULL = no consistency rule
    consistency_breach_action,    -- raise_target (FundedNext) | NULL = breach fails/none
    min_trading_days,             -- NULL = no published minimum
    daily_loss_cap,               -- DLL where the firm enforces one (mostly funded)
    profit_split_pct,             -- funded payout split
    force_flat_time_et,           -- daily auto-flat time (ET)
    max_contracts,                -- JSON: mini_max/micro_max + scaling ladder
    docs_url,
    reference_urls
FROM rulesets
WHERE ruleset_type IN ('prop_eval', 'prop_funded')
ORDER BY id;
"""

CORE_COLS = [
    "id",
    "account_tier",
    "account_size",
    "profit_target",
    "max_loss_eod",
    "mll_lock_balance",
    "consistency_pct",
    "consistency_breach_action",
    "min_trading_days",
    "daily_loss_cap",
    "profit_split_pct",
    "force_flat_time_et",
]


def _fmt(v):
    return "—" if v is None else v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of a table")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"lab.db not found at {DB_PATH}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(QUERY).fetchall()]
    conn.close()

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    hdr = "| " + " | ".join(CORE_COLS) + " |"
    sep = "| " + " | ".join("---" for _ in CORE_COLS) + " |"
    print(f"# {len(rows)} prop rulesets in lab.db\n")
    print(hdr)
    print(sep)
    for r in rows:
        print("| " + " | ".join(str(_fmt(r[c])) for c in CORE_COLS) + " |")
    print("\nContract scaling + links per row:")
    for r in rows:
        print(f"\n## {r['id']}")
        print(f"- contracts: {r['max_contracts']}")
        print(f"- docs: {r['docs_url']}")
        print(f"- refs: {_fmt(r['reference_urls'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
