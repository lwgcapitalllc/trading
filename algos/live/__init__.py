"""algos/live/ — the live runtime for a `strategies/python/` bot on an MT5 terminal.

The seam between a validated backtest and real orders. Nothing here contains strategy logic:
the same `SosFadeStrategy` object the lab replays is stepped bar by bar, and this package
only supplies it with live bars and mirrors its intent onto the broker.

    runner.py    the loop — connect, verify the version pin, warm the engines, step, reconcile
    feed.py      MT5 bars → the canonical replay frame; new-CLOSED-bar detection
    bridge.py    strategy intent ⇄ MT5 orders; halts when the two ledgers disagree
    ledger.py    the append-only JSONL trade + decision log
    config.py    one bot's instance configuration (which terminal, which account, which version)
    version.py   the content pin that makes "which version is trading" answerable

Design decisions and the full build plan: `docs/LIVE_TRADING_PIPELINE.md`.

Modules are imported by BARE NAME (the repo-wide "dir on sys.path" convention) because
`runner.py` is launched as a script by Task Scheduler, not as a package.
"""
