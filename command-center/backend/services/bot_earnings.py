"""What each bot actually MADE, read off its own decision record.

🔴 **This exists because the only P&L figure this app had was a fact about the ACCOUNT wearing a
bot's name.** `total_pnl_pct` is `(balance - starting_balance) / starting_balance`, and `balance` is
the ACCOUNT's — so on a stacked account every bot reports the same number, and that number counts
every dollar the account made whether a bot made it or not. Aaron, 2026-09-05: *"how much percent
each bot made on the account thus far … that 45% increase was only from the SOS Fade. That should
still be showing zero percent from the extreme leg."*

**The one honest source is each bot's own ledger**, `algos/ledger_archive/<bot>/ledger/
decisions-*.jsonl`, where a closed trade carries its realised `pnl_usd` and `r`. That is a record
of what THIS bot did, so summing it cannot pick up a neighbour's trade, a manual fill, or a deposit.

⚠ **It is the repo's compare-R-never-dollars rule in a new place.** Two bots on one balance SHARE
the account's growth, so the account's growth may not be split between them by any arithmetic —
each is asked what it did, separately, and whatever the account did beyond that is named rather
than divided up.

🔴 **The sum will NOT reconcile to the account, and the gap is the finding rather than a bug.**
MEASURED on the live PU Prime ECN demo 700152905, 2026-09-05: the account is up **$4,541.89** from
its $9,996.99 opening, of which SOS Fade's two closed trades are **$1,197.09** and the extreme leg
has closed none. **$3,344.80 came from something no bot here recorded.** A page that silently
credited the bots with 45% would be stating that as a strategy result. `unattributed_usd` is
therefore reported, always, and is not an error path.

⚠ **A bot with no ledger reads `traded: False`, never zero trades.** *Never traded* and *no record
to read* are different answers and only one of them is a measurement — the repo's rule 1, and the
whole reason a fresh bot's row may not print a confident `0.0%` under the same styling as a bot
that genuinely broke even.

⚠ **It reads the ARCHIVE on this machine, not the box.** `algos/tools/ledger_sync.py` commits and
pushes the record hourly, so this needs no SSH, works with the VPS down, and is the same bytes both
machines hold. The cost is LAG: the archive is up to an hour behind, and `records_to` says how far
it actually reaches so a reader can see that for themselves rather than assuming today.
"""

from __future__ import annotations

import json
from pathlib import Path

from config import MONOREPO_ROOT

# One folder per bot, named by BOT KEY — which is why the 2026-09-03 rename had to move the
# folder and could leave every record inside it untouched (see the archive's own RENAMED.md).
ARCHIVE = MONOREPO_ROOT / "algos" / "ledger_archive"


class BotLedgerSummary(dict):
    """A plain dict — the router builds the response model. Kept as a type name for readers."""


def _closed_trades(path: Path) -> list[dict]:
    """Every closed-trade row in one ledger file.

    ⚠ A malformed line is SKIPPED, never fatal. This file is appended to by a live bot and read
    while it is being written; one torn line at the end must not blank a month of history.
    """
    out: list[dict] = []
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        # Cheap reject before the parse — a ledger is ~99% bar rows and only a handful of
        # trades, so parsing every line would be the whole cost of this endpoint.
        #
        # 🔴 **It rejects on the KIND only, never on the event.** Filtering `"closed"` here too
        # was faster and made the structured test below INERT: a mutation deleting that test
        # changed nothing, so the test covering it passed against its own defect. A substring
        # is also the wrong instrument for the question — `"closed"` appears in an exit reason
        # as readily as in the event — so the string does the cheap half and the parsed fields
        # decide.
        #
        # ⚠ **It cost nothing, and the reason is worth knowing before anyone "optimises" it
        # back.** MEASURED on the live record, 61 files / 2,872 lines: exactly **4** lines reach
        # the parser either way, because a blocked, missed or bar row carries no `"kind":
        # "trade"` at all — the dropped `"closed"` clause was never rejecting anything. Read is
        # **4.7–5.4ms** with the files in the OS cache (three passes) and **19.6ms** on the
        # first read of a cold disk. Quote the cold figure when sizing this, not the warm one.
        if not line or '"kind": "trade"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("kind") == "trade" and row.get("event") == "closed":
            out.append(row)
    return out


# Keyed on a FINGERPRINT of the record rather than on time: how many files there are, and the
# newest one's name, size and mtime. A live bot appends to today's file, so its size moves and the
# cache turns over on its own — there is no interval to be stale inside of. MEASURED at 19.6ms for
# 61 files, which is nothing beside the snapshot's SSH; the cache is here because the archive grows
# by a file a day and a per-poll rescan is the fan-out shape this repo has already paid for once.
_ledger_cache: dict[str, tuple[tuple, dict]] = {}


def _fingerprint(files: list[Path]) -> tuple:
    newest = files[-1]
    try:
        st = newest.stat()
    except OSError:
        return (len(files), newest.name, -1, -1.0)
    return (len(files), newest.name, st.st_size, st.st_mtime)


def read_bot_ledger(bot_key: str) -> dict:
    """Sum one bot's realised results out of its own archived decision record.

    Returns `traded: False` with everything else `None` when there is no record — see the module
    docstring on why that may not collapse to zero.
    """
    folder = ARCHIVE / bot_key / "ledger"
    files = sorted(folder.glob("decisions-*.jsonl")) if folder.is_dir() else []
    if files:
        fp = _fingerprint(files)
        hit = _ledger_cache.get(bot_key)
        if hit and hit[0] == fp:
            return dict(hit[1])
    if not files:
        return {
            "bot_key": bot_key,
            "traded": False,
            "reason": "No decision record has reached this machine for this bot yet.",
            "closed_trades": None,
            "realised_usd": None,
            "realised_r": None,
            "wins": None,
            "losses": None,
            "records_from": None,
            "records_to": None,
        }

    rows: list[dict] = []
    for f in files:
        rows.extend(_closed_trades(f))

    usd = 0.0
    r = 0.0
    wins = 0
    losses = 0
    for row in rows:
        p = row.get("pnl_usd")
        if isinstance(p, (int, float)):
            usd += float(p)
            # A scratch counts as neither. The repo already refuses to call a breakeven exit a
            # win on the backtest side, and doing it differently here would put two definitions
            # of "won" in one app.
            if p > 0:
                wins += 1
            elif p < 0:
                losses += 1
        rr = row.get("r")
        if isinstance(rr, (int, float)):
            r += float(rr)

    # The SPAN OF THE RECORD, not of the trades — "nothing closed" and "nothing recorded" have
    # to look different, and the first date is what makes a bot's tenure on an account readable.
    result = {
        "bot_key": bot_key,
        "traded": True,
        "reason": None,
        "closed_trades": len(rows),
        "realised_usd": round(usd, 2),
        "realised_r": round(r, 4),
        "wins": wins,
        "losses": losses,
        "records_from": files[0].name[len("decisions-") : -len(".jsonl")],
        "records_to": files[-1].name[len("decisions-") : -len(".jsonl")],
    }
    _ledger_cache[bot_key] = (fp, dict(result))
    return result


# ── The account half ────────────────────────────────────────────────────────────────────────
#
# 🔴 **An account's OPENING balance is not any one bot's anchor, and picking the wrong one is
# silent.** Each bot anchors what the account held when IT arrived, so a bot that joined a grown
# account states a much higher number and both are correct. The account's own opening is the
# anchor of whichever bot has been here longest — ordered by the first day each bot wrote a
# record, because that is the only arrival evidence this app holds.
#
# ⚠ **A bot with NO record can never be chosen while a bot with one exists.** It might genuinely
# be the older tenant, and there is no way to show that — so the pick names the bot it came from
# and the page prints that name, rather than the reader having to trust an unexplained figure.


def _pick_opening(rows: list[dict]) -> tuple[float | None, str | None, str | None]:
    """(opening balance, the bot key it came from, why it could not be stated)."""
    have = [r for r in rows if r.get("starting_balance") is not None]
    if not have:
        return (
            None,
            None,
            "No bot here has connected to the account yet, so nothing recorded what it opened at.",
        )

    distinct = {round(float(r["starting_balance"]), 2) for r in have}
    if len(distinct) == 1:
        return round(float(have[0]["starting_balance"]), 2), have[0]["bot_key"], None

    # They disagree, which is the NORMAL state of a stack: each bot arrived at a different time.
    dated = [r for r in have if r.get("records_from")]
    if not dated:
        return (
            None,
            None,
            "The bots here state different opening balances and none has a record old enough to say which arrived first.",
        )
    oldest = min(dated, key=lambda r: r["records_from"])
    return round(float(oldest["starting_balance"]), 2), oldest["bot_key"], None


def account_earnings(bots: list[dict]) -> list[dict]:
    """Group bots by account and answer both halves: what the account did, and what each bot did.

    `bots` is one dict per bot carrying `bot_key`, `name`, `account`, `balance` and
    `starting_balance` — read off the snapshot that has already been fetched, so this adds no SSH.
    """
    by_account: dict[int, list[dict]] = {}
    for b in bots:
        acct = b.get("account")
        if not acct:
            continue
        by_account.setdefault(int(acct), []).append(b)

    out: list[dict] = []
    for account, rows in sorted(by_account.items()):
        merged = [{**r, **read_bot_ledger(r["bot_key"])} for r in rows]

        # One pot of money, not one each — the same rule the page's own header learned on
        # 2026-09-04 after a two-bot stack reported an account's balance twice.
        balance = next((r["balance"] for r in merged if r.get("balance") is not None), None)
        opening, opening_from, opening_note = _pick_opening(merged)

        net_usd = net_pct = None
        if balance is not None and opening:
            net_usd = round(balance - opening, 2)
            net_pct = round((balance - opening) / opening * 100, 2)

        traded = [r for r in merged if r.get("traded")]
        silent = [r["bot_key"] for r in merged if not r.get("traded")]
        attributed = round(sum(r["realised_usd"] or 0.0 for r in traded), 2) if traded else None

        unattributed = None
        if net_usd is not None and attributed is not None:
            unattributed = round(net_usd - attributed, 2)

        out.append(
            {
                "account": account,
                "balance": balance,
                "opening_balance": opening,
                "opening_from": opening_from,
                "opening_note": opening_note,
                "net_usd": net_usd,
                "net_pct": net_pct,
                "attributed_usd": attributed,
                "unattributed_usd": unattributed,
                # Named, never silently folded into the unattributed figure: a bot whose record
                # has not arrived may have traded, so the split below is a FLOOR while this is
                # non-empty and the page has to be able to say so.
                "bots_without_record": silent,
                "bots": [
                    {
                        "bot_key": r["bot_key"],
                        "name": r.get("name") or r["bot_key"],
                        "traded": bool(r.get("traded")),
                        "reason": r.get("reason"),
                        "closed_trades": r.get("closed_trades"),
                        "realised_usd": r.get("realised_usd"),
                        "realised_r": r.get("realised_r"),
                        "wins": r.get("wins"),
                        "losses": r.get("losses"),
                        "records_from": r.get("records_from"),
                        "records_to": r.get("records_to"),
                        # The number Aaron asked for: what this bot made, as a share of what the
                        # ACCOUNT opened at — so two bots on one balance are directly comparable
                        # and neither is credited with the other's growth.
                        "pct_of_opening": (
                            round((r["realised_usd"] or 0.0) / opening * 100, 2)
                            if opening and r.get("traded")
                            else None
                        ),
                    }
                    for r in merged
                ],
            }
        )
    return out
