"""A broker account's REAL history — its balance over time and every trade on it — off MT5's own deals.

**Why (Aaron, 2026-09-17):** the Bots page showed what each bot's own record says it made. That
is a claim by the bot. The broker's deal history is the account's own statement: every trade,
every deposit, every withdrawal, whoever placed it. This module turns that statement into the
three things the account page draws — the balance, the price chart with every trade on it, and the
same analysis panels a backtest gets.

**Where the deals come from.** Each live bot mirrors its account's whole MT5 deal history into
`<instance>/ledger/deals-YYYY-MM-DD.jsonl` (`algos/live/ledger.py::deal_history`), one row per
deal, stamped with the account it was read on. The box's own files are read first; the git
archive (`algos/ledger_archive/<bot>/ledger/`) is the fallback. **The answer names which one it
used and the newest deal it holds**, because an hour-old backup and the live box must never look
the same.

Rules, each one a way this goes wrong silently:

- 🔴 **Every bot on an account writes the SAME history**, and a bot that moved accounts wrote two.
  So every bot's files are read and rows are kept by their own `account` field, never by which
  folder they sat in, then de-duplicated by deal ticket.
- 🔴 **No file is "not written", never "no deals"** (repo rule 1). An account with nothing on
  record answers `status = "no_history"`, and nothing below it is a number.
- 🔴 **A deposit is not a return.** BALANCE and BONUS deals are money in or out; they are drawn as
  markers and kept out of every trade and every P&L figure. CREDIT is skipped entirely. The split
  is the one `algos/shared/account_flows.py` uses, repeated here because this app may not import
  `algos/` — `FLOW_TYPES` and `DEAL_CREDIT` must stay equal to its values.
- ⚠ **Deal times are on the broker SERVER's clock** and are converted with `broker_clock`.
- ⚠ **The original stop and the targets are not in a deal.** They come from the bots' own
  `trade / opened` records, matched on the position ticket (the bot records MT5's position ticket,
  and MT5 books every deal of that position under the same `position_id` — `algos/shared/
  mt5_ops.py` filters on exactly that). A target of 0.0 there means NO target. A position no bot
  opened is a manual trade: no stop, so its R is `None`, never 0.
- ⚠ **The worst and best price a trade saw come from the same bar cache the backtest chart reads,
  on 1-minute bars that lie wholly INSIDE the trade**, plus its own fills. A minute bar straddling
  the entry or the exit also holds prices from outside the trade, so it is left out — the measure
  can understate by those few seconds, and can never reach past the exit.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from config import MONOREPO_ROOT

from services import broker_clock

log = logging.getLogger("ACCOUNT_HISTORY")

ARCHIVE = MONOREPO_ROOT / "algos" / "ledger_archive"

# MetaTrader5's own deal constants — the same values `algos/shared/account_flows.py` reads.
DEAL_BUY = 0
DEAL_SELL = 1
DEAL_BALANCE = 2
DEAL_CREDIT = 3
DEAL_BONUS = 6
FLOW_TYPES = frozenset({DEAL_BALANCE, DEAL_BONUS})
TRADE_TYPES = frozenset({DEAL_BUY, DEAL_SELL})

ENTRY_IN = 0
ENTRY_OUT = 1
ENTRY_INOUT = 2
ENTRY_OUT_BY = 3

RECONCILE_TOLERANCE = 0.01

# How far a bot's "opened" record may sit from the entry deal's converted time and still be the
# same trade. The bot writes it within a poll of the fill; a wider gap means a ticket reused on
# another server, or a clock read wrongly — either way the stop is not this trade's.
OPEN_MATCH_WINDOW_MS = 6 * 60 * 60 * 1000

# The chart's own bars. M15 is what the slower bot trades; the panel drills to M5 and M1 live.
CHART_TIMEFRAME = "M15"
CHART_PAD_MS = 2 * 24 * 60 * 60 * 1000


class BoxUnreachable(Exception):
    """The box could not be asked. Raised by the caller's fetcher; read as *fall back*, never *empty*."""


# ── Reading the record ──────────────────────────────────────────────────────────────────────


# The marker the box command echoes FIRST. Its presence is what proves the box answered — a
# command that found no files prints nothing else, and "answered, nothing there" must not read the
# same as "could not ask".
BOX_MARKER = "===ACCOUNT_HISTORY==="


def box_command(instance_dirs: Iterable[str]) -> str:
    """One cmd line that prints every bot's deal rows and its trade-opened rows.

    ⚠ `findstr` with an unquoted token, for the reason `routers/bots.py` gives for the snapshot's
    ledger read: a pattern with no spaces or quotes survives the local shell and cmd unmangled.
    Every deal row carries `position_id`; every opened row carries `opened`. The parser decides
    what each line is — the token only keeps the transfer small.
    """
    parts = [f"echo {BOX_MARKER}"]
    for d in instance_dirs:
        parts.append(rf"findstr /c:position_id {d}\ledger\deals-*.jsonl 2>nul")
        parts.append(rf"findstr /c:opened {d}\ledger\decisions-*.jsonl 2>nul")
        parts.append(
            rf"findstr /c:counts_as_strategy_performance {d}\ledger\decisions-*.jsonl 2>nul"
        )
    return " & ".join(parts)


def parse_rows(raw: str) -> tuple[list[dict], list[dict]]:
    """(deal rows, trade-opened rows) out of any text holding one JSON row per line.

    `findstr` over several files prefixes each hit with its path, and a Windows path holds a
    colon, so a row is found by its opening brace. A torn or foreign line is skipped.
    """
    deals: list[dict] = []
    opens: list[dict] = []
    for line in raw.splitlines():
        brace = line.find("{")
        if brace < 0:
            continue
        try:
            row = json.loads(line[brace:])
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("kind") == "deal":
            deals.append(row)
        elif row.get("kind") == "trade" and row.get("event") == "opened":
            opens.append(row)
        elif row.get("counts_as_strategy_performance") is False:
            # A trade the record says is NOT the strategy's (a duplicate-order incident, a hand
            # mark). Carried with the opened rows; `attach_plans` reads it by ticket.
            opens.append(row)
    return deals, opens


def read_archive(root: Path = ARCHIVE) -> tuple[list[dict], list[dict], bool]:
    """(deal rows, opened rows, whether ANY deal file exists) from this machine's git archive."""
    deals: list[dict] = []
    opens: list[dict] = []
    any_file = False
    if not root.is_dir():
        return deals, opens, False
    for f in sorted(root.glob("*/ledger/deals-*.jsonl")):
        any_file = True
        try:
            d, _ = parse_rows(f.read_text(errors="replace"))
        except OSError:
            continue
        deals.extend(d)
    for f in sorted(root.glob("*/ledger/decisions-*.jsonl")):
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        # The cheap reject first — a decisions file is almost all bar rows.
        lines = "\n".join(
            line
            for line in text.splitlines()
            if '"opened"' in line or "counts_as_strategy_performance" in line
        )
        _, o = parse_rows(lines)
        opens.extend(o)
    return deals, opens, any_file


def _int(v) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return None
    return None


def _float(v) -> float:
    if isinstance(v, bool) or v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def account_deals(rows: Iterable[dict], account: int) -> list[dict]:
    """The rows read ON this account, one per deal ticket, in booking order.

    ⚠ Filtered by the row's own `account`, never by the folder it came from — a bot that moved
    wrote both accounts' histories. ⚠ De-duplicated by TICKET: every bot on the account wrote the
    same deal. A row with no ticket cannot be told apart from a real second deal, so it is dropped
    rather than guessed at.
    """
    seen: dict[int, dict] = {}
    for r in rows:
        if _int(r.get("account")) != account:
            continue
        t = _int(r.get("ticket"))
        if t is None:
            continue
        seen.setdefault(t, r)
    return sorted(seen.values(), key=lambda r: (_server_ms(r), _int(r.get("ticket")) or 0))


def _server_ms(r: dict) -> int:
    ms = _int(r.get("time_msc")) or 0
    if ms:
        return ms
    return (_int(r.get("time")) or 0) * 1000


def deal_utc_ms(r: dict) -> int:
    """A deal's booking instant as true UTC epoch ms."""
    return broker_clock.server_ms_to_utc_ms(_server_ms(r))


def _money(r: dict) -> float:
    """What one deal did to the balance — `account_flows._money`'s four fields."""
    return sum(_float(r.get(k)) for k in ("profit", "commission", "swap", "fee"))


# ── The positions, the flows and the balance ────────────────────────────────────────────────


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def build_book(deals: list[dict]) -> dict:
    """Rebuild the account from its deals: closed positions, money in and out, and the balance.

    `deals` must already be one account's, de-duplicated and in booking order (`account_deals`).
    Returns plain dicts; nothing here reads a file, a clock or a bar.
    """
    balance = 0.0
    capital = 0.0
    growth = 1.0
    period_start: Optional[float] = None
    twr_broken: Optional[str] = None

    positions: dict[int, dict] = {}
    closed: list[dict] = []
    flows: list[dict] = []
    adjustments: list[dict] = []
    credit_skipped = 0

    def twr_now(bal: float) -> Optional[float]:
        if twr_broken or period_start is None or period_start <= 0:
            return None
        return growth * (bal / period_start)

    for r in deals:
        kind = _int(r.get("type"))
        ms = deal_utc_ms(r)
        money = _money(r)
        if kind == DEAL_CREDIT:
            credit_skipped += 1
            continue
        if kind in FLOW_TYPES:
            # Close the period that just ended before the money moves — the time-weighted return.
            if period_start is not None and not twr_broken:
                if period_start > 0:
                    growth *= balance / period_start
                elif abs(balance - period_start) > RECONCILE_TOLERANCE:
                    twr_broken = "money was made or lost while the account held nothing"
            balance += money
            capital += money
            period_start = balance
            flows.append(
                {
                    "ticket": _int(r.get("ticket")),
                    "time_ms": ms,
                    "date": _iso(ms),
                    "amount": round(money, 2),
                    "balance_after": round(balance, 2),
                    "kind": "deposit" if money >= 0 else "withdrawal",
                    "comment": str(r.get("comment") or ""),
                }
            )
            continue

        balance += money
        if kind not in TRADE_TYPES:
            # A charge, interest, a correction — it moves the balance and is no trade.
            adjustments.append(
                {
                    "ticket": _int(r.get("ticket")),
                    "time_ms": ms,
                    "amount": round(money, 2),
                    "type": kind,
                }
            )
            continue

        pid = _int(r.get("position_id")) or _int(r.get("ticket"))
        entry = _int(r.get("entry"))
        vol = _float(r.get("volume"))
        price = _float(r.get("price"))
        pos = positions.get(pid)
        if pos is None:
            pos = positions[pid] = {
                "ticket": pid,
                "symbol": str(r.get("symbol") or ""),
                "dir": None,
                "ins": [],
                "outs": [],
                "money": 0.0,
                "costs": 0.0,
                "closed": False,
                "magic": _int(r.get("magic")),
                "comment": str(r.get("comment") or ""),
            }
        pos["money"] += money
        pos["costs"] += _float(r.get("commission")) + _float(r.get("swap")) + _float(r.get("fee"))
        if entry == ENTRY_IN:
            if pos["dir"] is None:
                pos["dir"] = "long" if kind == DEAL_BUY else "short"
            pos["ins"].append((ms, price, vol))
        else:
            # OUT, OUT_BY, and INOUT (which a hedging account never books) all take volume off.
            pos["outs"].append((ms, price, vol, _money(r), _int(r.get("reason"))))
        in_vol = sum(v for _, _, v in pos["ins"])
        out_vol = sum(v for _, _, v, _, _ in pos["outs"])
        if not pos["closed"] and pos["ins"] and out_vol >= in_vol - 1e-9 and out_vol > 0:
            pos["closed"] = True
            closed.append(_closed_position(pos, balance, twr_now(balance)))

    open_positions = [p for p in positions.values() if not p["closed"] and p["ins"]]
    open_costs = sum(p["money"] for p in open_positions)
    trading = sum(p["pnl"] for p in closed)
    adj = sum(a["amount"] for a in adjustments)
    # 🔴 The reconcile: money in, plus what the closed trades made, plus everything else that moved
    # the balance, must BE the balance the deals rebuild. A deal counted twice or on the wrong side
    # of the split shows up here as a difference.
    rebuilt = capital + trading + adj + open_costs
    reconciled = abs(rebuilt - balance) <= RECONCILE_TOLERANCE

    final_twr = None
    if not twr_broken and period_start is not None and period_start > 0:
        final_twr = growth * (balance / period_start)

    return {
        "positions": closed,
        "flows": flows,
        "adjustments": adjustments,
        "open_positions": len(open_positions),
        "open_position_costs": round(open_costs, 2),
        "credit_deals_skipped": credit_skipped,
        "balance": round(balance, 2),
        "capital_in": round(capital, 2),
        "trading_pnl": round(trading, 2),
        "adjustments_total": round(adj, 2),
        "reconciled": reconciled,
        "twr_pct": round((final_twr - 1) * 100, 4) if final_twr is not None else None,
        "twr_reason": twr_broken
        or (
            None if flows else "no deposit is on record, so there is nothing to measure a return on"
        ),
    }


def _vwap(rows) -> Optional[float]:
    vol = sum(r[2] for r in rows)
    if vol <= 0:
        return None
    return sum(r[1] * r[2] for r in rows) / vol


def _closed_position(pos: dict, balance_after: float, twr_growth: Optional[float]) -> dict:
    ins, outs = pos["ins"], pos["outs"]
    return {
        "ticket": pos["ticket"],
        "symbol": pos["symbol"],
        "dir": pos["dir"],
        "entry_ms": ins[0][0],
        "entry_price": _vwap(ins),
        "volume": round(sum(v for _, _, v in ins), 4),
        "exit_ms": outs[-1][0],
        "exit_price": _vwap(outs),
        "fills": [
            {"time_ms": t, "price": p, "volume": v, "pnl": round(m, 2), "reason": rs}
            for t, p, v, m, rs in outs
        ],
        "pnl": round(pos["money"], 2),
        "costs": round(pos["costs"], 2),
        "balance_after": round(balance_after, 2),
        "twr_growth": twr_growth,
        "magic": pos["magic"],
        "comment": pos["comment"],
    }


# ── What the bots knew: stop, targets, risk ─────────────────────────────────────────────────


def _open_ms(row: dict) -> Optional[int]:
    ts = row.get("ts")
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _target(v) -> Optional[float]:
    """A recorded target, or None. ⚠ 0.0 is the bots' word for NO target, never a price."""
    f = _float(v)
    return f if f > 0 else None


def attach_plans(positions: list[dict], opens: Iterable[dict]) -> int:
    """Put each bot trade's original stop, targets, risk and owner on its position. Returns how
    many opened records named a ticket here but sat too far from its entry to be trusted.

    ⚠ A position with no match is left with `bot = None` — a manual trade, or one no record
    reached — and its stop and R stay `None`.
    """
    by_ticket: dict[int, list[dict]] = {}
    excluded: dict[int, str] = {}
    plans = []
    for o in opens:
        if o.get("counts_as_strategy_performance") is False:
            why = str(o.get("why") or "marked as not the strategy's trade")
            for t in [o.get("ticket"), *(o.get("tickets") or [])]:
                if _int(t) is not None:
                    excluded.setdefault(_int(t), why)
            continue
        plans.append(o)
    for o in plans:
        t = _int(o.get("ticket"))
        if t is not None:
            by_ticket.setdefault(t, []).append(o)
    mismatched = 0
    for p in positions:
        p.setdefault("bot", None)
        p.setdefault("stop", None)
        p.setdefault("targets", [])
        p.setdefault("risk_usd", None)
        # ⚠ Excluded from the STRATEGY's figures only — the money is real and stays in the balance.
        p["excluded"] = excluded.get(p["ticket"])
        cands = by_ticket.get(p["ticket"]) or []
        best = None
        best_gap = None
        for o in cands:
            at = _open_ms(o)
            if at is None:
                continue
            gap = abs(at - p["entry_ms"])
            if gap <= OPEN_MATCH_WINDOW_MS and (best_gap is None or gap < best_gap):
                best, best_gap = o, gap
        if best is None:
            if cands:
                mismatched += 1
            continue
        p["bot"] = str(best.get("bot") or "") or None
        stop = _float(best.get("stop"))
        p["stop"] = stop if stop > 0 else None
        p["targets"] = [
            t for t in (_target(best.get("tp1")), _target(best.get("tp2"))) if t is not None
        ]
        risk = best.get("risk_usd")
        p["risk_usd"] = float(risk) if isinstance(risk, (int, float)) and risk > 0 else None
    return mismatched


def r_multiple(p: dict, contract_size: Optional[float]) -> Optional[float]:
    """P&L over the risk the trade was placed with — `None` when that risk is not on record.

    The bot's own `risk_usd` is preferred: it was measured off the fill and the stop that was
    attached. Otherwise |entry − stop| × volume × contract size. No stop ⇒ `None`, never 0.
    """
    risk = p.get("risk_usd")
    if not risk:
        stop = p.get("stop")
        if stop is None or not contract_size or p.get("entry_price") is None:
            return None
        risk = abs(p["entry_price"] - stop) * p["volume"] * contract_size
    if not risk or risk <= 0:
        return None
    return p["pnl"] / risk


# ── Excursion off the bars ──────────────────────────────────────────────────────────────────

M1_MS = 60_000


def excursion(p: dict, m1: list[dict]) -> tuple[Optional[float], Optional[float]]:
    """(worst price, best price) the trade saw, or (None, None) with no bar inside it.

    Only 1-minute bars that open at or after the entry and CLOSE at or before the exit count, plus
    the trade's own entry and exit fills — so nothing after the exit can reach the figure.
    ⚠ `m1` must be sorted by time.
    """
    lo_t, hi_t = p["entry_ms"], p["exit_ms"]
    inside = [b for b in m1 if b["time"] >= lo_t and b["time"] + M1_MS <= hi_t]
    if not inside:
        return None, None
    prices_hi = [b["high"] for b in inside]
    prices_lo = [b["low"] for b in inside]
    fills = [p["entry_price"]] + [f["price"] for f in p["fills"]]
    hi = max(prices_hi + fills)
    lo = min(prices_lo + fills)
    if p["dir"] == "long":
        return lo, hi
    return hi, lo


# ── The answer ──────────────────────────────────────────────────────────────────────────────


def _trade_row(p: dict) -> dict:
    """The ChartTrade contract (`ChartPanel/types.ts`) — camelCase, epoch ms."""
    out: dict[str, Any] = {
        "id": str(p["ticket"]),
        "dir": p["dir"],
        "entryTime": p["entry_ms"],
        "entryPrice": p["entry_price"],
        "exitTime": p["exit_ms"],
        "exitPrice": p["exit_price"],
        "pnl": p["pnl"],
        "outcome": "won" if p["pnl"] > 0 else "lost" if p["pnl"] < 0 else "scratch",
        "tag": p.get("bot") or "Manual",
        # Every fill, banked or not — `exitPrice` is their average (see the chart notes).
        "profitLegs": [
            {
                "price": f["price"],
                "label": "Exit" if len(p["fills"]) == 1 else f"Exit {i + 1}",
                "banked": f["pnl"] > 0,
            }
            for i, f in enumerate(p["fills"])
        ],
    }
    if p.get("stop") is not None:
        out["stopPrice"] = p["stop"]
    if p.get("targets"):
        out["tpTargets"] = [{"price": t, "banks": True} for t in p["targets"]]
    if p.get("mae") is not None:
        out["maePrice"] = p["mae"]
    if p.get("mfe") is not None:
        out["mfePrice"] = p["mfe"]
    return out


def _equity_point(
    i: int, p: dict, r: Optional[float], contract_size: Optional[float], twr_scale: Optional[float]
) -> dict:
    fav = adv = None
    if contract_size and p.get("mfe") is not None and p.get("mae") is not None:
        sign = 1 if p["dir"] == "long" else -1
        units = p["volume"] * contract_size
        fav = max(0.0, (p["mfe"] - p["entry_price"]) * sign * units)
        adv = min(0.0, (p["mae"] - p["entry_price"]) * sign * units)
    return {
        "index": i + 1,
        "equity": p["balance_after"],
        "date": _iso(p["exit_ms"]),
        "entry_ms": p["entry_ms"],
        "exit_ms": p["exit_ms"],
        "direction": "Long" if p["dir"] == "long" else "Short",
        "profit": p["pnl"],
        "exit_name": "Excluded" if p.get("excluded") else (p.get("bot") or "Manual"),
        "excluded": p.get("excluded"),
        "favorable": round(fav, 2) if fav is not None else None,
        "adverse": round(adv, 2) if adv is not None else None,
        "costs_usd": p["costs"],
        "r": round(r, 4) if r is not None else None,
        # Growth with every deposit and withdrawal taken out, on the balance's scale at trade one.
        "twr_equity": round(twr_scale * p["twr_growth"], 2)
        if twr_scale is not None and p.get("twr_growth") is not None
        else None,
    }


BarLoader = Callable[[str, str, str, str], tuple[list[dict], Optional[str], Optional[str]]]


def _span_dates(lo_ms: int, hi_ms: int) -> tuple[str, str]:
    return (
        datetime.fromtimestamp(lo_ms / 1000, tz=timezone.utc).date().isoformat(),
        datetime.fromtimestamp(hi_ms / 1000, tz=timezone.utc).date().isoformat(),
    )


def build_history(
    account: int,
    *,
    box: Optional[tuple[list[dict], list[dict]]],
    box_error: Optional[str],
    archive: tuple[list[dict], list[dict], bool],
    contract_size: Optional[float],
    load_bars: Optional[BarLoader],
    now_ms: Optional[int] = None,
    load_bars_key: Optional[str] = None,
    refresh_bars: bool = False,
) -> dict:
    """The whole answer for one account. Pure apart from `load_bars`, which the caller supplies.

    `box` is `(deal rows, opened rows)` when the box answered and `None` when it could not be
    asked (`box_error` says why). `archive` is `read_archive()`'s answer.
    """
    arch_deals, arch_opens, _ = archive
    source = None
    note = None
    deals: list[dict] = []
    if box is not None:
        deals = account_deals(box[0], account)
        if deals:
            source = "box"
        else:
            note = "The trading box holds no deal history for this account"
    else:
        note = f"The trading box could not be reached ({box_error or 'no reason given'})"
    if not deals:
        deals = account_deals(arch_deals, account)
        if deals:
            source = "archive"
            note = f"{note} — showing the git backup instead."

    base = {
        "account": account,
        "source": source,
        "source_note": note if source != "box" else None,
        "box_error": box_error,
        "read_at_ms": now_ms if now_ms is not None else int(time.time() * 1000),
    }
    if not deals:
        return {
            **base,
            "status": "no_history",
            "reason": (
                f"{note}, and the git backup holds none either. No bot has written this account's "
                "deal history yet — it starts once a bot on it runs the version that records it."
            ),
        }

    book = build_book(deals)
    opens = list((box or ([], []))[1]) + list(arch_opens)
    mismatched = attach_plans(book["positions"], opens)
    positions = book["positions"]
    newest = max(deal_utc_ms(d) for d in deals)

    # Bars: the chart's own frame over the whole history, and minute bars across the trades.
    bars_note = None
    bars_server = None
    candles: list[dict] = []
    if load_bars is not None:
        symbols = sorted({p["symbol"] for p in positions if p["symbol"]})
        symbol = symbols[0] if symbols else None
        if len(symbols) > 1:
            bars_note = f"Trades on {len(symbols)} symbols; the chart shows {symbol} only."
        if symbol and positions:
            lo = min(p["entry_ms"] for p in positions)
            hi = max(p["exit_ms"] for p in positions)
            ours = [p for p in positions if p["symbol"] == symbol]
            key = (
                symbol,
                load_bars_key,
                tuple((p["ticket"], p["entry_ms"], p["exit_ms"]) for p in ours),
            )
            hit = None if refresh_bars else _bars_memo_get(key)
            if hit is not None:
                candles, bars_note_b, bars_server, excursions = hit
                bars_note = bars_note or bars_note_b
            else:
                start, end = _span_dates(lo - CHART_PAD_MS, hi + CHART_PAD_MS)
                candles, err, bars_server = load_bars(symbol, CHART_TIMEFRAME, start, end)
                bars_note_b = err
                m1_start, m1_end = _span_dates(lo, hi)
                m1, m1_err, _ = load_bars(symbol, "M1", m1_start, m1_end)
                bars_note_b = bars_note_b or m1_err
                excursions = {p["ticket"]: excursion(p, m1) for p in ours}
                bars_note = bars_note or bars_note_b
                # Only an answer that SERVED bars is remembered (a fallback server's included — its
                # note travels with it); an empty one is a feed failure and the next open retries.
                if candles and m1:
                    reaches_now = hi + CHART_PAD_MS >= (now_ms or int(time.time() * 1000))
                    _bars_memo_put(
                        key, (candles, bars_note_b, bars_server, excursions), reaches_now
                    )
            for p in ours:
                p["mae"], p["mfe"] = excursions.get(p["ticket"], (None, None))

    opening = book["flows"][0]["balance_after"] if book["flows"] else None
    # The growth line is drawn on the balance's own scale AT THE FIRST TRADE, so both lines leave the
    # same point. Scaling on the opening deposit drew the live account's line at $470 beside a
    # $10,733 balance, because the first transfer in was $451.97 and trading began on $10,311.48.
    first = positions[0] if positions else None
    g1 = first.get("twr_growth") if first else None
    twr_scale = first["balance_after"] / g1 if g1 else None
    rs = [r_multiple(p, contract_size) for p in positions]
    equity = [
        _equity_point(i, p, r, contract_size, twr_scale)
        for i, (p, r) in enumerate(zip(positions, rs))
    ]
    trades = [_trade_row(p) for p in positions]
    chart_symbol = next((p["symbol"] for p in positions if p["symbol"]), "")
    chart = {
        "instrument": chart_symbol,
        "baseTimeframe": CHART_TIMEFRAME,
        "runTimeframe": CHART_TIMEFRAME,
        "historyStartMs": candles[0]["time"] if candles else None,
        "brokerGmtOffsetHours": 0,
        "candles": candles,
        "sessions": [],
        "trades": [t for t, p in zip(trades, positions) if p["symbol"] == chart_symbol],
        "overlays": [],
        "indicators": [],
    }
    return {
        **base,
        "status": "ok",
        "reason": None,
        "newest_deal_ms": newest,
        "deal_count": len(deals),
        "balance": book["balance"],
        "capital_in": book["capital_in"],
        "trading_pnl": book["trading_pnl"],
        "adjustments_total": book["adjustments_total"],
        "open_positions": book["open_positions"],
        "open_position_costs": book["open_position_costs"],
        "reconciled": book["reconciled"],
        "twr_pct": book["twr_pct"],
        "twr_reason": book["twr_reason"],
        "opening_balance": opening,
        "flows": book["flows"],
        "equity": equity,
        "manual_trades": sum(1 for p in positions if not p.get("bot") and not p.get("excluded")),
        "excluded_trades": sum(1 for p in positions if p.get("excluded")),
        "excluded_pnl": round(sum(p["pnl"] for p in positions if p.get("excluded")), 2),
        "unmatched_plans": mismatched,
        "bars_server": bars_server,
        "bars_note": bars_note,
        "chart": chart,
    }


# ── Wiring: the real sources ────────────────────────────────────────────────────────────────


def bar_loader(server: Optional[str]) -> BarLoader:
    """Bars from the backtest's own cache, pinned to the account's server when one is recorded.

    ⚠ When the account's own server cannot serve the window (nothing cached and its terminal not
    attached) the bars come from whichever terminal IS attached, and the answer names that server
    — a live account's trades drawn on demo bars is a different feed and must say so.
    """
    from services import ohlc_fetcher

    def load(symbol: str, tf: str, start: str, end: str):
        tries = [server, None] if server else [None]
        last_err = None
        for srv in tries:
            try:
                df = ohlc_fetcher._get_ohlc_backtest_cache(symbol, start, end, tf, srv)
            except Exception as exc:  # noqa: BLE001 — a feed failure is reported, never fatal
                last_err = f"{type(exc).__name__}: {exc}"[:300]
                continue
            times = df.index.as_unit("ms").astype("int64").tolist()
            rows = [
                {"time": t, "open": o, "high": h, "low": lo, "close": c}
                for t, o, h, lo, c in zip(
                    times,
                    df["open"].astype(float).tolist(),
                    df["high"].astype(float).tolist(),
                    df["low"].astype(float).tolist(),
                    df["close"].astype(float).tolist(),
                )
            ]
            served = srv or "the attached terminal"
            note = None
            if server and srv != server:
                note = f"{server} bars were unavailable ({last_err}); bars are from {served}."
            return rows, note, served
        return [], f"No bars for {symbol} {tf}: {last_err}", None

    return load


# One answer per account, kept briefly: the box read is an SSH round trip and the minute bars a
# multi-second file read, and the page asks again on every focus.
_CACHE_TTL_S = 60
_cache: dict[int, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


# 🔴 The bars are the slow half of an account page (measured 2026-09-17: 42s of a 51s open), because
# a window reaching today makes the backtest bar store fetch the newest bars and rewrite its whole
# file, twice. They depend only on WHICH trades there are, so they are remembered per trade set and
# recomputed when a trade opens or closes, or on Refresh. A window still reaching into the present
# is remembered for `_BARS_LIVE_TTL_S` only, so the chart's right edge keeps moving.
_BARS_LIVE_TTL_S = 15 * 60
_BARS_MEMO_MAX = 16
_bars_memo: dict = {}


def _bars_memo_get(key):
    with _cache_lock:
        hit = _bars_memo.get(key)
    if hit is None:
        return None
    expires, value = hit
    if expires is not None and time.monotonic() > expires:
        return None
    return value


def _bars_memo_put(key, value, reaches_now: bool) -> None:
    expires = time.monotonic() + _BARS_LIVE_TTL_S if reaches_now else None
    with _cache_lock:
        if key not in _bars_memo and len(_bars_memo) >= _BARS_MEMO_MAX:
            _bars_memo.pop(next(iter(_bars_memo)))
        _bars_memo[key] = (expires, value)


def cached(account: int, build: Callable[[], dict], refresh: bool = False) -> dict:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(account)
        if hit and not refresh and now - hit[0] < _CACHE_TTL_S:
            return hit[1]
    out = build()
    with _cache_lock:
        _cache[account] = (now, out)
    return out


def candles_window(load_bars: BarLoader, symbol: str, tf: str, from_ms: int, to_ms: int) -> dict:
    """One drill-down window — the ChartPage shape `routers/backtests.py` serves for a run."""
    if from_ms > to_ms:
        from_ms, to_ms = to_ms, from_ms
    start, end = _span_dates(from_ms, to_ms)
    rows, err, _ = load_bars(symbol, tf.upper(), start, end)
    rows = [c for c in rows if from_ms <= c["time"] <= to_ms]
    # Could the feed be ASKED — an empty list with no error is the feed answering "nothing here".
    available = err is None or bool(rows)
    return {
        "instrument": symbol,
        "timeframe": tf.upper(),
        "candles": rows,
        "available": available,
        "feed_error": err if not available else None,
        "data_start_ms": rows[0]["time"] if rows else None,
        "hard_edge": False,
        "overlays": [],
    }
