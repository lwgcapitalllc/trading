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

⚠ **It reads the ARCHIVE on this machine as its BASE.** `algos/tools/ledger_sync.py` commits and
pushes the record hourly from the box, so the base needs no SSH, works with the VPS down, and is
the same bytes both machines hold.

🔴 **THE ARCHIVE ALONE WAS THE DEFECT, AND THE COST WAS THAT A STALE READ LOOKED IDENTICAL TO A
REAL ATTRIBUTION GAP (2026-09-09).** The balance this sum is subtracted from is read live over SSH
and is seconds old. The archive is behind by however long ago the box last COMMITTED *and* this
machine last PULLED — **MEASURED at 66 minutes on 2026-09-09**, with no upper bound at all, because
nothing on this machine pulls on a schedule. A trade closed inside that window is already in the
balance and in no bot's row, so the bot under-reports by exactly its profit and the remainder line
over-reports by the same amount. It happened for real: the extreme leg's **$1,305.58** target
rendered as *"a manual fill, a deposit, or a trade older than the record"* — three real causes, none
of them true. **Two halves of one subtraction may not be read off two different clocks.**

✅ **Fixed by reading the box's OWN ledger in the same SSH the balances come from** (see
`routers/bots.py` → `_parse_live_trades`) and merging it over the archive, deduped by ticket. The
box answers with a couple of KB — trade rows only, and MEASURED at **6 rows / 3.1 KB for the whole
of both bots' history** — so freshness costs no round trip and no meaningful payload.

⚠ **The archive stays the base rather than being replaced, and the box is a TOP-UP.** The live
window is bounded by month, so it cannot reach an older trade; the archive cannot reach a newer one.
Each holds what the other cannot, which is why the union is taken rather than the fresher source
preferred.

⚠ **When the box cannot answer, the page SAYS the split is provisional** rather than printing a
confident one — `records_live`, the measured lag, and a sentence. That is the half that survives a
dead VPS, and it is the half that makes the four causes of a remainder distinguishable.

🔴 **A TRADE BELONGS TO THE ACCOUNT IT WAS MADE ON, NEVER TO THE ONE THE BOT IS ON NOW (2026-09-11).**
The sum above was every closed trade in a bot's record, credited to whatever account the bot named
today — so the moment a demo set went live, the live account showed the bots' DEMO trades as its
own (+264% on a $451.97 account that had not traded). A trade row names no account, but every run
starts with a `startup` record that does (in `health-*.jsonl` since 2026-08-05, `decisions-*.jsonl`
before), so a trade is placed on the account of the latest startup at or before it. ⚠ **An account a
bot has LEFT keeps that bot's trades**, as a history entry marked `former` — the demo record a set
was promoted on is the evidence for the promotion, and the demo-vs-live comparison needs it on
screen. ⚠ **A trade no startup precedes is COUNTED as unplaced**, never credited to a guess.
"""

from __future__ import annotations

import bisect
import json
from datetime import datetime, timezone
from pathlib import Path

from config import MONOREPO_ROOT

# One folder per bot, named by BOT KEY — which is why the 2026-09-03 rename had to move the
# folder and could leave every record inside it untouched (see the archive's own RENAMED.md).
ARCHIVE = MONOREPO_ROOT / "algos" / "ledger_archive"


class BotLedgerSummary(dict):
    """A plain dict — the router builds the response model. Kept as a type name for readers."""


def _newest_ts(lines: list[str]) -> str | None:
    """When the newest record in this file was written — `None` when it cannot be told.

    🔴 **This is the file's REACH, and it is the half that was missing.** The summary below
    reported `records_to` as a DAY, taken from the filename — so today's file always read as
    *"recorded through today"* while the newest line inside it could be an hour old. That is this
    repo's rule 3 in a new place: **the day is what was REQUESTED of the archive, the timestamp is
    what actually arrived**, and printing the first as though it were the second is what let a
    stale read look exactly like a real attribution gap.

    ⚠ **It walks BACKWARDS from the end and stops at the first line that parses**, bounded to the
    last 20. A live bot is appending to this file while it is read, so the final line is routinely
    torn; walking the whole file to find the newest timestamp would cost the whole read this
    module exists to keep cheap.

    ⚠ **`None` when no line in that tail parses — never a fabricated instant.** *We cannot tell
    how fresh this is* and *this is fresh* must not be the same value: the caller reports the
    first as an unknown lag, which is the thing a reader needs to see.
    """
    for line in reversed(lines[-20:]):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        ts = row.get("ts")
        if isinstance(ts, str) and ts:
            return ts
    return None


def _startup(row: dict) -> tuple[str, int] | None:
    """`(ts, account)` when this row is a run's startup naming its account, else `None`."""
    if row.get("event") != "startup":
        return None
    ts, account = row.get("ts"), row.get("account")
    if isinstance(ts, str) and ts and isinstance(account, int) and not isinstance(account, bool):
        return ts, account
    return None


def _startups(path: Path) -> list[tuple[str, int]]:
    """Every startup in one record file. A malformed line is skipped, same rule as trades."""
    out: list[tuple[str, int]] = []
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        # The token alone, like the trade filter below: the parsed fields decide.
        if '"startup"' not in line:
            continue
        try:
            found = _startup(json.loads(line))
        except ValueError:
            continue
        if found:
            out.append(found)
    return out


def _closed_trades(path: Path) -> tuple[list[dict], str | None]:
    """Every closed-trade row in one ledger file, and when its newest record was written.

    ⚠ A malformed line is SKIPPED, never fatal. This file is appended to by a live bot and read
    while it is being written; one torn line at the end must not blank a month of history.

    ⚠ **The reach comes back even when there are no trades in the file**, which is the normal
    case — a day of bar rows still tells you how far the record has got, and that is exactly the
    day a reader is asking about.
    """
    out: list[dict] = []
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return out, None
    lines = text.splitlines()
    for line in lines:
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
    return out, _newest_ts(lines)


# Keyed on a FINGERPRINT of the record rather than on time: how many files there are, and the
# newest one's name, size and mtime. A live bot appends to today's file, so its size moves and the
# cache turns over on its own — there is no interval to be stale inside of. MEASURED at 19.6ms for
# 61 files, which is nothing beside the snapshot's SSH; the cache is here because the archive grows
# by a file a day and a per-poll rescan is the fan-out shape this repo has already paid for once.
_ledger_cache: dict[str, tuple[tuple, dict]] = {}


def _fingerprint(files: list[Path]) -> tuple:
    if not files:
        return (0,)
    newest = files[-1]
    try:
        st = newest.stat()
    except OSError:
        return (len(files), newest.name, -1, -1.0)
    return (len(files), newest.name, st.st_size, st.st_mtime)


def _dedup_key(row: dict):
    """What makes two closed-trade rows the SAME trade.

    ⚠ **A ticket closes once**, so `(ticket, ts)` identifies a row across the two copies of it
    this module can now hold — the archived one and the one still only on the box. A row with no
    ticket falls back to its whole content, because guessing that two ticketless rows are the same
    trade is how a real second trade gets silently swallowed.
    """
    ticket = row.get("ticket")
    if ticket is not None:
        return ("t", ticket, row.get("ts"))
    return ("raw", json.dumps(row, sort_keys=True, default=str))


def _archive_scan(bot_key: str):
    """Everything this machine's archive holds for one bot, or `None` when it holds nothing.

    Returns `(closed rows, reach, first day, last day, startups)`. `reach` is the newest record's
    timestamp — see `_newest_ts` — and is `None` when it could not be read. `startups` is every
    `(ts, account)` a run began on, which is what places each trade on an account.

    ⚠ **Startups are read from BOTH record kinds**: the decision files carried them until
    2026-08-05 and the health files have since. Reading one kind would leave a month of trades
    with no account to belong to.
    """
    folder = ARCHIVE / bot_key / "ledger"
    files = sorted(folder.glob("decisions-*.jsonl")) if folder.is_dir() else []
    health = sorted(folder.glob("health-*.jsonl")) if folder.is_dir() else []
    if not files:
        return None

    # Both kinds, because a startup lands in the health file while no trade touches the other.
    fp = (_fingerprint(files), _fingerprint(health))
    hit = _ledger_cache.get(bot_key)
    if hit and hit[0] == fp:
        rows, reach, first, last, starts = hit[1]
        return [dict(r) for r in rows], reach, first, last, list(starts)

    rows: list[dict] = []
    starts: list[tuple[str, int]] = []
    reach: str | None = None
    for f in files:
        found, ts = _closed_trades(f)
        rows.extend(found)
        starts.extend(_startups(f))
        # The files are sorted by name and named by day, so the LAST one that could answer is
        # the newest. Taking the max would be wrong the moment a bot's clock or a filename
        # disagreed, and taking the last non-None keeps a torn final file from erasing the reach.
        if ts:
            reach = ts
    for f in health:
        starts.extend(_startups(f))
    first = files[0].name[len("decisions-") : -len(".jsonl")]
    last = files[-1].name[len("decisions-") : -len(".jsonl")]
    _ledger_cache[bot_key] = (fp, ([dict(r) for r in rows], reach, first, last, list(starts)))
    return rows, reach, first, last, starts


def _instant(ts) -> datetime | None:
    """A record's timestamp as an instant, or `None` when it cannot be read — never a guess."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        out = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return out if out.tzinfo else out.replace(tzinfo=timezone.utc)


def _placer(starts: list[tuple[str, int]]):
    """A function from a trade's timestamp to the ACCOUNT it was made on, or `None`.

    A run connects to one account for its whole life, so a trade belongs to the account of the
    latest startup at or before it. ⚠ `None` when no startup precedes it or its time cannot be
    read — the caller COUNTS those rather than crediting them to a guess.
    """
    timeline = sorted((t, acct) for t, acct in ((_instant(ts), a) for ts, a in starts) if t)
    stamps = [t for t, _ in timeline]

    def place(ts) -> int | None:
        at = _instant(ts)
        if at is None:
            return None
        i = bisect.bisect_right(stamps, at) - 1
        return timeline[i][1] if i >= 0 else None

    return place


def read_bot_ledger(
    bot_key: str,
    live_trades: list[dict] | None = None,
    *,
    account: int | None = None,
    live_starts: list[tuple[str, int]] | None = None,
) -> dict:
    """Sum one bot's realised results out of its own decision record.

    `account` scopes the sum to the trades made ON that account — see the module docstring;
    `None` sums every trade the bot has, which is what a caller asking about the bot rather than
    an account wants. `live_starts` is the box's own startups, read beside `live_trades`: a run that
    began since the last sync is only on the box, and without it that run's trades would be placed
    on the account before it.

    `live_trades` is what the BOX just said, read off the bot's own live ledger in the same SSH
    the balances came from. 🔴 **`None` means the box was not asked or did not answer; `[]` means
    it answered and there were no trades in the window.** Those are different facts and only one
    of them says the figure below is as fresh as the balance it will be subtracted from — this
    repo's rule 1, and the whole reason this argument is not a plain list.

    🔴 **The two halves of the account subtraction used to be read off two different clocks.** The
    balance is seconds old (SSH, live); the archive is behind by however long ago the box last
    committed AND this machine last pulled — MEASURED at 66 minutes on 2026-09-09 with no upper
    bound, since nothing here pulls. So a trade that closed inside that window was already in the
    account's balance and in no bot's row, which under-reports that bot by exactly its profit and
    over-reports *"not from these bots"* by the same amount. It happened for real: the extreme
    leg's **$1,305.58** target on 2026-09-09 read as money nobody's bot made.

    Returns `traded: False` with everything else `None` when there is no record at all — see the
    module docstring on why that may not collapse to zero.
    """
    scan = _archive_scan(bot_key)
    live = list(live_trades) if live_trades is not None else []

    if scan is None and live_trades is None:
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
            "records_through": None,
            "record_source": "archive",
            "unplaced_trades": None,
        }

    if scan is None:
        # The box answered and this machine has never archived anything for this bot. That is a
        # real record — a bot registered after the last sync — and refusing it would report a
        # trading bot as untraded while its own ledger is right there in the response.
        rows, reach, first, last, starts = [], None, None, None, []
    else:
        rows, reach, first, last, starts = scan
    starts = list(dict.fromkeys([*starts, *(live_starts or [])]))

    # ⚠ The live rows are merged rather than preferred, and the archive is not trusted to be a
    # subset either: a window bounded by month (see the router) cannot reach a trade older than
    # it, and the archive cannot reach one newer than its last sync. Each holds what the other
    # cannot, so the union is the only complete answer and the dedup is what makes it safe.
    if live:
        seen = {_dedup_key(r) for r in rows}
        for r in live:
            k = _dedup_key(r)
            if k not in seen:
                seen.add(k)
                rows.append(r)

    unplaced = 0
    if account is not None:
        place = _placer(starts)
        placed = [(place(row.get("ts")), row) for row in rows]
        unplaced = sum(1 for acct, _ in placed if acct is None)
        rows = [row for acct, row in placed if acct == account]
        # When this bot ARRIVED here, not when its record began: the account's opening is
        # whichever bot has been here longest, and a bot that traded somewhere else first did not
        # arrive here on its first day.
        here = sorted(t for t, a in ((_instant(ts), a) for ts, a in starts) if t and a == account)
        first = here[0].date().isoformat() if here else first

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
    return {
        "bot_key": bot_key,
        "traded": True,
        "reason": None,
        "closed_trades": len(rows),
        "realised_usd": round(usd, 2),
        "realised_r": round(r, 4),
        "wins": wins,
        "losses": losses,
        "records_from": first,
        "records_to": last,
        # How far this bot's record actually REACHES. `None` = could not be told, never "now".
        # When the box answered, its own ledger was read a moment ago, so the reach is the read
        # itself and the caller stamps it — this is the archive's reach and nothing else.
        "records_through": reach,
        # "live" = the box's own ledger was read in the same breath as the balance, so this
        # figure and that balance share a clock. "archive" = it does not, and the caller has to
        # say so rather than printing a confident split.
        "record_source": "live" if live_trades is not None else "archive",
        # Trades no startup precedes, so the account they were made on cannot be told. Counted,
        # never credited to a guess; only meaningful when an `account` was asked about.
        "unplaced_trades": unplaced,
    }


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


def _lag_seconds(reach: str | None, as_of: datetime | None) -> float | None:
    """How far behind `as_of` a record that reaches `reach` is. `None` = cannot be told."""
    if not reach or as_of is None:
        return None
    try:
        stamp = datetime.fromisoformat(reach)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    # Clamped at zero rather than reported negative: a record stamped slightly ahead of the read
    # is two clocks disagreeing, not a record from the future, and a negative lag on a page reads
    # as a bug in the page.
    return max(0.0, (as_of - stamp).total_seconds())


def _freshness(merged: list[dict], as_of: datetime | None) -> tuple[bool, float | None, str | None]:
    """Whether the split below shares a clock with the balance, and what to say when it does not.

    🔴 **This exists because a STALE READ and a REAL ATTRIBUTION GAP were the same pixel.** The
    remainder line says the money came from a manual fill, a deposit or a trade older than the
    record — three real causes — and it said exactly that for a trade that had simply not been
    synced yet. Aaron saw it on 2026-09-09 and the two are indistinguishable to a reader, which
    makes the honest answer a fourth sentence rather than a better number.
    """
    traded = [r for r in merged if r.get("traded")]
    if not traded:
        return True, None, None

    stale = [r for r in traded if r.get("record_source") != "live"]
    if not stale:
        return True, 0.0, None

    lags = [_lag_seconds(r.get("records_through"), as_of) for r in stale]
    known = [x for x in lags if x is not None]
    # The WORST lag, not the average: the question is whether ANY trade could be missing, and one
    # bot an hour behind makes the whole split provisional however fresh its neighbour is.
    worst = max(known) if known else None

    if worst is None:
        how = "how far behind it is could not be read"
    elif worst < 120:
        # Under two minutes is the sync landing between the two reads. Say the number anyway —
        # a threshold that silently reclassifies a lag as "fine" is the guard this repo keeps
        # having to un-learn.
        how = f"{int(worst)} seconds behind it"
    elif worst < 7200:
        how = f"{int(round(worst / 60))} minutes behind it"
    else:
        how = f"{worst / 3600:.1f} hours behind it"

    if len(stale) == 1:
        who = "One of these bots' records was"
        lag = "and it is " if worst is not None else "and "
    else:
        who = f"{len(stale)} of these bots' records were"
        lag = "and the furthest is " if worst is not None else "and "
    return (
        False,
        worst,
        (
            f"{who} read from this machine's archive rather than from the box, {lag}{how}. A trade "
            f"closed since then is already in the balance and in no bot's row, so each bot's figure "
            f"is a floor and the remainder is a ceiling until it syncs."
        ),
    )


def accounts_traded(
    bot_key: str,
    live_trades: list[dict] | None = None,
    live_starts: list[tuple[str, int]] | None = None,
) -> set[int]:
    """Every account this bot has CLOSED a trade on, placed by its startups. Empty when it has
    none or no record — an account it only started on and never traded is not history."""
    scan = _archive_scan(bot_key)
    rows, starts = (scan[0], scan[4]) if scan else ([], [])
    rows = [*rows, *(live_trades or [])]
    place = _placer([*starts, *(live_starts or [])])
    return {a for a in (place(r.get("ts")) for r in rows) if a is not None}


def account_earnings(bots: list[dict], as_of: datetime | None = None) -> list[dict]:
    """Group bots by account and answer both halves: what the account did, and what each bot did.

    `bots` is one dict per bot carrying `bot_key`, `name`, `account`, `balance` and
    `starting_balance` — read off the snapshot that has already been fetched, so this adds no SSH.
    A bot dict may also carry `live_trades`: the closed-trade rows the BOX just reported, or
    `None`/absent when it was not asked. See `read_bot_ledger` on why that is not a plain list.

    `as_of` is when the BALANCE was read. It is what the record's reach is measured against, so
    the page can say whether the two halves of its own subtraction share a clock.
    """
    by_account: dict[int, list[dict]] = {}
    for b in bots:
        acct = b.get("account")
        if not acct:
            continue
        by_account.setdefault(int(acct), []).append(b)

    # 🔴 An account a bot has LEFT keeps that bot's trades there — see the module docstring. It is
    # history: nothing on it reports a balance, so it carries the trades and nothing derived from
    # the account's growth.
    former: dict[int, list[dict]] = {}
    for b in bots:
        now = int(b["account"]) if b.get("account") else None
        for acct in accounts_traded(b["bot_key"], b.get("live_trades"), b.get("live_starts")):
            if acct != now:
                former.setdefault(acct, []).append({**b, "moved_to": now})

    def _ledger(r: dict, account: int) -> dict:
        return read_bot_ledger(
            r["bot_key"], r.get("live_trades"), account=account, live_starts=r.get("live_starts")
        )

    out: list[dict] = []
    for account in sorted(set(by_account) | set(former)):
        rows = by_account.get(account, [])
        merged = [{**r, **_ledger(r, account)} for r in rows]
        left = [{**r, **_ledger(r, account), "former": True} for r in former.get(account, [])]

        # One pot of money, not one each — the same rule the page's own header learned on
        # 2026-09-04 after a two-bot stack reported an account's balance twice.
        balance = next((r["balance"] for r in merged if r.get("balance") is not None), None)
        opening, opening_from, opening_note = _pick_opening(merged)
        if not merged:
            opening_note = (
                "No bot is on this account now, so nothing reads its balance — this is the record "
                "of the bots that traded here."
            )

        net_usd = net_pct = None
        if balance is not None and opening:
            net_usd = round(balance - opening, 2)
            net_pct = round((balance - opening) / opening * 100, 2)

        traded = [r for r in merged if r.get("traded")]
        silent = [r["bot_key"] for r in merged if not r.get("traded")]
        attributed = round(sum(r["realised_usd"] or 0.0 for r in traded), 2) if traded else None

        unattributed = None
        # ⚠ Refused when a bot that has LEFT traded here too: whether its trades fall inside the
        # window the opening was taken at cannot be told, so either answer would be a guess.
        left_traded = any(r.get("closed_trades") for r in left)
        if net_usd is not None and attributed is not None and not left_traded:
            unattributed = round(net_usd - attributed, 2)

        records_live, lag, note = _freshness(merged, as_of)

        out.append(
            {
                "account": account,
                # Whether the bots' figures and the balance above them were read at the same
                # moment. False does NOT mean anything is wrong — it means the split is
                # provisional, and the page has to be able to tell a reader that.
                "records_live": records_live,
                "attribution_lag_seconds": lag,
                "attribution_note": note,
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
                        # A bot that has LEFT this account, and where it went. Its row is the
                        # record of what it did here — no controls belong to it on this account.
                        "former": bool(r.get("former")),
                        "moved_to": r.get("moved_to") if r.get("former") else None,
                        "unplaced_trades": r.get("unplaced_trades"),
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
                        "records_through": r.get("records_through"),
                        "record_source": r.get("record_source"),
                        # The number Aaron asked for: what this bot made, as a share of what the
                        # ACCOUNT opened at — so two bots on one balance are directly comparable
                        # and neither is credited with the other's growth.
                        # Never for a bot that has LEFT: the opening is the current bots' anchor,
                        # and dividing a departed bot's dollars by it mixes two accounts' starts.
                        "pct_of_opening": (
                            round((r["realised_usd"] or 0.0) / opening * 100, 2)
                            if opening and r.get("traded") and not r.get("former")
                            else None
                        ),
                    }
                    for r in [*merged, *left]
                ],
            }
        )
    return out
