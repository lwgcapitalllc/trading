"""
shared_calmar.py — Live Calmar Ratio Tracker
Used by both bots. Each bot has its own equity log file.

Jason's #1 metric: Calmar = annualized return / max drawdown
  2.0 = okay
  3.0 = decent (prop firm ready)
  5.0+ = generational edge

Records equity after every trade close and prints a full
performance report every morning at daily reset.
"""

import json, logging, numpy as np, pandas as pd
from datetime import datetime
from pathlib import Path

log = logging.getLogger("CALMAR")


class CalmarTracker:
    def __init__(self, starting_balance: float, equity_file="equity.json"):
        self.start_balance = starting_balance
        self.start_date    = datetime.utcnow()
        self.equity_file   = equity_file
        self.equity_log    = []
        self.peak          = starting_balance
        self.max_dd        = 0.0
        self._load()

    def _load(self):
        if Path(self.equity_file).exists():
            with open(self.equity_file) as f:
                self.equity_log = json.load(f)
            if self.equity_log:
                self.peak       = max(e["balance"] for e in self.equity_log)
                self.start_date = datetime.fromisoformat(self.equity_log[0]["date"])
                log.info(f"Loaded {len(self.equity_log)} equity records from {self.equity_file}")

    def _save(self):
        # Keep last 1000 snapshots
        with open(self.equity_file, "w") as f:
            json.dump(self.equity_log[-1000:], f, indent=2)

    def record(self, balance: float):
        """Call once per day or after each trade closes."""
        entry = {"date": datetime.utcnow().isoformat(), "balance": round(balance, 2)}
        self.equity_log.append(entry)
        self.peak   = max(self.peak, balance)
        dd          = (self.peak - balance) / self.peak
        self.max_dd = max(self.max_dd, dd)
        self._save()

    def get_metrics(self) -> dict:
        if not self.equity_log: return {}
        bal   = self.equity_log[-1]["balance"]
        days  = max(1, (datetime.utcnow() - self.start_date).days)
        years = days / 365.0
        tot_r = (bal / self.start_balance) - 1
        ann_r = (1 + tot_r) ** (1 / max(years, 0.1)) - 1
        calmar= ann_r / self.max_dd if self.max_dd > 0.001 else 0.0

        bals   = pd.Series([e["balance"] for e in self.equity_log])
        d_rets = bals.pct_change().dropna()
        vol    = float(d_rets.std() * np.sqrt(252)) if len(d_rets) > 1 else 0.01
        sharpe = ann_r / vol if vol > 0 else 0.0
        cur_dd = (self.peak - bal) / self.peak

        grade = (
            "GENERATIONAL" if calmar >= 5 else
            "EXCELLENT"    if calmar >= 3 else
            "DECENT"       if calmar >= 2 else
            "BELOW TARGET"
        )

        return {
            "balance":           round(bal, 2),
            "start_balance":     round(self.start_balance, 2),
            "total_return_pct":  round(tot_r * 100, 2),
            "annual_return_pct": round(ann_r * 100, 2),
            "max_drawdown_pct":  round(self.max_dd * 100, 2),
            "current_dd_pct":    round(cur_dd * 100, 2),
            "peak":              round(self.peak, 2),
            "calmar":            round(calmar, 2),
            "sharpe":            round(sharpe, 2),
            "days_tracked":      days,
            "grade":             grade,
        }

    def log_report(self):
        m = self.get_metrics()
        if not m: return
        log.info("─" * 55)
        log.info(f"  Balance     ${m['balance']:>10,.2f}  (started ${m['start_balance']:,.2f})")
        log.info(f"  Return      {m['total_return_pct']:>+.2f}%  "
                 f"({m['annual_return_pct']:>+.2f}% annualised)")
        log.info(f"  Max DD      {m['max_drawdown_pct']:.2f}%   "
                 f"Current DD {m['current_dd_pct']:.2f}%")
        log.info(f"  Calmar      {m['calmar']:.2f}   [{m['grade']}]   "
                 f"Sharpe {m['sharpe']:.2f}")
        log.info(f"  Days live   {m['days_tracked']}")
        log.info(f"  Target      Calmar ≥ 3.0 (Jason's benchmark)")
        log.info("─" * 55)
